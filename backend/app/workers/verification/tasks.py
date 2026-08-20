"""Celery tasks for post-ingest opportunity verification."""

from __future__ import annotations

import asyncio

from app.database import async_session
from app.telemetry.langsmith import traceable
from app.verification.service import run_verification_batch, verify_opportunity
from app.workers.celery_app import celery_app


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@traceable(run_type="chain", name="verification_batch_celery", tags=["verification", "celery"])
async def _run_batch(limit: int) -> dict:
    async with async_session() as session:
        return await run_verification_batch(session, limit=limit)


@celery_app.task(name="app.workers.verification.tasks.verify_recent_opportunities_task")
def verify_recent_opportunities_task(limit: int = 25):
    """Process unverified opportunities that passed the relevance gate."""
    return run_async(_run_batch(limit))


@celery_app.task(name="app.workers.verification.tasks.verify_backfill_task")
def verify_backfill_task(limit: int = 100):
    """Verify unverified backlog (no recent-only cutoff)."""

    async def _run():
        async with async_session() as session:
            from app.verification.service import run_verification_backfill

            return await run_verification_backfill(session, limit=limit)

    return run_async(_run())


@celery_app.task(name="app.workers.verification.tasks.verify_opportunity_task")
def verify_opportunity_task(opportunity_id: str):
    async def _one():
        async with async_session() as session:
            return await verify_opportunity(session, opportunity_id)

    return run_async(_one())
