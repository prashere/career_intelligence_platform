"""Staleness detection — re-fetch stored URLs (Task 6)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models import Opportunity, OpportunitySource
from app.models.verification import VerificationStatus
from app.verification.compare import _deadline_match
from app.verification.page_intel import fetch_page_text_sync, heuristic_extract_page

logger = get_logger(__name__)

_STALE_PHRASES = re.compile(
    r"(no longer accepting|applications?\s+closed|deadline\s+has\s+passed|"
    r"this\s+(page|opportunity)\s+(has\s+)?expired|not\s+accepting\s+applications|"
    r"404\s+not\s+found|page\s+not\s+found)",
    re.I,
)


async def find_staleness_candidates(session: AsyncSession, limit: int | None = None) -> list[str]:
    now = datetime.now(timezone.utc)
    not_seen_cutoff = now - timedelta(days=settings.staleness_not_seen_days)
    recrawl_cutoff = now - timedelta(days=settings.staleness_recrawl_days)

    query = (
        select(Opportunity.id)
        .where(
            Opportunity.duplicate_of.is_(None),
            or_(
                Opportunity.verification_status.is_(None),
                Opportunity.verification_status != VerificationStatus.stale.value,
            ),
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
            or_(
                Opportunity.last_seen_at.is_(None),
                Opportunity.last_seen_at < not_seen_cutoff,
                Opportunity.verified_at.is_(None),
                Opportunity.verified_at < recrawl_cutoff,
            ),
        )
        .order_by(Opportunity.last_seen_at.asc().nullsfirst())
    )
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return [row[0] for row in result.all()]


def _page_looks_stale(page_text: str) -> bool:
    if not page_text or len(page_text.strip()) < 80:
        return True
    return bool(_STALE_PHRASES.search(page_text[:4000]))


async def check_opportunity_staleness(
    session: AsyncSession,
    opportunity_id: str,
) -> dict:
    opp = await session.get(Opportunity, opportunity_id)
    if not opp or not opp.url:
        return {"ok": False, "error": "not_found"}

    source: OpportunitySource | None = None
    if opp.source_id:
        source = await session.get(OpportunitySource, opp.source_id)

    extract_config = (source.parser_config or {}) if source else {}
    try:
        page_text = fetch_page_text_sync(opp.url, extract_config)
    except Exception as exc:
        opp.verification_status = VerificationStatus.stale.value
        opp.verified_at = datetime.now(timezone.utc)
        opp.verification_meta = {
            **(opp.verification_meta or {}),
            "staleness_check": {"reason": "fetch_failed", "error": str(exc)},
        }
        await session.flush()
        return {"ok": True, "stale": True, "reason": "fetch_failed"}

    if _page_looks_stale(page_text):
        opp.verification_status = VerificationStatus.stale.value
        opp.verified_at = datetime.now(timezone.utc)
        opp.verification_meta = {
            **(opp.verification_meta or {}),
            "staleness_check": {"reason": "stale_phrase_or_empty"},
        }
        await session.flush()
        return {"ok": True, "stale": True, "reason": "stale_phrase"}

    primary = heuristic_extract_page(
        page_text,
        opp.url,
        extract_config,
        fallback_title=opp.title,
        fallback_summary=opp.summary or "",
    )
    d_match, _, d_note = _deadline_match(opp.deadline, primary.deadline)
    if opp.deadline and primary.deadline and not d_match:
        opp.verification_status = VerificationStatus.stale.value
        opp.verified_at = datetime.now(timezone.utc)
        opp.verification_meta = {
            **(opp.verification_meta or {}),
            "staleness_check": {"reason": "deadline_mismatch", "note": d_note},
        }
        await session.flush()
        return {"ok": True, "stale": True, "reason": "deadline_mismatch"}

    opp.verified_at = datetime.now(timezone.utc)
    if opp.verification_status == VerificationStatus.stale.value:
        opp.verification_status = VerificationStatus.unverified.value
    opp.verification_meta = {
        **(opp.verification_meta or {}),
        "staleness_check": {"reason": "ok", "checked_at": datetime.now(timezone.utc).isoformat()},
    }
    await session.flush()
    return {"ok": True, "stale": False}


async def run_staleness_batch(session: AsyncSession, limit: int | None = None) -> dict:
    batch = limit or settings.staleness_check_batch_size
    ids = await find_staleness_candidates(session, limit=batch)
    stale = 0
    errors = 0
    for oid in ids:
        try:
            outcome = await check_opportunity_staleness(session, oid)
            if outcome.get("stale"):
                stale += 1
        except Exception as exc:
            errors += 1
            logger.warning("staleness_check_failed", opportunity_id=oid, error=str(exc))
    await session.commit()
    return {"processed": len(ids), "marked_stale": stale, "errors": errors}
