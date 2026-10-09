"""Optional fictional demo listings — never personal, never attached to real accounts.

Default behaviour is to *remove* leftover authentic sample rows from older versions
of this script (real programme names, labs, and profile fields).

Pass --fictional-demo only if you want clearly fake placeholder cards for UI checks.
Those rows are tagged with url_hash prefix demo- and are hidden from anyone who has
finished profile setup. Live matching still comes from profile setup + ingestion.

This script never writes onto an existing user's goals, projects, or connections.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.database import async_session
from app.models import (
    Application,
    Community,
    DocumentChunk,
    Experience,
    LearningItem,
    Opportunity,
    OpportunitySource,
    OpportunityType,
    Person,
    Requirement,
    SourceType,
    UserOpportunity,
    UserProfile,
)
from app.services.catalog_privacy import FICTIONAL_DEMO_URL_HASH_PREFIX

# Rows the previous seed wrote using real-looking personal/career data.
LEGACY_AUTHENTIC_URL_HASHES = ("secai123", "daad456", "fuse789")
LEGACY_AUTHENTIC_TITLES = (
    "SECAI intelligence scholarship",
    "DAAD research grant",
    "Fusemachines AI fellowship, cycle 2",
)
LEGACY_AUTHENTIC_SOURCE_NAMES = (
    "DAAD Scholarships RSS",
    "Scholars4Dev",
    "Opportunities for Youth",
)
LEGACY_PERSON_NAMES = ("Prof. Calandra",)
LEGACY_EXPERIENCE_TITLES = ("TellO Research Project",)
LEGACY_COMMUNITY_NAMES = ("ML Research Discord",)
LEGACY_LEARNING_TITLES = ("Advanced ML Specialization",)


async def _purge_legacy_authentic(session) -> dict[str, int]:
    counts = {"opportunities": 0, "sources": 0, "people": 0, "experiences": 0, "communities": 0, "learning": 0}

    opp_result = await session.execute(
        select(Opportunity).where(
            or_(
                Opportunity.url_hash.in_(LEGACY_AUTHENTIC_URL_HASHES),
                Opportunity.title.in_(LEGACY_AUTHENTIC_TITLES),
            )
        )
    )
    for opp in opp_result.scalars().all():
        uos = await session.execute(
            select(UserOpportunity).where(UserOpportunity.opportunity_id == opp.id)
        )
        for uo in uos.scalars().all():
            reqs = await session.execute(
                select(Requirement).where(Requirement.user_opportunity_id == uo.id)
            )
            for req in reqs.scalars().all():
                await session.delete(req)
            apps = await session.execute(
                select(Application).where(Application.user_opportunity_id == uo.id)
            )
            for app in apps.scalars().all():
                await session.delete(app)
            await session.delete(uo)
        chunks = await session.execute(
            select(DocumentChunk).where(DocumentChunk.opportunity_id == opp.id)
        )
        for chunk in chunks.scalars().all():
            await session.delete(chunk)
        await session.delete(opp)
        counts["opportunities"] += 1

    src_result = await session.execute(
        select(OpportunitySource).where(OpportunitySource.name.in_(LEGACY_AUTHENTIC_SOURCE_NAMES))
    )
    for source in src_result.scalars().all():
        await session.delete(source)
        counts["sources"] += 1

    people = await session.execute(select(Person).where(Person.name.in_(LEGACY_PERSON_NAMES)))
    for row in people.scalars().all():
        await session.delete(row)
        counts["people"] += 1

    experiences = await session.execute(
        select(Experience).where(Experience.title.in_(LEGACY_EXPERIENCE_TITLES))
    )
    for row in experiences.scalars().all():
        await session.delete(row)
        counts["experiences"] += 1

    communities = await session.execute(
        select(Community).where(Community.name.in_(LEGACY_COMMUNITY_NAMES))
    )
    for row in communities.scalars().all():
        await session.delete(row)
        counts["communities"] += 1

    learning = await session.execute(
        select(LearningItem).where(LearningItem.title.in_(LEGACY_LEARNING_TITLES))
    )
    for row in learning.scalars().all():
        await session.delete(row)
        counts["learning"] += 1

    # Undo profile fields the old seed copied onto the first account.
    profiles = await session.execute(select(UserProfile))
    for profile in profiles.scalars().all():
        seeded = (
            profile.projects == ["TellO"]
            or profile.connections == ["Calandra"]
            or profile.target_universities == ["TU Dresden"]
            or profile.research_interests
            == ["applied AI", "machine learning", "computational modelling"]
        )
        if not seeded:
            continue
        profile.projects = []
        profile.connections = []
        profile.target_universities = []
        profile.research_interests = []
        if profile.long_term_goals == "Build a research career in applied AI and machine learning":
            profile.long_term_goals = ""
        if profile.skills == ["Python", "PyTorch", "research"]:
            profile.skills = []
        if profile.target_regions == ["Germany", "Europe"]:
            profile.target_regions = []
        if profile.degree_level == "MSc":
            profile.degree_level = None

    return counts


async def _insert_fictional_demo(session) -> int:
    existing = await session.execute(
        select(Opportunity).where(Opportunity.url_hash.startswith(FICTIONAL_DEMO_URL_HASH_PREFIX))
    )
    if existing.scalars().first():
        print("Fictional demo listings already present; not duplicating.")
        return 0

    source = OpportunitySource(
        name="Fictional demo catalog",
        url="https://example.invalid/demo-feed",
        source_type=SourceType.rss,
        fetch_interval_minutes=1440,
        parser_config={"fictional_demo": True},
        is_active=False,
    )
    session.add(source)

    now = datetime.now(timezone.utc)
    listings = [
        Opportunity(
            title="Northhaven Graduate Fellowship (fictional)",
            summary="A made-up funded research fellowship used only to preview the card layout.",
            institution="Northhaven Institute",
            program="MSc Environmental Informatics",
            opportunity_type=OpportunityType.fellowship,
            url="https://example.invalid/northhaven-fellowship",
            url_hash=f"{FICTIONAL_DEMO_URL_HASH_PREFIX}northhaven",
            deadline=now + timedelta(days=18),
            tags=["demo", "fictional"],
            requirements=["Statement of purpose (sample)"],
        ),
        Opportunity(
            title="Riverbend International Scholarship (fictional)",
            summary="Placeholder scholarship. Not a real programme and not tied to any person.",
            institution="Riverbend University",
            program="Taught master's",
            opportunity_type=OpportunityType.scholarship,
            url="https://example.invalid/riverbend-scholarship",
            url_hash=f"{FICTIONAL_DEMO_URL_HASH_PREFIX}riverbend",
            deadline=now + timedelta(days=40),
            tags=["demo", "fictional"],
            requirements=["Transcripts (sample)"],
        ),
        Opportunity(
            title="Cedar Grove Mobility Grant (fictional)",
            summary="Imaginary short grant so the dashboard has a closing-soon example.",
            institution="Cedar Grove Foundation",
            opportunity_type=OpportunityType.grant,
            url="https://example.invalid/cedar-grove-grant",
            url_hash=f"{FICTIONAL_DEMO_URL_HASH_PREFIX}cedargrove",
            deadline=now + timedelta(days=5),
            tags=["demo", "fictional"],
            requirements=["One-page outline (sample)"],
        ),
    ]
    for opp in listings:
        session.add(opp)
    return len(listings)


async def seed(*, fictional_demo: bool) -> None:
    async with async_session() as session:
        purged = await _purge_legacy_authentic(session)
        inserted = 0
        if fictional_demo:
            inserted = await _insert_fictional_demo(session)
        await session.commit()

    print("Removed leftover authentic sample rows:", purged)
    if fictional_demo:
        print(f"Inserted {inserted} fictional demo listings (hidden after profile setup).")
    else:
        print(
            "Authentic sample seeding is disabled. "
            "Complete profile setup so ingestion can load live opportunities. "
            "Use --fictional-demo only for clearly fake placeholder cards."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fictional-demo",
        action="store_true",
        help="Insert clearly fake placeholder listings. Never copies a real profile.",
    )
    args = parser.parse_args()
    asyncio.run(seed(fictional_demo=args.fictional_demo))


if __name__ == "__main__":
    main()
