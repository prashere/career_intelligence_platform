#!/usr/bin/env python3
"""Run end-to-end ingestion for registry-backed DB sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _check_deps() -> None:
    missing: list[str] = []
    for mod, pkg in (
        ("asyncpg", "asyncpg"),
        ("pgvector", "pgvector"),
        ("httpx", "httpx"),
        ("sqlalchemy", "sqlalchemy"),
    ):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(
            "Missing packages: " + ", ".join(missing) + "\n"
            "Run: pip install -r requirements.txt\n"
            "Or:  .\\scripts\\bootstrap_backend.ps1",
            file=sys.stderr,
        )
        raise SystemExit(1)


async def _seed_from_registry(session) -> tuple[int, int]:
    """Seed active sources from source-registry.yaml when DB is empty. Returns (added, total)."""
    import yaml
    from sqlalchemy import select

    from app.ingestion.registry_config import normalize_source_url
    from app.models import OpportunitySource, SourceType
    from app.source_registry_paths import SOURCE_REGISTRY_PATH

    existing = (await session.execute(select(OpportunitySource))).scalars().all()
    if existing:
        return 0, len(existing)

    registry = yaml.safe_load(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    added = 0
    for entry in registry.get("aggregators") or []:
        stype = SourceType.rss
        try:
            stype = SourceType(entry.get("type") or "rss")
        except ValueError:
            stype = SourceType.rss
        session.add(
            OpportunitySource(
                name=entry["name"],
                url=normalize_source_url(entry["url"]),
                source_type=stype,
                fetch_interval_minutes=entry.get("fetch_interval_minutes", 360),
                is_active=bool(entry.get("default_active", True)),
                registry_id=entry.get("id"),
                adapter_id=entry.get("adapter_id"),
                fetch_mode=entry.get("fetch_mode") or "http",
                summary_completeness=entry.get("summary_completeness") or "snippet_only",
                authority=float(entry.get("authority") or 0.5),
                politeness_delay_ms=int(entry.get("politeness_delay_ms") or 2500),
                parser_config=entry.get("parser_config") or {},
            )
        )
        added += 1
    await session.commit()
    return added, added


async def main(include_browser: bool, max_items: int) -> int:
    _check_deps()

    from sqlalchemy import select

    from app.database import async_session, engine, Base
    from app.ingestion.envelope_store import load_envelope_from_compiled, sync_platform_envelope
    from app.ingestion.pipeline import run_all_active_sources
    from app.models import Opportunity, OpportunitySource

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        added, total = await _seed_from_registry(session)
        if added:
            print(f"Seeded {added} sources from registry (total {total})", file=sys.stderr)
        await sync_platform_envelope(session, load_envelope_from_compiled())
        results = await run_all_active_sources(
            session, max_items=max_items, skip_browser=not include_browser
        )

    http = [r for r in results if not r.get("skipped")]
    browser = [r for r in results if r.get("skipped")]
    ok = [r for r in http if r.get("ok")]
    failed = [r for r in http if not r.get("ok")]

    async with async_session() as session:
        opp_count = len((await session.execute(select(Opportunity))).scalars().all())
        sources = (await session.execute(select(OpportunitySource))).scalars().all()

    payload = {
        "sources_total": len(sources),
        "http_runs": len(http),
        "browser_skipped": len(browser),
        "ok": len(ok),
        "failed": len(failed),
        "opportunities_in_db": opp_count,
        "include_browser": include_browser,
        "runs": results,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run end-to-end ingestion")
    parser.add_argument("--include-browser", action="store_true", help="Use Playwright for CF/JS sources")
    parser.add_argument("--max-items", type=int, default=15)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.include_browser, args.max_items)))
