#!/usr/bin/env python3
"""Run the admin playground against a registry aggregator, without the API.

Exercises the same code path the Ingestion lab uses, including DB writes, so
you can confirm the relevance gate end to end.

Usage:
    docker compose exec api python scripts/smoke_playground.py opportunitydesk
    docker compose exec api python scripts/smoke_playground.py profellow --resolve
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session
from app.ingestion.playground import run_playground


async def main(registry_id: str, *, max_items: int, resolve: bool) -> int:
    async with async_session() as session:
        result = await run_playground(
            session,
            registry_id=registry_id,
            mode="discover",
            max_items=max_items,
            resolve_investigate=resolve,
        )

    if not result.get("ok"):
        print(f"FAILED: {result.get('error')}")
        return 1

    print(f"run_id           {result['run_id']}")
    print(f"source           {result['source_name']} ({result['registry_id']})")
    print(f"winning strategy {result.get('winning_strategy')}")
    print(f"discovered       {result['discovered']}")
    print(
        f"verdicts         admit={result.get('admit')} "
        f"investigate={result.get('investigate')} reject={result.get('reject')} "
        f"resolved={result.get('resolved')}"
    )
    print()

    for row in result.get("preview_items") or []:
        marker = "*" if row.get("resolved") else " "
        print(f"{marker}[{row['verdict']:<11} {row['score']:.2f}] {(row.get('title') or row['url'])[:72]}")
        print(f"    {row['reason']} | {', '.join(row.get('evidence') or []) or 'no evidence'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry_id")
    parser.add_argument("--max-items", type=int, default=12)
    parser.add_argument("--resolve", action="store_true", help="Fetch detail pages for uncertain items")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.registry_id, max_items=args.max_items, resolve=args.resolve)))
