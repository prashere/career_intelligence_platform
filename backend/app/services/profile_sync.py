"""Sync L2 structured profile into the runtime UserProfile table."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserProfile
from app.services.profile_intake import load_structured_profile, validate_structured_profile
from app.services.profile_pipeline import structured_profile_to_user_fields


async def sync_user_profile_from_structured(
    session: AsyncSession,
    data: dict | None = None,
) -> UserProfile | None:
    """Update or create the default user profile from structured-profile.json."""
    raw = data if data is not None else load_structured_profile()
    if not raw:
        return None

    profile, errors = validate_structured_profile(raw)
    if profile is None:
        raise ValueError(f"Invalid structured profile: {'; '.join(errors)}")

    fields = structured_profile_to_user_fields(profile)

    result = await session.execute(select(UserProfile).limit(1))
    user = result.scalar_one_or_none()
    if not user:
        user = UserProfile(name=fields["name"])
        session.add(user)

    for key, value in fields.items():
        setattr(user, key, value)

    await session.commit()
    await session.refresh(user)
    return user


async def sync_user_profile_from_path(session: AsyncSession, path: Path) -> UserProfile | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return await sync_user_profile_from_structured(session, raw)
