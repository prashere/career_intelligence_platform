import hashlib
from typing import Any

from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.text_utils import classify_opportunity_type, extract_requirements, parse_deadline
from app.models import Opportunity, OpportunityType, RawDocument


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


async def fetch_source(session: AsyncSession, source_id: str) -> dict[str, Any]:
    """Run registry-driven ingestion pipeline for one source."""
    from app.ingestion.pipeline import run_source_ingestion

    return await run_source_ingestion(session, source_id)


async def normalize_raw_documents(session: AsyncSession, limit: int = 100) -> dict[str, Any]:
    """Legacy normalize path — pipeline extracts inline; process any backlog rows."""
    result = await session.execute(
        select(RawDocument).where(RawDocument.processed.is_(False)).limit(limit)
    )
    docs = result.scalars().all()
    if not docs:
        return {"created": 0, "skipped": 0, "note": "pipeline_inline"}

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
        title = doc.title or (soup.get_text(strip=True)[:500] if soup else doc.raw_content[:200])
        if soup and not doc.title:
            title_el = soup.find(["h1", "h2", "h3", "title"])
            if title_el:
                title = title_el.get_text(strip=True)[:500]

        summary = doc.summary or (
            BeautifulSoup(doc.raw_content, "lxml").get_text(" ", strip=True)[:2000]
            if soup
            else doc.raw_content[:2000]
        )
        opp_type_str = classify_opportunity_type(title, summary)
        try:
            opp_type = OpportunityType(opp_type_str)
        except ValueError:
            opp_type = OpportunityType.other
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
