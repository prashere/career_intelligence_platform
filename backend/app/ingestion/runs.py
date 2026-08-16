"""Ingestion run queries for admin API."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Opportunity, OpportunitySource
from app.models.ingestion import IngestionRun, IngestionTraceEvent, RejectedItem


async def source_health(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(OpportunitySource).order_by(OpportunitySource.name))
    sources = result.scalars().all()
    opp_counts = dict(
        (await session.execute(select(Opportunity.source_id, func.count()).group_by(Opportunity.source_id))).all()
    )
    out = []
    for src in sources:
        out.append(
            {
                "id": src.id,
                "name": src.name,
                "registry_id": src.registry_id or (src.parser_config or {}).get("registry_id"),
                "fetch_mode": src.fetch_mode,
                "is_active": src.is_active,
                "last_fetched_at": src.last_fetched_at,
                "next_fetch_at": src.next_fetch_at,
                "consecutive_failures": src.consecutive_failures,
                "last_error": src.last_error,
                "opportunity_count": opp_counts.get(src.id, 0),
            }
        )
    return out


async def recent_runs(session: AsyncSession, limit: int = 20) -> list[IngestionRun]:
    result = await session.execute(
        select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(limit)
    )
    return list(result.scalars().all())


async def recent_rejected(session: AsyncSession, limit: int = 50) -> list[RejectedItem]:
    result = await session.execute(
        select(RejectedItem).order_by(desc(RejectedItem.created_at)).limit(limit)
    )
    return list(result.scalars().all())


async def get_run_detail(session: AsyncSession, run_id: str) -> dict[str, Any] | None:
    run = await session.get(IngestionRun, run_id)
    if not run:
        return None

    rejected = (
        await session.execute(
            select(RejectedItem)
            .where(RejectedItem.run_id == run_id)
            .order_by(RejectedItem.created_at)
            .limit(200)
        )
    ).scalars().all()

    trace = (
        await session.execute(
            select(IngestionTraceEvent)
            .where(IngestionTraceEvent.run_id == run_id)
            .order_by(IngestionTraceEvent.seq)
        )
    ).scalars().all()

    source_name: str | None = None
    if run.source_id:
        src = await session.get(OpportunitySource, run.source_id)
        source_name = src.name if src else None

    return {
        "run": run,
        "source_name": source_name,
        "rejected_items": list(rejected),
        "trace_events": list(trace),
    }
