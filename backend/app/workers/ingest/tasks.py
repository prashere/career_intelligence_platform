import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models import Opportunity, OpportunitySource, UserProfile, DocumentChunk
from app.services.ingestion import fetch_source, normalize_raw_documents
from app.services.ranking import rank_opportunities_for_user
from app.rag.retriever import index_opportunity
from app.workers.celery_app import celery_app
from app.workers.scheduler_hooks import touch_scheduler_run


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fetch_all_active_sources(session) -> list[dict]:
    result = await session.execute(
        select(OpportunitySource).where(OpportunitySource.is_active.is_(True))
    )
    sources = result.scalars().all()
    results = []
    for source in sources:
        r = await fetch_source(session, source.id)
        results.append({"source": source.name, **r})
    return results


async def _normalize_and_index(session) -> dict:
    norm_result = await normalize_raw_documents(session, limit=200)

    indexed = 0
    opp_result = await session.execute(select(Opportunity))
    for opp in opp_result.scalars().all():
        chunks = await session.execute(
            select(DocumentChunk).where(DocumentChunk.opportunity_id == opp.id)
        )
        if not chunks.scalar_one_or_none():
            await index_opportunity(session, opp.id)
            indexed += 1

    return {**norm_result, "indexed": indexed}


async def _source_health_check(session) -> dict:
    from app.ingestion.source_health import deactivate_over_threshold_sources

    result = await session.execute(
        select(OpportunitySource).where(OpportunitySource.is_active.is_(True))
    )
    sources = result.scalars().all()
    deactivated = deactivate_over_threshold_sources(sources)
    await session.flush()
    return {"deactivated": len(deactivated), "sources": deactivated}


@celery_app.task(name="app.workers.ingest.tasks.ingestion_sync_task")
def ingestion_sync_task():
    """Scheduled ingestion: fetch all sources, normalize backlog, index RAG, health check."""

    async def _run():
        async with async_session() as session:
            fetch_results = await _fetch_all_active_sources(session)
            normalize_result = await _normalize_and_index(session)
            health_result = await _source_health_check(session)
            await touch_scheduler_run(session, "ingestion-sync-hourly")
            await session.commit()
            return {
                "sources_fetched": len(fetch_results),
                "fetch": fetch_results,
                "normalize": normalize_result,
                "health": health_result,
            }

    return run_async(_run())


@celery_app.task(name="app.workers.ingest.tasks.fetch_all_sources_task")
def fetch_all_sources_task():
    async def _fetch():
        async with async_session() as session:
            return await _fetch_all_active_sources(session)

    return run_async(_fetch())


@celery_app.task(name="app.workers.ingest.tasks.normalize_all_task")
def normalize_all_task():
    async def _normalize():
        async with async_session() as session:
            return await _normalize_and_index(session)

    return run_async(_normalize())


@celery_app.task(name="app.workers.ingest.tasks.fetch_source_task")
def fetch_source_task(source_id: str):
    async def _fetch():
        async with async_session() as session:
            return await fetch_source(session, source_id)

    return run_async(_fetch())


@celery_app.task(name="app.workers.ingest.tasks.dispatch_due_sources_task")
def dispatch_due_sources_task():
    """Enqueue fetch for sources past next_fetch_at."""

    async def _dispatch():
        from datetime import datetime, timezone

        async with async_session() as session:
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(OpportunitySource).where(
                    OpportunitySource.is_active.is_(True),
                    (OpportunitySource.next_fetch_at.is_(None)) | (OpportunitySource.next_fetch_at <= now),
                )
            )
            sources = result.scalars().all()
            queued = []
            for source in sources:
                fetch_source_task.delay(source.id)
                queued.append(source.name)
            return {"queued": len(queued), "sources": queued}

    return run_async(_dispatch())


@celery_app.task(name="app.workers.ingest.tasks.rerank_all_task")
def rerank_all_task():
    async def _rerank():
        async with async_session() as session:
            result = await session.execute(select(UserProfile))
            profiles = result.scalars().all()
            total = 0
            for profile in profiles:
                total += await rank_opportunities_for_user(session, profile.id)
            await touch_scheduler_run(session, "rerank-daily")
            await session.commit()
            return {"ranked": total}

    return run_async(_rerank())


@celery_app.task(name="app.workers.ingest.tasks.source_health_check_task")
def source_health_check_task():
    async def _check():
        async with async_session() as session:
            health = await _source_health_check(session)
            await session.commit()
            return health

    return run_async(_check())


@celery_app.task(name="app.workers.ingest.tasks.staleness_check_task")
def staleness_check_task():
    async def _check():
        from app.services.staleness import run_staleness_batch

        async with async_session() as session:
            result = await run_staleness_batch(session)
            await touch_scheduler_run(session, "staleness-check-weekly")
            await session.commit()
            return result

    return run_async(_check())
