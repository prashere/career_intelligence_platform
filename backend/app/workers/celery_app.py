from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "career_intelligence",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.ingest.tasks", "app.workers.notifications.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "fetch-all-sources-hourly": {
            "task": "app.workers.ingest.tasks.fetch_all_sources_task",
            "schedule": crontab(minute=0),
        },
        "normalize-every-30-min": {
            "task": "app.workers.ingest.tasks.normalize_all_task",
            "schedule": crontab(minute="*/30"),
        },
        "daily-digest-8am": {
            "task": "app.workers.notifications.tasks.send_daily_digest_task",
            "schedule": crontab(hour=8, minute=0),
        },
        "deadline-reminders-9am": {
            "task": "app.workers.notifications.tasks.send_deadline_reminders_task",
            "schedule": crontab(hour=9, minute=0),
        },
        "rerank-daily": {
            "task": "app.workers.ingest.tasks.rerank_all_task",
            "schedule": crontab(hour=6, minute=0),
        },
    },
)
