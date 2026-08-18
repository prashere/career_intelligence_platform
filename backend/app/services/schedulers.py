"""Default Celery beat jobs and DB seed helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleKind, SchedulerCategory, SchedulerJob

DEFAULT_SCHEDULER_JOBS: list[dict] = [
    {
        "key": "fetch-all-sources-hourly",
        "name": "Fetch all sources",
        "description": "Pull RSS/HTML listings from active opportunity sources.",
        "task_path": "app.workers.ingest.tasks.fetch_all_sources_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "*",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.ingest,
    },
    {
        "key": "normalize-every-30-min",
        "name": "Normalize raw documents",
        "description": "Convert fetched raw documents into opportunity records.",
        "task_path": "app.workers.ingest.tasks.normalize_all_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "*/30",
        "cron_hour": "*",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.ingest,
    },
    {
        "key": "daily-digest-8am",
        "name": "Daily digest email",
        "description": "Send morning digest of new matches and deadlines.",
        "task_path": "app.workers.notifications.tasks.send_daily_digest_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "8",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.notify,
    },
    {
        "key": "deadline-reminders-9am",
        "name": "Deadline reminders",
        "description": "Notify users about upcoming application deadlines.",
        "task_path": "app.workers.notifications.tasks.send_deadline_reminders_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "0",
        "cron_hour": "9",
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
        "key": "source-health-hourly",
        "name": "Source health check",
        "description": "Auto-deactivate sources that exceeded consecutive failure threshold.",
        "task_path": "app.workers.ingest.tasks.source_health_check_task",
        "schedule_kind": ScheduleKind.cron,
        "cron_minute": "30",
        "cron_hour": "*",
        "cron_day_of_week": "*",
        "interval_seconds": None,
        "is_enabled": True,
        "category": SchedulerCategory.ingest,
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


async def seed_scheduler_jobs(session: AsyncSession) -> int:
    """Insert default scheduler rows and sync any missing job definitions."""
    added = 0
    for spec in DEFAULT_SCHEDULER_JOBS:
        result = await session.execute(
            select(SchedulerJob).where(SchedulerJob.key == spec["key"])
        )
        if result.scalar_one_or_none() is None:
            session.add(SchedulerJob(**spec))
            added += 1
    if added:
        await session.commit()
    return added


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
