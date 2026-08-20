"""Helpers for scheduled Celery tasks (last-run timestamps)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SchedulerJob

# Maps Celery task name → scheduler_jobs.key
TASK_TO_SCHEDULER_KEY: dict[str, str] = {
    "app.workers.ingest.tasks.ingestion_sync_task": "ingestion-sync-hourly",
    "app.workers.ingest.tasks.rerank_all_task": "rerank-daily",
    "app.workers.ingest.tasks.staleness_check_task": "staleness-check-weekly",
    "app.workers.notifications.tasks.notifications_daily_task": "notifications-daily",
}


async def touch_scheduler_run(session: AsyncSession, job_key: str) -> None:
    result = await session.execute(select(SchedulerJob).where(SchedulerJob.key == job_key))
    job = result.scalar_one_or_none()
    if job:
        job.last_run_at = datetime.now(timezone.utc)
        await session.flush()
