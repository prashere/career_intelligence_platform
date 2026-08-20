"""Default Celery beat jobs and DB seed helpers."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleKind, SchedulerCategory, SchedulerJob

# Long-form hover / admin help text (also mirrored in docs/background-schedulers.md).
SCHEDULER_INFO_DETAILS: dict[str, str] = {
    "ingestion-sync-hourly": (
        "Runs the full ingestion maintenance cycle every hour. "
        "Fetches RSS/HTML listings from every active opportunity source through the ingestion pipeline "
        "(discover → relevance gate → persist opportunities). "
        "Then normalizes any backlog raw documents, indexes opportunities missing RAG chunks, "
        "and deactivates sources that exceeded the consecutive failure threshold. "
        "Replaces the former separate fetch, normalize, and health-check jobs."
    ),
    "rerank-daily": (
        "Recomputes fit scores and explanations for every user profile against the current opportunity "
        "catalog. Updates UserOpportunity rows so the dashboard feed order and match badges reflect "
        "compiled filter_config and ranking weights. Runs before most users open the app."
    ),
    "notifications-daily": (
        "Morning notification batch for all users. Sends the daily digest (new strong/moderate matches "
        "from the last 24 hours) and deadline reminders (7, 3, and 1 days before application deadlines "
        "for saved or in-progress opportunities). Creates in-app notifications and attempts email delivery "
        "when email is configured."
    ),
    "staleness-check-weekly": (
        "Weekly quality pass on stored opportunity URLs. Re-fetches pages that have not been seen recently "
        "or verified in a long time, detects closed/expired listings, and marks opportunities as stale so "
        "they drop out of the default feed."
    ),
}

DEPRECATED_SCHEDULER_KEYS: frozenset[str] = frozenset(
    {
        "fetch-all-sources-hourly",
        "normalize-every-30-min",
        "source-health-hourly",
        "daily-digest-8am",
        "deadline-reminders-9am",
    }
)

SYNC_FIELDS = (
    "name",
    "description",
    "task_path",
    "schedule_kind",
    "cron_minute",
    "cron_hour",
    "cron_day_of_week",
    "interval_seconds",
    "is_enabled",
    "category",
)

DEFAULT_SCHEDULER_JOBS: list[dict] = [
    {
        "key": "ingestion-sync-hourly",
        "name": "Ingestion sync",
        "description": "Fetch sources, normalize backlog, index search, and check source health.",
        "task_path": "app.workers.ingest.tasks.ingestion_sync_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "*",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.ingest,
    },
    {
        "key": "notifications-daily",
        "name": "Daily notifications",
        "description": "Morning digest and deadline reminders for all users.",
        "task_path": "app.workers.notifications.tasks.notifications_daily_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "8",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.notify,
    },
    {
        "key": "rerank-daily",
        "name": "Re-rank opportunities",
        "description": "Refresh fit scores for all users against the opportunity index.",
        "task_path": "app.workers.ingest.tasks.rerank_all_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "6",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.rank,
    },
    {
        "key": "staleness-check-weekly",
        "name": "Staleness check",
        "description": "Re-fetch opportunity pages and mark stale listings.",
        "task_path": "app.workers.ingest.tasks.staleness_check_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "3",
        "cron_day_of_week": "0",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.ingest,
    },
]


def scheduler_info_detail(key: str) -> str | None:
    return SCHEDULER_INFO_DETAILS.get(key)


async def seed_scheduler_jobs(session: AsyncSession, *, reset_defaults: bool = False) -> int:
    """Insert missing jobs, remove deprecated merged jobs; optionally reset all fields to defaults."""
    changed = 0
    for spec in DEFAULT_SCHEDULER_JOBS:
        result = await session.execute(
            select(SchedulerJob).where(SchedulerJob.key == spec["key"])
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(SchedulerJob(**spec))
            changed += 1
        elif reset_defaults:
            for field in SYNC_FIELDS:
                setattr(row, field, spec[field])
            changed += 1

    if DEPRECATED_SCHEDULER_KEYS:
        del_result = await session.execute(
            delete(SchedulerJob).where(SchedulerJob.key.in_(DEPRECATED_SCHEDULER_KEYS))
        )
        if del_result.rowcount:
            changed += del_result.rowcount

    if changed:
        await session.commit()
    return changed


def build_celery_schedule_entry(job: SchedulerJob) -> dict:
    from celery.schedules import crontab, schedule as interval_schedule

    if job.schedule_kind == ScheduleKind.interval:
        seconds = job.interval_seconds or 3600
        sched = interval_schedule(run_every=seconds)
    else:
        sched = crontab(
            minute=job.cron_minute or "*",
            hour=job.cron_hour or "*",
            day_of_week=job.cron_day_of_week or "*",
        )

    return {"task": job.task_path, "schedule": sched}
