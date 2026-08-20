"""Verification orchestration — tier 0 eligibility through tier 2 agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models import Opportunity, OpportunitySource
from app.models.verification import VerificationStatus
from app.telemetry.langsmith import traceable
from app.verification.agent import verify_opportunity_with_agent
from app.verification.cache import get_org_domain, refresh_domain_legitimacy
from app.verification.contracts import AggregatorClaims, VerificationResult
from app.verification.domain_utils import extract_domain, guess_org_name
from app.verification.prescreen import run_prescreen

from app.verification.eligibility import is_eligible_for_verification

logger = get_logger(__name__)


def _claims_from_opportunity(opp: Opportunity) -> AggregatorClaims:
    elig = " ".join(opp.requirements or [])[:800] if opp.requirements else None
    return AggregatorClaims(
        title=opp.title,
        url=opp.url,
        institution=opp.institution,
        program=opp.program,
        deadline=opp.deadline,
        funding_type=opp.funding_type,
        summary=opp.summary,
        eligibility_text=elig,
    )


async def apply_verification_result(
    session: AsyncSession,
    opportunity: Opportunity,
    result: VerificationResult,
    *,
    commit: bool = True,
) -> None:
    opportunity.verification_status = result.status
    opportunity.verified_at = datetime.now(timezone.utc)
    opportunity.verification_meta = {
        "trust_score": result.trust_score,
        "primary_url": result.primary_url,
        "search_queries": result.search_queries,
        **result.meta,
    }
    if commit:
        await session.commit()
    else:
        await session.flush()


@traceable(run_type="chain", name="verify_opportunity", tags=["verification"])
async def verify_opportunity(
    session: AsyncSession,
    opportunity_id: str,
) -> dict:
    opp = await session.get(Opportunity, opportunity_id)
    if not opp:
        return {"ok": False, "error": "not_found"}

    if not is_eligible_for_verification(opp):
        return {"ok": False, "error": "not_eligible", "opportunity_id": opportunity_id}

    if opp.verification_status in (
        VerificationStatus.primary_confirmed.value,
        VerificationStatus.stale.value,
    ):
        return {"ok": True, "skipped": True, "status": opp.verification_status}

    source = None
    if opp.source_id:
        source = await session.get(OpportunitySource, opp.source_id)

    claims = _claims_from_opportunity(opp)
    org_name = guess_org_name(claims.title, claims.institution, claims.summary)
    listing_domain = extract_domain(claims.url)

    domain_rec = None
    domain_flags: list[str] = []
    if listing_domain:
        domain_rec = await refresh_domain_legitimacy(
            session,
            listing_domain,
            page_text=f"{claims.title} {claims.summary or ''}",
            commit=False,
        )
        domain_flags = list(domain_rec.flags or [])

    cached_org = await get_org_domain(session, org_name)
    cached_conf = cached_org.confidence if cached_org else None

    prescreen = run_prescreen(
        claims,
        domain_trust=domain_rec.trust_score if domain_rec else None,
        domain_flags=domain_flags,
        cached_org_confidence=cached_conf,
        source_outcome_stats=source.outcome_stats if source else None,
        allowlisted_domain=bool(cached_org),
    )

    if prescreen.action == "stop":
        result = VerificationResult(
            status=VerificationStatus.aggregator_only.value,
            trust_score=prescreen.trust_score,
            prescreen=prescreen,
            meta={"tier1_only": True, "prescreen": {"flags": prescreen.flags, "action": "stop"}},
        )
        await apply_verification_result(session, opp, result, commit=False)
        await session.commit()
        return {"ok": True, "status": result.status, "trust_score": result.trust_score}

    result = await verify_opportunity_with_agent(session, opp, source, prescreen)
    await apply_verification_result(session, opp, result, commit=False)

    # Update source outcome stats with verification signal when confirmed
    if source and result.status == VerificationStatus.primary_confirmed.value:
        stats = dict(source.outcome_stats or {})
        stats["primary_confirmed_total"] = int(stats.get("primary_confirmed_total") or 0) + 1
        stats["last_primary_confirmed_at"] = datetime.now(timezone.utc).isoformat()
        source.outcome_stats = stats

    await session.commit()
    return {
        "ok": True,
        "opportunity_id": opportunity_id,
        "status": result.status,
        "trust_score": result.trust_score,
        "primary_url": result.primary_url,
    }


async def find_pending_verification_ids(
    session: AsyncSession,
    *,
    limit: int | None = None,
    since_hours: int = 48,
) -> list[str]:
    """Opportunities that passed the gate but are still unverified."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    result = await session.execute(
        select(Opportunity.id)
        .where(
            Opportunity.verification_status == VerificationStatus.unverified.value,
            Opportunity.ingestion_meta.isnot(None),
            Opportunity.created_at >= cutoff,
        )
        .order_by(Opportunity.created_at.desc())
        .limit(limit or settings.verification_batch_size)
    )
    ids = [row[0] for row in result.all()]
    # Filter in Python for gate verdict (JSONB query avoided for simplicity)
    if not ids:
        return []
    opps = await session.execute(select(Opportunity).where(Opportunity.id.in_(ids)))
    return [o.id for o in opps.scalars().all() if is_eligible_for_verification(o)]


async def find_backlog_verification_ids(
    session: AsyncSession,
    *,
    limit: int | None = None,
    include_aggregator_only: bool = False,
) -> list[str]:
    """Unverified opportunities eligible for verification (no time cutoff)."""
    statuses = [VerificationStatus.unverified.value]
    if include_aggregator_only:
        statuses.append(VerificationStatus.aggregator_only.value)

    result = await session.execute(
        select(Opportunity.id)
        .where(
            Opportunity.verification_status.in_(statuses),
            Opportunity.duplicate_of.is_(None),
        )
        .order_by(Opportunity.created_at.asc())
        .limit(limit or settings.verification_batch_size)
    )
    ids = [row[0] for row in result.all()]
    if not ids:
        return []
    opps = await session.execute(select(Opportunity).where(Opportunity.id.in_(ids)))
    return [o.id for o in opps.scalars().all() if is_eligible_for_verification(o)]


async def run_verification_backfill(
    session: AsyncSession,
    *,
    limit: int | None = None,
    include_aggregator_only: bool = False,
) -> dict:
    ids = await find_backlog_verification_ids(
        session,
        limit=limit,
        include_aggregator_only=include_aggregator_only,
    )
    outcomes = []
    for oid in ids:
        try:
            outcomes.append(await verify_opportunity(session, oid))
        except Exception as exc:
            logger.exception("verification_backfill_failed", opportunity_id=oid)
            outcomes.append({"ok": False, "opportunity_id": oid, "error": str(exc)})
    confirmed = sum(1 for o in outcomes if o.get("status") == VerificationStatus.primary_confirmed.value)
    return {
        "ok": True,
        "processed": len(outcomes),
        "primary_confirmed": confirmed,
        "outcomes": outcomes,
    }


async def run_verification_batch(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> dict:
    ids = await find_pending_verification_ids(session, limit=limit)
    outcomes = []
    for oid in ids:
        try:
            outcomes.append(await verify_opportunity(session, oid))
        except Exception as exc:
            logger.exception("verification_failed", opportunity_id=oid)
            outcomes.append({"ok": False, "opportunity_id": oid, "error": str(exc)})
    confirmed = sum(1 for o in outcomes if o.get("status") == VerificationStatus.primary_confirmed.value)
    return {
        "ok": True,
        "processed": len(outcomes),
        "primary_confirmed": confirmed,
        "outcomes": outcomes,
    }
