"""Dedup and upsert opportunities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.canonicalize import canonicalize_url
from app.ingestion.extract.heuristic import ExtractedOpportunity
from app.models import Opportunity, OpportunitySource, OpportunityType
from app.services.ingestion import hash_content, hash_url


async def upsert_opportunity(
    session: AsyncSession,
    source: OpportunitySource,
    item_url: str,
    extracted: ExtractedOpportunity,
    raw_document_id: Optional[str],
    content_for_hash: str,
    *,
    now: Optional[datetime] = None,
) -> tuple[str, bool]:
    """Returns (opportunity_id, created)."""
    now = now or datetime.now(timezone.utc)
    parser_config = source.parser_config or {}
    canonical = canonicalize_url(item_url, parser_config)
    url_h = hash_url(canonical)
    content_h = hash_content(content_for_hash)

    result = await session.execute(select(Opportunity).where(Opportunity.url_hash == url_h))
    existing = result.scalar_one_or_none()

    if not existing:
        fuzzy = await _find_fuzzy_duplicate(session, extracted.title)
        if fuzzy:
            existing = fuzzy

    try:
        opp_type = OpportunityType(extracted.opportunity_type)
    except ValueError:
        opp_type = OpportunityType.other

    if existing:
        changed = _apply_updates(existing, extracted, opp_type, content_h, source, now)
        if raw_document_id:
            existing.raw_document_id = raw_document_id
        await session.flush()
        return existing.id, False if not changed else False

    opp = Opportunity(
        title=extracted.title,
        summary=extracted.summary,
        institution=extracted.institution,
        program=extracted.program,
        opportunity_type=opp_type,
        url=item_url,
        canonical_url=canonical,
        url_hash=url_h,
        content_hash=content_h,
        first_seen_at=now,
        last_seen_at=now,
        funding_type=extracted.funding_type,
        degree_levels=extracted.degree_levels,
        countries=extracted.countries,
        extraction_confidence=extracted.extraction_confidence,
        field_provenance=extracted.field_provenance,
        field_changes=[],
        deadline=extracted.deadline,
        requirements=extracted.requirements,
        tags=extracted.tags,
        source_id=source.id,
        raw_document_id=raw_document_id,
        search_vector=f"{extracted.title} {extracted.summary}".lower()[:8000],
    )
    session.add(opp)
    await session.flush()
    return opp.id, True


async def _find_fuzzy_duplicate(session: AsyncSession, title: str) -> Optional[Opportunity]:
    if not title or len(title) < 8:
        return None
    result = await session.execute(select(Opportunity).limit(500))
    for opp in result.scalars().all():
        if fuzz.ratio(title.lower(), (opp.title or "").lower()) >= 92:
            return opp
    return None


def _apply_updates(
    opp: Opportunity,
    extracted: ExtractedOpportunity,
    opp_type: OpportunityType,
    content_h: str,
    source: OpportunitySource,
    now: datetime,
) -> bool:
    changes: list[dict[str, Any]] = list(opp.field_changes or [])
    updated = False

    if extracted.deadline and opp.deadline != extracted.deadline:
        changes.append(
            {"field": "deadline", "from": opp.deadline.isoformat() if opp.deadline else None, "to": extracted.deadline.isoformat()}
        )
        opp.deadline = extracted.deadline
        updated = True

    source_authority = float(source.authority or 0.5)
    if extracted.summary and (not opp.summary or len(extracted.summary) > len(opp.summary or "")):
        opp.summary = extracted.summary
        updated = True

    if content_h != opp.content_hash:
        opp.content_hash = content_h
        updated = True

    opp.last_seen_at = now
    opp.opportunity_type = opp_type
    if extracted.funding_type:
        opp.funding_type = extracted.funding_type
    if extracted.degree_levels:
        opp.degree_levels = extracted.degree_levels
    if extracted.field_provenance:
        opp.field_provenance = {**(opp.field_provenance or {}), **extracted.field_provenance}
    opp.field_changes = changes[-20:]
    opp.search_vector = f"{opp.title} {opp.summary or ''}".lower()[:8000]
    return updated
