import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models import OpportunitySource, UserProfile
from app.services.ingestion import fetch_source, normalize_raw_documents
from app.services.ranking import rank_opportunities_for_user
from app.rag.retriever import index_opportunity
from app.workers.celery_app import celery_app


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.ingest.tasks.fetch_all_sources_task")
def fetch_all_sources_task():
    async def _fetch():
        async with async_session() as session:
            result = await session.execute(select(OpportunitySource).where(OpportunitySource.is_active.is_(True)))
            sources = result.scalars().all()
            results = []
            for source in sources:
                r = await fetch_source(session, source.id)
                results.append({"source": source.name, **r})
            return results

    return run_async(_fetch())


@celery_app.task(name="app.workers.ingest.tasks.normalize_all_task")
def normalize_all_task():
    async def _normalize():
        async with async_session() as session:
            return await normalize_raw_documents(session, limit=200)

    norm_result = run_async(_normalize())

    async def _index_new():
        from app.models import Opportunity, DocumentChunk
        async with async_session() as session:
            result = await session.execute(select(Opportunity))
            for opp in result.scalars().all():
                chunks = await session.execute(
                    select(DocumentChunk).where(DocumentChunk.opportunity_id == opp.id)
                )
                if not chunks.scalar_one_or_none():
                    await index_opportunity(session, opp.id)

    run_async(_index_new())
    return norm_result


@celery_app.task(name="app.workers.ingest.tasks.fetch_source_task")
def fetch_source_task(source_id: str):
    async def _fetch():
        async with async_session() as session:
            return await fetch_source(session, source_id)

    return run_async(_fetch())


@celery_app.task(name="app.workers.ingest.tasks.rerank_all_task")
def rerank_all_task():
    async def _rerank():
        async with async_session() as session:
            result = await session.execute(select(UserProfile))
            users = result.scalars().all()
            total = 0
            for user in users:
                total += await rank_opportunities_for_user(session, user.id)
            return {"ranked": total}

    return run_async(_rerank())
