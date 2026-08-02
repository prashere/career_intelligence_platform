#!/usr/bin/env python3
"""Sync structured-profile.json into the user_profiles table for ranking.

Usage:
    python scripts/sync_profile_to_db.py
    python scripts/sync_profile_to_db.py path/to/structured-profile.json
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session, engine, Base
from app.services.profile_intake import load_structured_profile
from app.services.profile_sync import sync_user_profile_from_structured


async def main_async(path: Path | None) -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    raw = None
    if path:
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = load_structured_profile()

    if not raw:
        print("Error: structured-profile.json not found. Run merge_profile.py first.")
        return 1

    async with async_session() as session:
        user = await sync_user_profile_from_structured(session, raw)
        if not user:
            print("Error: sync failed.")
            return 1

    print(f"Synced user profile: {user.name}")
    print(f"  Target universities: {', '.join(user.target_universities or []) or '—'}")
    constraints = user.constraints or {}
    print(f"  Discovery mode: {constraints.get('discovery_mode', 'open')}")
    print(f"  Manual channels: {', '.join(constraints.get('manual_channels') or []) or '—'}")
    return 0


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python scripts/sync_profile_to_db.py [structured-profile.json]")
        return 1

    path = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    if path and not path.exists():
        print(f"Error: file not found: {path}")
        return 1

    return asyncio.run(main_async(path))


if __name__ == "__main__":
    raise SystemExit(main())
