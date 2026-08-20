"""Tests for Celery scheduler tasks and job seeding."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import SchedulerCategory, SchedulerJob, ScheduleKind
from app.services.schedulers import (
    DEPRECATED_SCHEDULER_KEYS,
    DEFAULT_SCHEDULER_JOBS,
    build_celery_schedule_entry,
    scheduler_info_detail,
    seed_scheduler_jobs,
)


def _mock_async_session(session: AsyncMock):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def test_scheduler_info_detail_known_keys():
    for spec in DEFAULT_SCHEDULER_JOBS:
        detail = scheduler_info_detail(spec["key"])
        assert detail and len(detail) > 20


def test_build_celery_schedule_entry_cron():
    job = SchedulerJob(
        key="test",
        name="Test",
        description="d",
        task_path="app.workers.ingest.tasks.ingestion_sync_task",
        schedule_kind=ScheduleKind.cron,
        cron_minute="0",
        cron_hour="8",
        cron_day_of_week="*",
        category=SchedulerCategory.ingest,
    )
    entry = build_celery_schedule_entry(job)
    assert entry["task"] == job.task_path
    assert entry["schedule"] is not None


def test_seed_scheduler_jobs_inserts_and_removes_deprecated():
    session = AsyncMock()
    legacy_rows = [
        SchedulerJob(
            key=key,
            name="Legacy",
            description="old",
            task_path="app.workers.ingest.tasks.fetch_all_sources_task",
            schedule_kind=ScheduleKind.cron,
            cron_minute="0",
            cron_hour="*",
            category=SchedulerCategory.ingest,
        )
        for key in DEPRECATED_SCHEDULER_KEYS
    ]

    async def fake_execute(stmt):
        result = MagicMock()
        key_filter = getattr(stmt, "whereclause", None)
        if key_filter is not None and "key" in str(stmt):
            result.scalar_one_or_none = MagicMock(return_value=None)
        else:
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=legacy_rows)))
        result.rowcount = len(DEPRECATED_SCHEDULER_KEYS)
        return result

    session.execute = fake_execute
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _run():
        changed = await seed_scheduler_jobs(session, reset_defaults=True)
        assert changed >= len(DEFAULT_SCHEDULER_JOBS)
        assert session.add.call_count >= len(DEFAULT_SCHEDULER_JOBS)

    asyncio.run(_run())


def test_ingestion_sync_task_orchestration():
    from app.workers.ingest.tasks import ingestion_sync_task

    session = AsyncMock()
    session.commit = AsyncMock()

    with patch(
        "app.workers.ingest.tasks.async_session",
        return_value=_mock_async_session(session),
    ), patch(
        "app.workers.ingest.tasks._fetch_all_active_sources",
        new=AsyncMock(return_value=[{"source": "Test", "created": 1}]),
    ), patch(
        "app.workers.ingest.tasks._normalize_and_index",
        new=AsyncMock(return_value={"created": 0, "skipped": 0, "indexed": 2}),
    ), patch(
        "app.workers.ingest.tasks._source_health_check",
        new=AsyncMock(return_value={"deactivated": 0, "sources": []}),
    ), patch(
        "app.workers.ingest.tasks.touch_scheduler_run",
        new=AsyncMock(),
    ):
        result = ingestion_sync_task()

    assert result["sources_fetched"] == 1
    assert result["normalize"]["indexed"] == 2
    assert result["health"]["deactivated"] == 0
    session.commit.assert_awaited_once()


def test_notifications_daily_task():
    from app.workers.notifications.tasks import notifications_daily_task

    profile = MagicMock(id="profile-1")
    session = AsyncMock()
    session.commit = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[profile])))
    session.execute = AsyncMock(return_value=exec_result)

    with patch(
        "app.workers.notifications.tasks.async_session",
        return_value=_mock_async_session(session),
    ), patch(
        "app.workers.notifications.tasks.send_daily_digest",
        new=AsyncMock(return_value={"sent": False}),
    ), patch(
        "app.workers.notifications.tasks.send_deadline_reminders",
        new=AsyncMock(return_value={"sent_count": 0}),
    ), patch(
        "app.workers.notifications.tasks.touch_scheduler_run",
        new=AsyncMock(),
    ):
        outcomes = notifications_daily_task()

    assert len(outcomes) == 1
    assert outcomes[0]["user_id"] == "profile-1"
    assert "digest" in outcomes[0]
    assert "deadline_reminders" in outcomes[0]


def test_rerank_all_task():
    from app.workers.ingest.tasks import rerank_all_task

    profile = MagicMock(id="profile-1")
    session = AsyncMock()
    session.commit = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[profile])))
    session.execute = AsyncMock(return_value=exec_result)

    with patch(
        "app.workers.ingest.tasks.async_session",
        return_value=_mock_async_session(session),
    ), patch(
        "app.workers.ingest.tasks.rank_opportunities_for_user",
        new=AsyncMock(return_value=3),
    ), patch(
        "app.workers.ingest.tasks.touch_scheduler_run",
        new=AsyncMock(),
    ):
        result = rerank_all_task()

    assert result["ranked"] == 3


def test_staleness_check_task():
    from app.workers.ingest.tasks import staleness_check_task

    session = AsyncMock()
    session.commit = AsyncMock()

    with patch(
        "app.workers.ingest.tasks.async_session",
        return_value=_mock_async_session(session),
    ), patch(
        "app.services.staleness.run_staleness_batch",
        new=AsyncMock(return_value={"checked": 5, "marked_stale": 1}),
    ), patch(
        "app.workers.ingest.tasks.touch_scheduler_run",
        new=AsyncMock(),
    ):
        result = staleness_check_task()

    assert result["checked"] == 5
    assert result["marked_stale"] == 1


def test_touch_scheduler_run_updates_timestamp():
    from app.workers.scheduler_hooks import touch_scheduler_run

    job = SchedulerJob(
        key="ingestion-sync-hourly",
        name="Ingestion sync",
        description="d",
        task_path="app.workers.ingest.tasks.ingestion_sync_task",
        schedule_kind=ScheduleKind.cron,
        cron_minute="0",
        cron_hour="*",
        category=SchedulerCategory.ingest,
    )
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=job)
    session.execute = AsyncMock(return_value=exec_result)
    session.flush = AsyncMock()

    asyncio.run(touch_scheduler_run(session, "ingestion-sync-hourly"))
    assert job.last_run_at is not None
    session.flush.assert_awaited_once()
