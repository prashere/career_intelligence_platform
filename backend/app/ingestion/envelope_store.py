"""Persist and load platform interest envelope from DB / compiled profile."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.envelope import default_envelope
from app.models.ingestion import PlatformSettings
from app.services.profile_intake import compiled_dir

ENVELOPE_KEY = "interest_envelope"


def load_envelope_from_compiled() -> dict:
    path = compiled_dir() / "filter_config.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default_envelope()


async def get_platform_envelope(session: AsyncSession) -> dict:
    result = await session.execute(select(PlatformSettings).where(PlatformSettings.key == ENVELOPE_KEY))
    row = result.scalar_one_or_none()
    if row and row.value:
        return row.value
    env = load_envelope_from_compiled()
    session.add(PlatformSettings(key=ENVELOPE_KEY, value=env))
    await session.commit()
    return env


async def get_user_envelope(session: AsyncSession, user_id: str) -> dict | None:
    """Per-user filter envelope from compiled artifacts (preferred for profile ingest)."""
    from app.services.profile_storage import load_artifacts

    artifacts = await load_artifacts(session, user_id)
    if artifacts and artifacts.filter_config:
        return artifacts.filter_config
    return None


async def sync_platform_envelope(session: AsyncSession, envelope: dict, *, commit: bool = True) -> None:
    result = await session.execute(select(PlatformSettings).where(PlatformSettings.key == ENVELOPE_KEY))
    row = result.scalar_one_or_none()
    if row:
        row.value = envelope
    else:
        session.add(PlatformSettings(key=ENVELOPE_KEY, value=envelope))
    if commit:
        await session.commit()
    else:
        await session.flush()
