#!/usr/bin/env python3
"""Print composite score distribution and component degradation stats.

Usage:
    cd backend
    python scripts/score_distribution.py
    python scripts/score_distribution.py --user-email you@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session
from app.models import Opportunity, User, UserOpportunity, UserProfile


def _histogram(values: list[float], bins: int = 10) -> list[tuple[str, int]]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [(f"{lo:.2f}", len(values))]
    step = (hi - lo) / bins
    counts: Counter[str] = Counter()
    for v in values:
        idx = min(int((v - lo) / step), bins - 1)
        start = lo + idx * step
        end = start + step
        label = f"{start:.2f}-{end:.2f}"
        counts[label] += 1
    return sorted(counts.items())


async def run(user_email: str | None) -> None:
    async with async_session() as session:
        profile_id: str | None = None
        if user_email:
            user = (
                await session.execute(select(User).where(User.email == user_email))
            ).scalar_one_or_none()
            if not user:
                print(f"No user for email {user_email}")
                return
            profile = (
                await session.execute(select(UserProfile).where(UserProfile.user_id == user.id))
            ).scalar_one_or_none()
            if not profile:
                print(f"No profile for {user_email}")
                return
            profile_id = profile.id

        query = select(UserOpportunity, Opportunity).join(
            Opportunity, UserOpportunity.opportunity_id == Opportunity.id
        )
        if profile_id:
            query = query.where(UserOpportunity.user_id == profile_id)

        result = await session.execute(query)
        rows = result.all()

    composites = [uo.fit_score for uo, _ in rows if uo.fit_score is not None]
    levels = Counter(uo.fit_level.value if uo.fit_level else "none" for uo, _ in rows)
    no_deadline = 0
    degraded_semantic = 0
    hard_elig = 0
    component_missing: Counter[str] = Counter()

    for uo, opp in rows:
        bd = uo.score_breakdown or {}
        available = set(bd.get("components_available") or [])
        for comp in ("semantic", "eligibility", "urgency", "affinity"):
            if comp not in available:
                component_missing[comp] += 1
        if bd.get("semantic_degraded") or bd.get("semantic_method") == "lexical":
            degraded_semantic += 1
        if bd.get("hard_eligibility_failed"):
            hard_elig += 1
        if opp.deadline is None:
            no_deadline += 1

    print("=== Score distribution ===")
    print(f"Rows with fit_score: {len(composites)} / {len(rows)}")
    if composites:
        print(f"Min composite: {min(composites):.3f}")
        print(f"Max composite: {max(composites):.3f}")
        print(f"Mean composite: {sum(composites) / len(composites):.3f}")
    print("\nHistogram (composite):")
    for label, count in _histogram(composites):
        print(f"  {label}: {count}")

    print("\nFit levels:")
    for level, count in sorted(levels.items()):
        print(f"  {level}: {count}")

    print("\nComponent missing counts (from score_breakdown):")
    for comp, count in component_missing.most_common():
        print(f"  {comp}: {count}")

    print(f"\nSemantic degraded / lexical: {degraded_semantic}")
    print(f"Hard eligibility failed: {hard_elig}")
    print(f"Opportunities with no deadline (uo rows): {no_deadline}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score distribution report")
    parser.add_argument("--user-email", help="Scope to one user's profile")
    args = parser.parse_args()
    asyncio.run(run(args.user_email))


if __name__ == "__main__":
    main()
