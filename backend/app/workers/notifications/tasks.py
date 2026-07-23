import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models import UserProfile
from app.services.notifications import send_daily_digest, send_deadline_reminders
from app.workers.celery_app import celery_app


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.notifications.tasks.send_daily_digest_task")
def send_daily_digest_task():
    async def _send():
        async with async_session() as session:
            result = await session.execute(select(UserProfile))
            users = result.scalars().all()
            outcomes = []
            for user in users:
                outcomes.append(await send_daily_digest(session, user.id))
            return outcomes

    return run_async(_send())


@celery_app.task(name="app.workers.notifications.tasks.send_deadline_reminders_task")
def send_deadline_reminders_task():
    async def _send():
        async with async_session() as session:
            result = await session.execute(select(UserProfile))
            users = result.scalars().all()
            outcomes = []
            for user in users:
                outcomes.append(await send_deadline_reminders(session, user.id))
            return outcomes

    return run_async(_send())
