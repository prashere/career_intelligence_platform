"""Application startup helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User, UserRole
from app.services.auth import register_user
from app.services.schedulers import seed_scheduler_jobs


async def bootstrap_admin_if_needed(session: AsyncSession) -> None:
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    count = await session.execute(select(func.count()).select_from(User))
    if count.scalar_one() > 0:
        return

    await register_user(
        session,
        email=settings.bootstrap_admin_email,
        password=settings.bootstrap_admin_password,
        name="Administrator",
        role=UserRole.administrator,
    )


async def run_startup_tasks(session: AsyncSession) -> None:
    await bootstrap_admin_if_needed(session)
    await seed_scheduler_jobs(session)
