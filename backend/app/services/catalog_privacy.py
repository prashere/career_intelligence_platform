"""Keep the opportunity feed from leaking listings that are not this user's.

Demo / leftover seed rows must never appear after someone has a real profile.
Accounts that have not finished profile setup see no catalog at all.
"""

from __future__ import annotations

from sqlalchemy import not_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models import Opportunity

# Hypothetical demo listings use this url_hash prefix. Ingested rows never do.
FICTIONAL_DEMO_URL_HASH_PREFIX = "demo-"


def exclude_fictional_demo(query: Select) -> Select:
    return query.where(
        not_(Opportunity.url_hash.startswith(FICTIONAL_DEMO_URL_HASH_PREFIX))
    )


def is_fictional_demo_hash(url_hash: str | None) -> bool:
    return bool(url_hash) and url_hash.startswith(FICTIONAL_DEMO_URL_HASH_PREFIX)


async def user_has_matching_profile(session: AsyncSession, user_id: str) -> bool:
    from app.services.profile_storage import load_structured_profile

    data = await load_structured_profile(session, user_id)
    return bool(data)
