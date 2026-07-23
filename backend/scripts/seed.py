"""Seed script for development."""

import asyncio

from sqlalchemy import select

from app.database import async_session, engine, Base
from app.models import (
    Community,
    Experience,
    LearningItem,
    Opportunity,
    OpportunitySource,
    OpportunityType,
    Person,
    SourceType,
    UserOpportunity,
    UserOpportunityStatus,
    UserProfile,
)
from app.services.ranking import rank_opportunities_for_user
from datetime import datetime, timedelta, timezone


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(select(UserProfile).limit(1))
        if result.scalar_one_or_none():
            print("Database already seeded")
            return

        user = UserProfile(
            name="Default User",
            long_term_goals="Build a research career in applied AI and machine learning",
            research_interests=["applied AI", "machine learning", "computational modelling"],
            skills=["Python", "PyTorch", "research"],
            target_regions=["Germany", "Europe"],
            target_universities=["TU Dresden"],
            degree_level="MSc",
            projects=["TellO"],
            connections=["Calandra"],
        )
        session.add(user)

        sources = [
            OpportunitySource(
                name="DAAD Scholarships RSS",
                url="https://www.daad.de/en/rss/rss.xml",
                source_type=SourceType.rss,
                fetch_interval_minutes=360,
            ),
            OpportunitySource(
                name="Scholars4Dev",
                url="https://www.scholars4dev.com/feed/",
                source_type=SourceType.rss,
                fetch_interval_minutes=360,
            ),
            OpportunitySource(
                name="Opportunities for Youth",
                url="https://opportunitiesforyouth.org/feed/",
                source_type=SourceType.rss,
                fetch_interval_minutes=360,
            ),
        ]
        for s in sources:
            session.add(s)

        now = datetime.now(timezone.utc)
        sample_opps = [
            Opportunity(
                title="SECAI intelligence scholarship",
                summary="Scholarship for applied AI research at TU Dresden MSc computational modelling program.",
                institution="TU Dresden",
                program="MSc computational modelling",
                opportunity_type=OpportunityType.scholarship,
                url="https://example.com/secai-scholarship",
                url_hash="secai123",
                deadline=now + timedelta(days=6),
                requirements=["Motivation letter", "2 letters of recommendation", "Transcripts", "English proficiency proof"],
                tags=["AI", "Germany"],
            ),
            Opportunity(
                title="DAAD research grant",
                summary="Research grant for international students in relevant STEM fields.",
                institution="DAAD",
                opportunity_type=OpportunityType.grant,
                url="https://example.com/daad-grant",
                url_hash="daad456",
                deadline=now + timedelta(days=21),
                requirements=["Research proposal", "CV"],
                tags=["grant", "Germany"],
            ),
            Opportunity(
                title="Fusemachines AI fellowship, cycle 2",
                summary="AI fellowship program with strong alumni network.",
                institution="Fusemachines",
                opportunity_type=OpportunityType.fellowship,
                url="https://example.com/fuse-fellowship",
                url_hash="fuse789",
                opens_at=now + timedelta(days=35),
                requirements=["Application form", "Portfolio"],
                tags=["fellowship", "AI"],
            ),
        ]
        for opp in sample_opps:
            session.add(opp)

        await session.commit()
        await session.refresh(user)

        opp_result = await session.execute(select(Opportunity))
        for opp in opp_result.scalars().all():
            session.add(
                UserOpportunity(
                    user_id=user.id,
                    opportunity_id=opp.id,
                    status=UserOpportunityStatus.new,
                )
            )

        session.add(
            LearningItem(
                user_id=user.id,
                title="Advanced ML Specialization",
                item_type="course",
                progress_percent=45,
                status="in_progress",
            )
        )
        session.add(
            Person(
                user_id=user.id,
                name="Prof. Calandra",
                role="researcher",
                affiliation="TU Dresden",
                research_areas=["applied ML", "robotics"],
            )
        )
        session.add(
            Community(
                user_id=user.id,
                name="ML Research Discord",
                community_type="online",
                description="Active community for ML researchers",
            )
        )
        session.add(
            Experience(
                user_id=user.id,
                title="TellO Research Project",
                experience_type="research",
                description="Applied AI research project",
                status="in_progress",
            )
        )

        await session.commit()
        await rank_opportunities_for_user(session, user.id)
        print("Seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
