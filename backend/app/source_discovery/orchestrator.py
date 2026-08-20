"""Orchestrate bounded source discovery runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models.ingestion import (
    CandidateEvaluationVerdict,
    CandidateSource,
    CandidateSourceStatus,
    DiscoveryRun,
    DiscoveryRunStage,
    DiscoveryRunStatus,
)
from app.source_discovery.constants import (
    HIGH_CONFIDENCE_THRESHOLD,
    MAX_CANDIDATES_EVALUATED,
    MAX_QUERIES_PER_ROUND,
    MAX_ROUNDS,
    TARGET_RECURRING_COUNT,
)
from app.source_discovery.evaluation import evaluate_candidate
from app.source_discovery.profile_context import load_discovery_profile_context
from app.source_discovery.queries import plan_search_queries
from app.source_discovery.search import load_excluded_domains, search_domain_candidates

logger = get_logger(__name__)


async def _count_strong_recurring(session: AsyncSession, run_id: str) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(CandidateSource)
        .where(
            CandidateSource.discovery_run_id == run_id,
            CandidateSource.evaluation_verdict == CandidateEvaluationVerdict.recurring_source,
            CandidateSource.confidence >= HIGH_CONFIDENCE_THRESHOLD,
        )
    )
    return int(result.scalar() or 0)


def _round_summary(meta_rounds: list[dict[str, Any]]) -> str:
    if not meta_rounds:
        return ""
    last = meta_rounds[-1]
    return (
        f"round {last.get('round')}: queries={len(last.get('queries', []))}, "
        f"found={last.get('found', 0)}, evaluated={last.get('evaluated', 0)}, "
        f"recurring={last.get('recurring_high_conf', 0)}"
    )


async def run_discovery(session: AsyncSession, run_id: str) -> None:
    run = await session.get(DiscoveryRun, run_id)
    if not run:
        raise ValueError(f"Discovery run {run_id} not found")

    profile_ctx = await load_discovery_profile_context(session, run.user_id)
    excluded = await load_excluded_domains(session)
    meta_rounds: list[dict[str, Any]] = []
    all_queries: list[dict[str, str]] = []
    evaluated_total = 0
    found_total = 0

    try:
        for round_num in range(1, MAX_ROUNDS + 1):
            if evaluated_total >= MAX_CANDIDATES_EVALUATED:
                break
            strong = await _count_strong_recurring(session, run_id)
            if strong >= TARGET_RECURRING_COUNT and round_num > 1:
                break

            run.current_stage = DiscoveryRunStage.searching
            prior = _round_summary(meta_rounds)
            plan = await plan_search_queries(profile_ctx, round_num=round_num, prior_summary=prior)
            round_queries = [q.model_dump() for q in plan.queries]
            all_queries.extend(round_queries)

            remaining_eval = MAX_CANDIDATES_EVALUATED - evaluated_total
            candidates = await search_domain_candidates(
                session,
                plan.queries,
                excluded=excluded,
                max_domains=remaining_eval,
            )
            found_total += len(candidates)
            for c in candidates:
                excluded.add(c.domain)

            run.current_stage = DiscoveryRunStage.evaluating
            round_evaluated = 0
            round_recurring = 0

            for candidate in candidates:
                if evaluated_total >= MAX_CANDIDATES_EVALUATED:
                    break
                evaluation = await evaluate_candidate(session, candidate, profile_ctx)
                verdict = CandidateEvaluationVerdict(evaluation.evaluation_verdict)
                row = CandidateSource(
                    discovery_run_id=run_id,
                    domain=candidate.domain,
                    discovered_url=candidate.discovered_url,
                    evaluation_verdict=verdict,
                    relevance_notes=evaluation.relevance_notes,
                    legitimacy_notes=evaluation.legitimacy_notes,
                    confidence=float(evaluation.confidence),
                    guessed_parser_config=evaluation.guessed_parser_config,
                    status=CandidateSourceStatus.pending_review,
                )
                session.add(row)
                evaluated_total += 1
                round_evaluated += 1
                if (
                    verdict == CandidateEvaluationVerdict.recurring_source
                    and evaluation.confidence >= HIGH_CONFIDENCE_THRESHOLD
                ):
                    round_recurring += 1

            await session.flush()
            meta_rounds.append(
                {
                    "round": round_num,
                    "focus": plan.round_focus,
                    "queries": round_queries,
                    "found": len(candidates),
                    "evaluated": round_evaluated,
                    "recurring_high_conf": round_recurring,
                }
            )

            strong = await _count_strong_recurring(session, run_id)
            if strong >= TARGET_RECURRING_COUNT:
                break

        run.queries_used = all_queries
        run.candidates_found = found_total
        run.candidates_evaluated = evaluated_total
        run.current_stage = DiscoveryRunStage.done
        run.status = DiscoveryRunStatus.completed
        run.finished_at = datetime.now(timezone.utc)
        run.meta = {"rounds": meta_rounds}
        await session.commit()
    except Exception as exc:
        logger.exception("discovery_run_failed", run_id=run_id, error=str(exc))
        run.status = DiscoveryRunStatus.failed
        run.current_stage = DiscoveryRunStage.done
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        run.meta = {"rounds": meta_rounds, "error": str(exc)}
        await session.commit()
        raise
