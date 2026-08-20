"""Merge legacy scheduler jobs into consolidated background tasks."""

from typing import Sequence, Union

from alembic import op

revision: str = "014_scheduler_merge"
down_revision: Union[str, None] = "013_source_discovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPRECATED_KEYS = (
    "fetch-all-sources-hourly",
    "normalize-every-30-min",
    "source-health-hourly",
    "daily-digest-8am",
    "deadline-reminders-9am",
)


def upgrade() -> None:
    for key in DEPRECATED_KEYS:
        op.execute(f"DELETE FROM scheduler_jobs WHERE key = '{key}'")

    op.execute(
        """
        INSERT INTO scheduler_jobs (
            id, key, name, description, task_path, schedule_kind,
            cron_minute, cron_hour, cron_day_of_week, interval_seconds,
            is_enabled, category, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            'ingestion-sync-hourly',
            'Ingestion sync',
            'Fetch sources, normalize backlog, index search, and check source health.',
            'app.workers.ingest.tasks.ingestion_sync_task',
            'cron'::schedulekind,
            '0', '*', '*', NULL,
            true,
            'ingest'::schedulercategory,
            NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduler_jobs WHERE key = 'ingestion-sync-hourly'
        )
        """
    )

    op.execute(
        """
        INSERT INTO scheduler_jobs (
            id, key, name, description, task_path, schedule_kind,
            cron_minute, cron_hour, cron_day_of_week, interval_seconds,
            is_enabled, category, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            'notifications-daily',
            'Daily notifications',
            'Morning digest and deadline reminders for all users.',
            'app.workers.notifications.tasks.notifications_daily_task',
            'cron'::schedulekind,
            '0', '8', '*', NULL,
            true,
            'notify'::schedulercategory,
            NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduler_jobs WHERE key = 'notifications-daily'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM scheduler_jobs WHERE key IN ('ingestion-sync-hourly', 'notifications-daily')"
    )
