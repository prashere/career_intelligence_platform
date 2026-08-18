"""Sync L2 structured profile into the runtime UserProfile table."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserProfile
from app.services.profile_intake import load_structured_profile, validate_structured_profile
from app.services.profile_pipeline import structured_profile_to_user_fields


async def sync_user_profile_from_structured(
    session: AsyncSession,
    data: dict | None = None,
    *,
    user: User | None = None,
    profile: UserProfile | None = None,
    commit: bool = True,
) -> UserProfile | None:
    """Update or create a user profile from structured-profile.json."""
    raw = data if data is not None else load_structured_profile()
    if not raw:
        return None

    structured, errors = validate_structured_profile(raw)
    if structured is None:
        raise ValueError(f"Invalid structured profile: {'; '.join(errors)}")

    fields = structured_profile_to_user_fields(structured)

    if profile is None and user is not None:
        result = await session.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        profile = result.scalar_one_or_none()

    if profile is None:
        if user is None:
            raise ValueError("No user profile to sync into — sign in or pass --email")
        profile = UserProfile(user_id=user.id, name=fields["name"])
        session.add(profile)

    for key, value in fields.items():
        setattr(profile, key, value)

    if commit:
        await session.commit()
        await session.refresh(profile)
    else:
        await session.flush()
    return profile


async def sync_user_profile_from_path(
    session: AsyncSession,
    path: Path,
    *,
    user: User | None = None,
) -> UserProfile | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return await sync_user_profile_from_structured(session, raw, user=user)
