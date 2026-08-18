#!/usr/bin/env python3
"""Wipe profile, ingestion, and opportunity data; keep user accounts and scheduler jobs.

Does not modify config/sources/source-registry.yaml (registry YAML on disk).

Usage:
    python scripts/cleanup_pipeline_data.py          # dry-run counts
    python scripts/cleanup_pipeline_data.py --execute
    python scripts/cleanup_pipeline_data.py --execute --flush-redis
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.config import settings
from app.database import async_session, engine

# Preserved: login accounts + beat scheduler configuration.
PRESERVED_TABLES = ("users", "scheduler_jobs")

# Cleared in one TRUNCATE (FK-safe with CASCADE).
TABLES_TO_TRUNCATE = (
    "ingestion_trace_events",
    "rejected_items",
    "ingestion_runs",
    "user_opportunities",
    "applications",
    "requirements",
    "document_chunks",
    "learning_items",
    "notifications",
    "agent_threads",
    "opportunities",
    "raw_documents",
    "org_domain_cache",
    "domain_legitimacy_cache",
    "profile_pipeline_runs",
    "profile_submissions",
    "profile_intake_drafts",
    "user_structured_profiles",
    "user_profile_artifacts",
    "user_profiles",
    "opportunity_sources",
    "platform_settings",
    "experiences",
    "people",
    "communities",
)


async def _table_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    async with engine.connect() as conn:
        for table in (*PRESERVED_TABLES, *TABLES_TO_TRUNCATE):
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = int(result.scalar_one())
    return counts


async def _list_users() -> list[tuple[str, str]]:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, email FROM users ORDER BY created_at"))
        return [(row[0], row[1]) for row in result.fetchall()]


async def _truncate_pipeline_data() -> None:
    tables_sql = ", ".join(TABLES_TO_TRUNCATE)
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE")
        )


def _flush_redis() -> bool:
    try:
        import redis

        client = redis.from_url(settings.redis_url)
        client.flushall()
        return True
    except Exception as exc:
        print(f"Redis flush skipped: {exc}")
        return False


async def main(execute: bool, flush_redis: bool) -> int:
    users = await _list_users()
    print("Users preserved:")
    for uid, email in users:
        print(f"  {email} ({uid})")

    counts = await _table_counts()
    print("\nRow counts before cleanup:")
    for table in PRESERVED_TABLES:
        print(f"  {table}: {counts.get(table, 0)} (preserved)")
    wipe_total = 0
    for table in TABLES_TO_TRUNCATE:
        n = counts.get(table, 0)
        wipe_total += n
        print(f"  {table}: {n}")
    print(f"\nTotal rows to remove: {wipe_total}")

    if not execute:
        print("\nDry run only. Re-run with --execute to wipe data.")
        return 0

    await _truncate_pipeline_data()
    print("\nDatabase cleanup complete.")

    if flush_redis:
        if _flush_redis():
            print("Redis flushed (Celery queues cleared).")

    after = await _table_counts()
    print("\nRow counts after cleanup:")
    for table in PRESERVED_TABLES:
        print(f"  {table}: {after.get(table, 0)}")
    for table in TABLES_TO_TRUNCATE:
        print(f"  {table}: {after.get(table, 0)}")

    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description="Clean pipeline/ingestion DB data")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually truncate tables (default is dry-run)",
    )
    parser.add_argument(
        "--flush-redis",
        action="store_true",
        help="Flush Redis after DB cleanup (clears pending Celery tasks)",
    )
    args = parser.parse_args()
    return asyncio.run(main(execute=args.execute, flush_redis=args.flush_redis))


if __name__ == "__main__":
    raise SystemExit(cli())
