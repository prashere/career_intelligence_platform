"""Celery beat scheduler that reads job definitions from PostgreSQL."""

from __future__ import annotations

import time

from celery.beat import PersistentScheduler, ScheduleEntry
from celery.schedules import crontab, schedule as interval_schedule
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ScheduleKind, SchedulerJob
from app.services.schedulers import build_celery_schedule_entry


class DatabaseScheduler(PersistentScheduler):
    """Reload enabled scheduler_jobs from the database periodically."""

    SYNC_INTERVAL_SECONDS = 30

    def __init__(self, *args, **kwargs):
        self._last_db_sync = 0.0
        super().__init__(*args, **kwargs)

    def setup_schedule(self):
        super().setup_schedule()
        self.update_from_database()

    def tick(self, *args, **kwargs):
        self._maybe_sync_from_database()
        return super().tick(*args, **kwargs)

    def _maybe_sync_from_database(self) -> None:
        now = time.time()
        if now - self._last_db_sync < self.SYNC_INTERVAL_SECONDS:
            return
        self._last_db_sync = now
        self.update_from_database()

    def update_from_database(self) -> None:
        engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
        schedule: dict = {}

        with Session(engine) as session:
            jobs = session.execute(select(SchedulerJob)).scalars().all()
            for job in jobs:
                if not job.is_enabled:
                    continue
                entry = build_celery_schedule_entry(job)
                schedule[job.key] = ScheduleEntry(
                    name=job.key,
                    task=entry["task"],
                    schedule=entry["schedule"],
                    options={},
                )

        self.schedule.clear()
        self.schedule.update(schedule)
        self._last_db_sync = time.time()

    @staticmethod
    def _build_schedule(job: SchedulerJob):
        if job.schedule_kind == ScheduleKind.interval:
            seconds = job.interval_seconds or 3600
            return interval_schedule(run_every=seconds)
        return crontab(
            minute=job.cron_minute or "*",
            hour=job.cron_hour or "*",
            day_of_week=job.cron_day_of_week or "*",
        )
