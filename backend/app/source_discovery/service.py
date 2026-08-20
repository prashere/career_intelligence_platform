"""API-facing service for source discovery."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import (
    CandidateEvaluationVerdict,
    CandidateSource,
    CandidateSourceStatus,
    DiscoveryRun,
    DiscoveryRunStatus,
)
from app.source_discovery.contracts import SourceApprovalPayload
from app.source_discovery.promotion import promote_candidate_source, _slug_registry_id


async def create_discovery_run(session: AsyncSession, user_id: str) -> DiscoveryRun:
    active = await session.execute(
        select(DiscoveryRun).where(
            DiscoveryRun.user_id == user_id,
            DiscoveryRun.status == DiscoveryRunStatus.running,
        )
    )
    if active.scalar_one_or_none():
        raise ValueError("A discovery run is already in progress")

    run = DiscoveryRun(user_id=user_id)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_discovery_run(session: AsyncSession, run_id: str) -> DiscoveryRun | None:
    return await session.get(DiscoveryRun, run_id)


async def list_discovery_runs(session: AsyncSession, user_id: str, limit: int = 20) -> list[DiscoveryRun]:
    result = await session.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.user_id == user_id)
        .order_by(DiscoveryRun.triggered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_run_candidates(session: AsyncSession, run_id: str) -> list[CandidateSource]:
    result = await session.execute(
        select(CandidateSource)
        .where(CandidateSource.discovery_run_id == run_id)
        .order_by(
            CandidateSource.evaluation_verdict,
            CandidateSource.confidence.desc(),
        )
    )
    rows = list(result.scalars().all())
    verdict_order = {
        CandidateEvaluationVerdict.recurring_source: 0,
        CandidateEvaluationVerdict.unclear: 1,
        CandidateEvaluationVerdict.one_off_page: 2,
    }
    rows.sort(key=lambda r: (verdict_order.get(r.evaluation_verdict, 9), -r.confidence))
    return rows


async def get_candidate(session: AsyncSession, candidate_id: str) -> CandidateSource | None:
    return await session.get(CandidateSource, candidate_id)


async def reject_candidate(session: AsyncSession, candidate_id: str) -> CandidateSource:
    candidate = await session.get(CandidateSource, candidate_id)
    if not candidate:
        raise ValueError("Candidate not found")
    candidate.status = CandidateSourceStatus.rejected
    candidate.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(candidate)
    return candidate


def build_approval_defaults(candidate: CandidateSource) -> SourceApprovalPayload:
    guessed = candidate.guessed_parser_config or {}
    discover = guessed.get("discover") or {}
    url = candidate.discovered_url
    if discover.get("feed_urls"):
        url = discover["feed_urls"][0]
    source_type = "rss" if discover.get("kind") == "rss" or discover.get("feed_urls") else "html"
    name = candidate.domain.replace(".", " ").title()
    return SourceApprovalPayload(
        registry_id=_slug_registry_id(name, candidate.domain),
        name=name,
        url=url,
        source_type=source_type,
        fetch_mode="http",
        parser_config=guessed,
    )


async def approve_candidate(
    session: AsyncSession,
    candidate_id: str,
    payload: SourceApprovalPayload,
    user_id: str,
) -> dict:
    candidate = await session.get(CandidateSource, candidate_id)
    if not candidate:
        raise ValueError("Candidate not found")
    return await promote_candidate_source(session, candidate, payload, user_id)
