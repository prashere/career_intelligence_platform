"""Print the explanation payload the dashboard receives, for spot-checking.

Usage (inside the api container):
    python scripts/show_card_reasons.py [limit]
"""

import asyncio
import sys

from sqlalchemy import select

from app.database import async_session
from app.models import UserProfile
from app.services.opportunities import list_opportunities

ICON = {"positive": "+", "negative": "-", "neutral": "."}


async def main(limit: int) -> None:
    async with async_session() as session:
        profile = (await session.execute(select(UserProfile))).scalars().first()
        if not profile:
            print("no profile found")
            return

        result = await list_opportunities(
            session, profile.id, bucket="matches", sort="fit", limit=limit
        )
        print(f"{result.total} matches for {profile.name}\n")

        for item in result.items:
            breakdown = item.score_breakdown or {}
            percent = f"{item.fit_percent}%" if item.fit_percent is not None else "hidden"
            print("=" * 72)
            print(item.title[:68])
            print(f"  {item.fit_level} - {percent} (via {breakdown.get('semantic_method')})")
            print(f"  summary: {item.fit_explanation}")
            for reason in breakdown.get("reasons", []):
                mark = ICON.get(reason.get("direction"), "?")
                print(f"    {mark} {reason.get('label')}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
