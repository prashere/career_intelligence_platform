"""Dedup and upsert opportunities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from rapidfuzz import fuzz
from sqlalchemy import or_, select
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
    ingestion_meta: dict[str, Any] | None = None,
    now: Optional[datetime] = None,
) -> tuple[str, bool, bool]:
    """Returns (opportunity_id, created, updated_fields)."""
    now = now or datetime.now(timezone.utc)
    parser_config = source.parser_config or {}
    canonical = canonicalize_url(item_url, parser_config)
    url_h = hash_url(canonical)
    content_h = hash_content(content_for_hash)

    result = await session.execute(select(Opportunity).where(Opportunity.url_hash == url_h))
    existing = result.scalar_one_or_none()

    fuzzy_match: Optional[Opportunity] = None
    if not existing:
        fuzzy_match = await _find_fuzzy_duplicate(session, extracted.title, extracted.institution)
        if fuzzy_match and fuzzy_match.source_id and fuzzy_match.source_id != source.id:
            shadow = _new_opportunity(
                source,
                item_url,
                canonical,
                url_h,
                content_h,
                extracted,
                opp_type=_resolve_type(extracted),
                raw_document_id=raw_document_id,
                ingestion_meta={
                    **(ingestion_meta or {}),
                    "dedupe": "cross_source_fuzzy",
                },
                now=now,
                duplicate_of=fuzzy_match.id,
            )
            session.add(shadow)
            await session.flush()
            return shadow.id, True, True
        if fuzzy_match:
            existing = fuzzy_match

    try:
        opp_type = OpportunityType(extracted.opportunity_type)
    except ValueError:
        opp_type = OpportunityType.other

    if existing:
        _record_cross_source(existing, source)
        changed = _apply_updates(
            existing, extracted, opp_type, content_h, source, now, ingestion_meta=ingestion_meta,
        )
        if raw_document_id:
            existing.raw_document_id = raw_document_id
        if canonical and existing.canonical_url != canonical:
            existing.canonical_url = canonical
        await session.flush()
        return existing.id, False, changed

    opp = _new_opportunity(
        source,
        item_url,
        canonical,
        url_h,
        content_h,
        extracted,
        opp_type=opp_type,
        raw_document_id=raw_document_id,
        ingestion_meta=ingestion_meta,
        now=now,
    )
    session.add(opp)
    await session.flush()
    return opp.id, True, True


def _resolve_type(extracted: ExtractedOpportunity) -> OpportunityType:
    try:
        return OpportunityType(extracted.opportunity_type)
    except ValueError:
        return OpportunityType.other


def _new_opportunity(
    source: OpportunitySource,
    item_url: str,
    canonical: str,
    url_h: str,
    content_h: str,
    extracted: ExtractedOpportunity,
    *,
    opp_type: OpportunityType,
    raw_document_id: Optional[str],
    ingestion_meta: dict[str, Any] | None,
    now: datetime,
    duplicate_of: Optional[str] = None,
) -> Opportunity:
    return Opportunity(
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
        duplicate_of=duplicate_of,
        ingestion_meta=ingestion_meta,
        search_vector=f"{extracted.title} {extracted.summary}".lower()[:8000],
    )


def _record_cross_source(opp: Opportunity, source: OpportunitySource) -> None:
    if not source.id or opp.source_id == source.id:
        return
    meta = dict(opp.ingestion_meta or {})
    seen = list(meta.get("also_seen_from") or [])
    entry = {
        "source_id": source.id,
        "registry_id": source.registry_id,
        "name": source.name,
    }
    if entry not in seen:
        seen.append(entry)
    meta["also_seen_from"] = seen[-10:]
    opp.ingestion_meta = meta


async def _find_fuzzy_duplicate(
    session: AsyncSession,
    title: str,
    institution: Optional[str] = None,
) -> Optional[Opportunity]:
    if not title or len(title) < 8:
        return None

    query = (
        select(Opportunity)
        .where(Opportunity.duplicate_of.is_(None))
        .order_by(Opportunity.last_seen_at.desc().nullslast())
        .limit(200)
    )
    if institution and len(institution.strip()) >= 3:
        inst = institution.strip()
        query = query.where(
            or_(
                Opportunity.institution.ilike(f"%{inst}%"),
                Opportunity.title.ilike(f"%{inst}%"),
            )
        )
    result = await session.execute(query)
    best: Optional[Opportunity] = None
    best_score = 0.0
    title_lower = title.lower()
    for opp in result.scalars().all():
        ratio = fuzz.ratio(title_lower, (opp.title or "").lower())
        if ratio >= 92 and ratio > best_score:
            best = opp
            best_score = ratio
    return best


def _apply_updates(
    opp: Opportunity,
    extracted: ExtractedOpportunity,
    opp_type: OpportunityType,
    content_h: str,
    source: OpportunitySource,
    now: datetime,
    *,
    ingestion_meta: dict[str, Any] | None = None,
) -> bool:
    changes: list[dict[str, Any]] = list(opp.field_changes or [])
    updated = False

    if extracted.deadline and opp.deadline != extracted.deadline:
        changes.append(
            {"field": "deadline", "from": opp.deadline.isoformat() if opp.deadline else None, "to": extracted.deadline.isoformat()}
        )
        opp.deadline = extracted.deadline
        updated = True

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
    if ingestion_meta:
        opp.ingestion_meta = {**(opp.ingestion_meta or {}), **ingestion_meta}
    opp.field_changes = changes[-20:]
    opp.search_vector = f"{opp.title} {opp.summary or ''}".lower()[:8000]
    return updated
