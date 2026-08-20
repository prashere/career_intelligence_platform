import asyncio

from app.database import async_session
from app.logging_config import get_logger
from app.source_discovery.orchestrator import run_discovery
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.source_discovery.tasks.run_discovery_task")
def run_discovery_task(run_id: str):
    async def _inner():
        async with async_session() as session:
            await run_discovery(session, run_id)

    try:
        return _run_async(_inner())
    except Exception as exc:
        logger.exception("discovery_task_failed", run_id=run_id, error=str(exc))
        return {"ok": False, "error": str(exc)}
