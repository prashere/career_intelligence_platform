"""Track per-source ingest outcomes and feed them back into aggregator scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpportunitySource


def compute_admit_rate(admitted: int, discovered: int) -> float | None:
    if discovered <= 0:
        return None
    return round(admitted / discovered, 4)


def merge_outcome_stats(existing: dict[str, Any] | None, run_stats: dict[str, Any]) -> dict[str, Any]:
    """Accumulate run counters into rolling source outcome stats."""
    base = dict(existing or {})
    discovered = int(run_stats.get("discovered") or 0)
    admitted = int(run_stats.get("admitted") or 0)
    rejected = int(
        run_stats.get("rejected_at_discover", 0) + run_stats.get("rejected_after_detail", 0)
    )
    created = int(run_stats.get("created") or 0)
    updated = int(run_stats.get("updated") or 0)

    base["runs"] = int(base.get("runs") or 0) + 1
    base["discovered_total"] = int(base.get("discovered_total") or 0) + discovered
    base["admitted_total"] = int(base.get("admitted_total") or 0) + admitted
    base["rejected_total"] = int(base.get("rejected_total") or 0) + rejected
    base["created_total"] = int(base.get("created_total") or 0) + created
    base["updated_total"] = int(base.get("updated_total") or 0) + updated
    base["admit_rate"] = compute_admit_rate(base["admitted_total"], base["discovered_total"])
    base["persist_rate"] = (
        round((base["created_total"] + base["updated_total"]) / base["discovered_total"], 4)
        if base["discovered_total"] > 0
        else None
    )
    base["last_run_at"] = datetime.now(timezone.utc).isoformat()
    base["last_run"] = {
        "discovered": discovered,
        "admitted": admitted,
        "rejected": rejected,
        "created": created,
        "updated": updated,
        "deferred_investigate": int(run_stats.get("deferred_investigate") or 0),
    }
    return base


async def update_source_outcome_stats(
    session: AsyncSession,
    source: OpportunitySource,
    run_stats: dict[str, Any],
    *,
    commit: bool = True,
) -> dict[str, Any]:
    merged = merge_outcome_stats(source.outcome_stats, run_stats)
    source.outcome_stats = merged
    if commit:
        await session.commit()
    else:
        await session.flush()
    return merged


async def load_registry_outcome_stats(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Map registry_id → outcome_stats for aggregator scoring at profile prefill."""
    result = await session.execute(select(OpportunitySource))
    out: dict[str, dict[str, Any]] = {}
    for source in result.scalars().all():
        if source.registry_id and source.outcome_stats:
            out[source.registry_id] = source.outcome_stats
    return out


def outcome_bonus_for_scoring(stats: dict[str, Any] | None) -> tuple[int, list[str]]:
    """Translate rolling admit rate into aggregator score bonus (0–10 points)."""
    if not stats:
        return 0, []
    admit_rate = stats.get("admit_rate")
    if admit_rate is None:
        return 0, []
    reasons: list[str] = []
    bonus = 0
    if admit_rate >= 0.35:
        bonus += 8
        reasons.append(f"high_admit_rate:{admit_rate:.2f}")
    elif admit_rate >= 0.20:
        bonus += 4
        reasons.append(f"moderate_admit_rate:{admit_rate:.2f}")
    elif admit_rate < 0.08 and int(stats.get("runs") or 0) >= 3:
        bonus -= 6
        reasons.append(f"low_admit_rate:{admit_rate:.2f}")
    return bonus, reasons


def effective_authority(static_authority: float, stats: dict[str, Any] | None) -> float:
    """Blend registry authority with empirical admit rate for display."""
    base = float(static_authority or 0.5)
    if not stats or stats.get("admit_rate") is None:
        return base
    empirical = min(1.0, max(0.0, float(stats["admit_rate"]) * 2.5))
    return round(0.6 * base + 0.4 * empirical, 3)
