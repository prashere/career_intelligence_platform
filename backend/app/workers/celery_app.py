from celery import Celery

from app.config import settings
from app.logging_config import configure_logging
from app.telemetry.langsmith import configure_langsmith

configure_logging()
configure_langsmith()

celery_app = Celery(
    "career_intelligence",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.ingest.tasks",
        "app.workers.notifications.tasks",
        "app.workers.profile.tasks",
        "app.workers.verification.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_scheduler="app.workers.beat_scheduler:DatabaseScheduler",
)
