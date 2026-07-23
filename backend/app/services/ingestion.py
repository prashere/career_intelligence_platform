import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Opportunity,
    OpportunitySource,
    OpportunityType,
    RawDocument,
    SourceType,
)


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def classify_opportunity_type(title: str, summary: str = "") -> OpportunityType:
    text = f"{title} {summary}".lower()
    mapping = {
        OpportunityType.scholarship: ["scholarship", "stipend", "tuition"],
        OpportunityType.fellowship: ["fellowship", "fellow"],
        OpportunityType.internship: ["internship", "intern "],
        OpportunityType.graduate_program: ["graduate program", "master", "msc", "m.sc"],
        OpportunityType.phd: ["phd", "doctoral", "doctorate"],
        OpportunityType.grant: ["grant", "funding"],
        OpportunityType.conference: ["conference", "symposium"],
        OpportunityType.workshop: ["workshop", "summer school"],
        OpportunityType.competition: ["competition", "hackathon", "challenge"],
    }
    for opp_type, keywords in mapping.items():
        if any(k in text for k in keywords):
            return opp_type
    return OpportunityType.other


def parse_deadline(text: str) -> Optional[datetime]:
    if not text:
        return None
    patterns = [
        r"deadline[:\s]+([^\n\.]+)",
        r"due[:\s]+([^\n\.]+)",
        r"apply by[:\s]+([^\n\.]+)",
        r"closes?[:\s]+([^\n\.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                dt = date_parser.parse(match.group(1), fuzzy=True)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, OverflowError):
                continue
    return None


def extract_requirements(text: str) -> list[str]:
    reqs = []
    keywords = [
        "motivation letter",
        "recommendation",
        "transcript",
        "cv",
        "resume",
        "english proficiency",
        "statement of purpose",
        "portfolio",
    ]
    lower = text.lower()
    for kw in keywords:
        if kw in lower:
            reqs.append(kw.title())
    return reqs


class RSSFetcher:
    async def fetch(self, source: OpportunitySource) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(source.url)
            response.raise_for_status()
            feed = feedparser.parse(response.text)

        items = []
        for entry in feed.entries:
            url = entry.get("link") or source.url
            title = entry.get("title", "Untitled")
            summary = entry.get("summary", entry.get("description", ""))
            if hasattr(summary, "__html__"):
                summary = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
            items.append({"url": url, "title": title, "summary": summary, "raw_content": str(entry)})
        return items


class HTMLFetcher:
    async def fetch(self, source: OpportunitySource) -> list[dict[str, Any]]:
        config = source.parser_config or {}
        selector = config.get("item_selector", "article, .opportunity, li")
        title_sel = config.get("title_selector", "h2, h3, a")
        link_sel = config.get("link_selector", "a")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(source.url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")

        items = []
        for el in soup.select(selector)[:50]:
            title_el = el.select_one(title_sel)
            link_el = el.select_one(link_sel)
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = link_el.get("href") if link_el else source.url
            if url and url.startswith("/"):
                from urllib.parse import urljoin

                url = urljoin(source.url, url)
            summary = el.get_text(" ", strip=True)[:500]
            items.append({"url": url or source.url, "title": title, "summary": summary, "raw_content": str(el)})
        return items


class JSONFetcher:
    async def fetch(self, source: OpportunitySource) -> list[dict[str, Any]]:
        config = source.parser_config or {}
        items_path = config.get("items_path", "items")
        title_key = config.get("title_key", "title")
        url_key = config.get("url_key", "url")
        summary_key = config.get("summary_key", "summary")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(source.url)
            response.raise_for_status()
            data = response.json()

        raw_items = data
        for part in items_path.split("."):
            if part:
                raw_items = raw_items.get(part, []) if isinstance(raw_items, dict) else raw_items

        items = []
        for entry in raw_items[:50]:
            items.append(
                {
                    "url": entry.get(url_key, source.url),
                    "title": entry.get(title_key, "Untitled"),
                    "summary": entry.get(summary_key, ""),
                    "raw_content": str(entry),
                }
            )
        return items


FETCHERS = {
    SourceType.rss: RSSFetcher(),
    SourceType.html: HTMLFetcher(),
    SourceType.json: JSONFetcher(),
}


async def fetch_source(session: AsyncSession, source_id: str) -> dict[str, Any]:
    source = await session.get(OpportunitySource, source_id)
    if not source or not source.is_active:
        return {"fetched": 0, "error": "Source not found or inactive"}

    fetcher = FETCHERS.get(source.source_type)
    if not fetcher:
        source.last_error = f"No fetcher for {source.source_type}"
        await session.commit()
        return {"fetched": 0, "error": source.last_error}

    try:
        items = await fetcher.fetch(source)
        stored = 0
        for item in items:
            url = item["url"]
            url_h = hash_url(url)
            content = item.get("raw_content", item.get("summary", ""))
            content_h = hash_content(content)

            existing = await session.execute(
                select(RawDocument).where(RawDocument.url_hash == url_h, RawDocument.content_hash == content_h)
            )
            if existing.scalar_one_or_none():
                continue

            session.add(
                RawDocument(
                    source_id=source.id,
                    url=url,
                    url_hash=url_h,
                    raw_content=content,
                    content_hash=content_h,
                )
            )
            stored += 1

        source.last_fetched_at = datetime.now(timezone.utc)
        source.last_error = None
        await session.commit()
        return {"fetched": stored, "total_items": len(items)}
    except Exception as exc:
        source.last_error = str(exc)
        await session.commit()
        return {"fetched": 0, "error": str(exc)}


async def normalize_raw_documents(session: AsyncSession, limit: int = 100) -> dict[str, Any]:
    result = await session.execute(
        select(RawDocument).where(RawDocument.processed.is_(False)).limit(limit)
    )
    docs = result.scalars().all()
    created = 0
    skipped = 0

    for doc in docs:
        url_h = doc.url_hash
        existing = await session.execute(select(Opportunity).where(Opportunity.url_hash == url_h))
        if existing.scalar_one_or_none():
            doc.processed = True
            skipped += 1
            continue

        soup = BeautifulSoup(doc.raw_content, "lxml") if "<" in doc.raw_content else None
        title = soup.get_text(strip=True)[:500] if soup and not doc.raw_content.startswith("{") else doc.raw_content[:200]
        if soup:
            title_el = soup.find(["h1", "h2", "h3", "title"])
            if title_el:
                title = title_el.get_text(strip=True)[:500]

        summary = BeautifulSoup(doc.raw_content, "lxml").get_text(" ", strip=True)[:2000] if soup else doc.raw_content[:2000]
        opp_type = classify_opportunity_type(title, summary)
        deadline = parse_deadline(summary)
        requirements = extract_requirements(summary)

        fuzzy_dup = False
        all_opps = await session.execute(select(Opportunity.title, Opportunity.id))
        for existing_title, _ in all_opps.all():
            if fuzz.ratio(title.lower(), existing_title.lower()) > 90:
                fuzzy_dup = True
                break

        if fuzzy_dup:
            doc.processed = True
            skipped += 1
            continue

        session.add(
            Opportunity(
                title=title or "Untitled Opportunity",
                summary=summary,
                opportunity_type=opp_type,
                url=doc.url,
                url_hash=url_h,
                deadline=deadline,
                requirements=requirements,
                source_id=doc.source_id,
                raw_document_id=doc.id,
                search_vector=f"{title} {summary}".lower(),
            )
        )
        doc.processed = True
        created += 1

    await session.commit()
    return {"created": created, "skipped": skipped}
