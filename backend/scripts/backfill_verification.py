"""Backfill verification for unverified opportunity backlog.

Usage:
    python scripts/backfill_verification.py --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.config import settings
from app.database import async_session
from app.models import Opportunity
from app.models.verification import VerificationStatus
from app.verification.service import run_verification_backfill


async def print_status_snapshot() -> None:
    async with async_session() as session:
        rows = await session.execute(
            select(Opportunity.verification_status, func.count())
            .where(Opportunity.duplicate_of.is_(None))
            .group_by(Opportunity.verification_status)
        )
        counts = dict(rows.all())
    print("Current verification_status counts:", counts or "none")


async def main(limit: int, reverify: bool) -> int:
    if not settings.tavily_api_key:
        print(
            "WARNING: TAVILY_API_KEY is not set. Web search is disabled, so "
            "verification cannot find official source pages. Expect aggregator_only "
            "or unchecked states, not primary_confirmed.\n"
            "Add TAVILY_API_KEY to career_intelligence_platform/.env and rerun.\n"
        )
    elif reverify:
        print(
            "Re-verifying aggregator_only rows with Tavily enabled. "
            "This uses API credits for search and page fetch.\n"
        )

    async with async_session() as session:
        result = await run_verification_backfill(
            session,
            limit=limit,
            include_aggregator_only=reverify,
        )

    outcomes = result.get("outcomes") or []
    status_counts = Counter(
        o.get("status")
        for o in outcomes
        if o.get("ok") and o.get("status")
    )
    skipped = sum(1 for o in outcomes if o.get("skipped"))
    errors = [o for o in outcomes if not o.get("ok")]

    print(f"Processed: {result['processed']}")
    print(f"Primary confirmed: {result['primary_confirmed']}")
    if status_counts:
        print("Outcome statuses:", dict(status_counts))
    if skipped:
        print(f"Skipped (already verified): {skipped}")
    if errors:
        print(f"Errors: {len(errors)}")
        for err in errors[:5]:
            print(f"  - {err.get('opportunity_id') or 'unknown'}: {err.get('error')}")

    await print_status_snapshot()

    if result["processed"] == 0 and not reverify:
        print(
            "\nNo unverified rows left. Rows verified without Tavily are aggregator_only. "
            "Re-run with --reverify to process those again:\n"
            "  python scripts/backfill_verification.py --limit 25 --reverify\n"
        )

    if result["primary_confirmed"] == 0 and settings.tavily_api_key and result["processed"] > 0:
        print(
            "\nTip: With Tavily configured, zero confirmations usually means search "
            "did not find a matching official page, or field comparison disagreed "
            "(deadline/funding/eligibility). Check LangSmith traces or re-run with "
            "--limit 5 and inspect verification_meta on a sample row."
        )

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill verification for unverified opportunities")
    parser.add_argument("--limit", type=int, default=100, help="Max opportunities to verify")
    parser.add_argument(
        "--reverify",
        action="store_true",
        help="Also re-run verification on aggregator_only rows (e.g. after adding Tavily)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.limit, args.reverify)))
