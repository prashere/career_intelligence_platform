#!/usr/bin/env python3
"""Seed opportunity_sources from compiled ingestion_sources.json.

URLs come from ingestion_sources.json (compiled from app/data/source-registry.yaml).

Usage:
    python scripts/seed_sources_from_profile.py
    python scripts/seed_sources_from_profile.py path/to/ingestion_sources.json
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session, engine, Base
from app.models import OpportunitySource, SourceType
from app.services.profile_intake import compiled_dir


async def seed_from_file(path: Path) -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    data = json.loads(path.read_text(encoding="utf-8"))
    sources = data.get("sources") or []
    if not sources:
        print("No sources in ingestion config.")
        return 1

    async with async_session() as session:
        added = 0
        updated = 0
        for entry in sources:
            url = entry["url"]
            result = await session.execute(
                select(OpportunitySource).where(OpportunitySource.url == url)
            )
            existing = result.scalar_one_or_none()
            source_type = SourceType.rss
            try:
                source_type = SourceType(entry.get("source_type", "rss"))
            except ValueError:
                source_type = SourceType.rss

            if existing:
                existing.name = entry["name"]
                existing.fetch_interval_minutes = entry.get("fetch_interval_minutes", 360)
                existing.is_active = entry.get("is_active", True)
                updated += 1
            else:
                session.add(
                    OpportunitySource(
                        name=entry["name"],
                        url=url,
                        source_type=source_type,
                        fetch_interval_minutes=entry.get("fetch_interval_minutes", 360),
                        is_active=entry.get("is_active", True),
                    )
                )
                added += 1

        await session.commit()

    print(f"Sources seeded: {added} added, {updated} updated ({len(sources)} total in config)")
    manual = data.get("manual_channels") or []
    if manual:
        print(f"Manual channels (not seeded — workflow only): {', '.join(manual)}")
    return 0


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python scripts/seed_sources_from_profile.py [ingestion_sources.json]")
        return 1

    path = Path(sys.argv[1]) if len(sys.argv) == 2 else compiled_dir() / "ingestion_sources.json"
    if not path.exists():
        print(f"Error: {path} not found. Run compile_profile.py first.")
        return 1

    return asyncio.run(seed_from_file(path))


if __name__ == "__main__":
    raise SystemExit(main())
