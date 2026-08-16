"""Extraction ladder — structured, adapter selectors, heuristics (Phase A, no LLM)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.ingestion.text_utils import classify_opportunity_type, extract_requirements, parse_deadline


@dataclass
class ExtractedOpportunity:
    title: str = ""
    summary: str = ""
    institution: Optional[str] = None
    program: Optional[str] = None
    deadline: Optional[datetime] = None
    opportunity_type: str = "other"
    requirements: list[str] = field(default_factory=list)
    funding_type: Optional[str] = None
    degree_levels: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    extraction_confidence: str = "medium"
    field_provenance: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


def _strip_html(text: str) -> str:
    if not text or "<" not in text:
        return text.strip()
    return BeautifulSoup(text, "lxml").get_text(" ", strip=True)


def _extract_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        return item
            elif isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def _parse_structured(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ld = _extract_json_ld(soup)
    if ld:
        out["title"] = ld.get("name") or ld.get("headline")
        out["summary"] = ld.get("description")
        end = ld.get("endDate") or ld.get("validThrough")
        if end:
            try:
                out["deadline"] = date_parser.parse(str(end))
            except (ValueError, OverflowError):
                pass
        org = ld.get("provider") or ld.get("organizer") or {}
        if isinstance(org, dict):
            out["institution"] = org.get("name")
        elif isinstance(org, str):
            out["institution"] = org
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        out.setdefault("title", og_title["content"])
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        out.setdefault("summary", og_desc["content"])
    return out


def _select_text(soup: BeautifulSoup, selector: str) -> str:
    el = soup.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


def _clean_content(soup: BeautifulSoup, content_selector: str, remove: list[str]) -> str:
    root = soup.select_one(content_selector) or soup.body or soup
    clone = BeautifulSoup(str(root), "lxml")
    for sel in remove:
        for el in clone.select(sel):
            el.decompose()
    return clone.get_text("\n", strip=True)


def _detect_funding(text: str) -> Optional[str]:
    lower = text.lower()
    if any(k in lower for k in ("fully funded", "full scholarship", "full tuition", "full stipend")):
        return "full"
    if any(k in lower for k in ("partial", "tuition waiver")):
        return "partial"
    if any(k in lower for k in ("self-funded", "self funded")):
        return "self"
    return None


def _detect_degrees(text: str) -> list[str]:
    found = []
    mapping = {
        "phd": "PhD",
        "doctoral": "PhD",
        "master": "MSc",
        "msc": "MSc",
        "undergraduate": "Undergraduate",
        "bachelor": "Undergraduate",
        "fellowship": "Fellowship",
        "internship": "Internship",
    }
    lower = text.lower()
    for key, label in mapping.items():
        if key in lower and label not in found:
            found.append(label)
    return found


def extract_from_feed_item(
    title: str,
    summary: str,
    extract_config: dict[str, Any],
) -> ExtractedOpportunity:
    feed_cfg = extract_config.get("feed") or {}
    if feed_cfg.get("strip_html", True):
        summary = _strip_html(summary)
    text = f"{title}\n{summary}"
    deadline = parse_deadline(text)
    opp_type = classify_opportunity_type(title, summary)
    return ExtractedOpportunity(
        title=title or "Untitled",
        summary=summary[:4000],
        deadline=deadline,
        opportunity_type=opp_type,
        requirements=extract_requirements(text),
        funding_type=_detect_funding(text),
        degree_levels=_detect_degrees(text),
        extraction_confidence="medium" if summary else "low",
        field_provenance={"title": "feed", "summary": "feed"},
    )


def extract_from_html(
    html: str,
    base_url: str,
    extract_config: dict[str, Any],
    *,
    fallback_title: str = "",
    fallback_summary: str = "",
) -> ExtractedOpportunity:
    soup = BeautifulSoup(html, "lxml")
    detail = extract_config.get("detail") or {}
    provenance: dict[str, str] = {}

    structured = _parse_structured(soup)
    title = structured.get("title") or _select_text(soup, detail.get("title") or "h1") or fallback_title
    provenance["title"] = "structured" if structured.get("title") else "adapter"

    content = ""
    if detail.get("content"):
        content = _clean_content(soup, detail["content"], detail.get("remove") or [])
        provenance["summary"] = "adapter"
    if not content:
        content = structured.get("summary") or fallback_summary
        if structured.get("summary"):
            provenance["summary"] = "structured"
        elif fallback_summary:
            provenance["summary"] = "feed"
        else:
            provenance["summary"] = "heuristic"
            content = soup.get_text("\n", strip=True)[:8000]

    text = f"{title}\n{content}"
    deadline = structured.get("deadline")
    if not deadline:
        patterns = detail.get("deadline_patterns") or [
            r"(?i)deadline[:\s]+([^<\n\.]+)",
            r"(?i)apply by[:\s]+([^<\n\.]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    deadline = date_parser.parse(match.group(1), fuzzy=True)
                    provenance["deadline"] = "heuristic"
                    break
                except (ValueError, OverflowError):
                    continue

    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    institution = structured.get("institution")
    if institution:
        provenance["institution"] = "structured"

    confidence = "high" if provenance.get("summary") == "adapter" and deadline else "medium"
    if not content:
        confidence = "low"

    opp_type = classify_opportunity_type(title, content)
    return ExtractedOpportunity(
        title=(title or "Untitled")[:500],
        summary=content[:4000],
        institution=institution,
        deadline=deadline,
        opportunity_type=opp_type,
        requirements=extract_requirements(text),
        funding_type=_detect_funding(text),
        degree_levels=_detect_degrees(text),
        extraction_confidence=confidence,
        field_provenance=provenance,
    )


def should_fetch_detail(source_summary_completeness: str, extract_config: dict[str, Any]) -> bool:
    if source_summary_completeness == "full_in_feed":
        return False
    detail_fetch = (extract_config or {}).get("detail_fetch") or "optional"
    return detail_fetch in ("required", "optional", True)


def _uses_jina_markdown(extract_config: dict[str, Any]) -> bool:
    return bool(extract_config.get("proxy_prefix")) or extract_config.get("content_format") == "jina_markdown"


def fetch_detail_text(client: Any, url: str, extract_config: dict[str, Any], *, headers: dict[str, str] | None = None) -> str:
    """Fetch a detail page, optionally through the Jina reader proxy."""
    if _uses_jina_markdown(extract_config):
        from app.ingestion.discover.strategies import _fetch_jina_text, _jina_markdown_body

        proxy_prefix = extract_config.get("proxy_prefix") or "https://r.jina.ai/"
        return _jina_markdown_body(_fetch_jina_text(client, url, proxy_prefix=proxy_prefix))

    response = client.get(url, headers=headers or {})
    response.raise_for_status()
    return response.text


def extract_from_jina_markdown(
    markdown: str,
    base_url: str,
    extract_config: dict[str, Any],
    *,
    fallback_title: str = "",
    fallback_summary: str = "",
) -> ExtractedOpportunity:
    """Parse ProFellow-style fellowship database pages returned as Jina markdown."""
    provenance: dict[str, str] = {}
    body = markdown.strip()

    title = fallback_title
    heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if heading:
        title = heading.group(1).strip()
        provenance["title"] = "adapter"

    institution = None
    org_match = re.search(
        r"!\[Image \d+: Organization\]\([^)]+\)\s+([^\n]+)",
        body,
    )
    if org_match:
        institution = org_match.group(1).strip()
        provenance["institution"] = "adapter"

    deadline = None
    deadline_match = re.search(
        r"!\[Image \d+: Deadline\]\([^)]+\)\s+([^\n]+)",
        body,
    )
    if deadline_match:
        raw_deadline = deadline_match.group(1).strip()
        if raw_deadline and "1970" not in raw_deadline:
            try:
                deadline = date_parser.parse(raw_deadline, fuzzy=True)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                provenance["deadline"] = "adapter"
            except (ValueError, OverflowError):
                pass

    summary = fallback_summary
    if heading:
        start = heading.end()
        end = len(body)
        for marker in ("\n## Create a free ProFellow account", "\n## Related Programs", "\n## "):
            idx = body.find(marker, start)
            if idx > start:
                end = min(end, idx)
        block = body[start:end].strip()
        # Drop metadata lines (organization, location, deadline icons).
        lines = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("![") and (
                "Organization" in stripped or "Location" in stripped or "Deadline" in stripped
            ):
                continue
            if stripped.startswith("**Type:") or stripped.startswith("**Discipline:") or stripped.startswith(
                "**Keywords:"
            ):
                continue
            lines.append(stripped)
        if lines:
            summary = " ".join(lines)[:4000]
            provenance["summary"] = "adapter"

    if not summary:
        summary = fallback_summary
        provenance["summary"] = "feed" if fallback_summary else "heuristic"

    text = f"{title}\n{summary}"
    if not deadline:
        patterns = extract_config.get("deadline_patterns") or (extract_config.get("detail") or {}).get(
            "deadline_patterns"
        ) or [
            r"(?i)deadline[:\s]+([^<\n\.]+)",
            r"(?i)apply by[:\s]+([^<\n\.]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                try:
                    deadline = date_parser.parse(match.group(1), fuzzy=True)
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    provenance["deadline"] = "heuristic"
                    break
                except (ValueError, OverflowError):
                    continue

    opp_type = classify_opportunity_type(title, summary)
    confidence = "high" if provenance.get("summary") == "adapter" and institution else "medium"
    if not summary:
        confidence = "low"

    return ExtractedOpportunity(
        title=title or "Untitled",
        summary=summary[:4000],
        institution=institution,
        deadline=deadline,
        opportunity_type=opp_type,
        requirements=extract_requirements(text),
        funding_type=_detect_funding(text),
        degree_levels=_detect_degrees(text),
        extraction_confidence=confidence,
        field_provenance=provenance,
    )


def extract_detail(
    content: str,
    base_url: str,
    extract_config: dict[str, Any],
    *,
    fallback_title: str = "",
    fallback_summary: str = "",
) -> ExtractedOpportunity:
    if _uses_jina_markdown(extract_config):
        return extract_from_jina_markdown(
            content,
            base_url,
            extract_config,
            fallback_title=fallback_title,
            fallback_summary=fallback_summary,
        )
    return extract_from_html(
        content,
        base_url,
        extract_config,
        fallback_title=fallback_title,
        fallback_summary=fallback_summary,
    )
