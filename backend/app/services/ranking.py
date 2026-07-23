from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FitLevel, Opportunity, UserOpportunity, UserOpportunityStatus, UserProfile
from app.services.embeddings import embed_text


def urgency_score(deadline: Optional[datetime]) -> float:
    if not deadline:
        return 0.2
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    days = (deadline - now).days
    if days < 0:
        return 0.0
    if days <= 7:
        return 1.0
    if days <= 14:
        return 0.8
    if days <= 30:
        return 0.6
    return 0.3


def eligibility_score(profile: UserProfile, opportunity: Opportunity) -> float:
    score = 0.5
    text = f"{opportunity.title} {opportunity.summary or ''} {opportunity.institution or ''}".lower()
    for interest in profile.research_interests or []:
        if interest.lower() in text:
            score += 0.15
    for uni in profile.target_universities or []:
        if uni.lower() in text:
            score += 0.2
    for region in profile.target_regions or []:
        if region.lower() in text:
            score += 0.1
    return min(score, 1.0)


def fit_level_from_score(score: float) -> FitLevel:
    if score >= 0.75:
        return FitLevel.strong
    if score >= 0.5:
        return FitLevel.moderate
    return FitLevel.weak


def build_explanation(profile: UserProfile, opportunity: Opportunity, semantic: float, eligibility: float) -> str:
    parts = []
    text = f"{opportunity.title} {opportunity.summary or ''}".lower()
    matched_interests = [i for i in (profile.research_interests or []) if i.lower() in text]
    matched_unis = [u for u in (profile.target_universities or []) if u.lower() in text]

    if matched_interests:
        parts.append(f"matches your {', '.join(matched_interests[:2])} focus")
    if matched_unis:
        parts.append(f"aligns with your interest in {', '.join(matched_unis[:2])}")
    if semantic > 0.7:
        parts.append("strong semantic alignment with your profile goals")
    elif semantic > 0.5:
        parts.append("relevant field, moderate fit vs top matches")
    else:
        parts.append("relevant field, lower fit than top match")

    if opportunity.deadline:
        days = (opportunity.deadline.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
        if days <= 7:
            parts.append(f"deadline in {days} days")

    return "; ".join(parts[:3])


async def rank_opportunities_for_user(session: AsyncSession, user_id: str) -> int:
    profile = await session.get(UserProfile, user_id)
    if not profile:
        return 0

    profile_text = " ".join(
        [
            profile.long_term_goals or "",
            " ".join(profile.research_interests or []),
            " ".join(profile.skills or []),
            " ".join(profile.target_universities or []),
        ]
    )
    profile_embedding = await embed_text(profile_text)
    if profile_embedding:
        profile.embedding = profile_embedding

    result = await session.execute(select(Opportunity))
    opportunities = result.scalars().all()
    scored: list[tuple[Opportunity, float, FitLevel, str]] = []

    for opp in opportunities:
        if not opp.embedding and (opp.summary or opp.title):
            opp.embedding = await embed_text(f"{opp.title}. {opp.summary or ''}")

        semantic = 0.5
        if profile.embedding and opp.embedding:
            semantic = cosine_similarity(profile.embedding, opp.embedding)

        elig = eligibility_score(profile, opp)
        urg = urgency_score(opp.deadline)
        composite = semantic * 0.5 + elig * 0.35 + urg * 0.15
        level = fit_level_from_score(composite)
        explanation = build_explanation(profile, opp, semantic, elig)
        scored.append((opp, composite, level, explanation))

    scored.sort(key=lambda x: x[1], reverse=True)

    for rank, (opp, composite, level, explanation) in enumerate(scored, start=1):
        existing = await session.execute(
            select(UserOpportunity).where(
                UserOpportunity.user_id == user_id,
                UserOpportunity.opportunity_id == opp.id,
            )
        )
        uo = existing.scalar_one_or_none()
        if not uo:
            uo = UserOpportunity(
                user_id=user_id,
                opportunity_id=opp.id,
                status=UserOpportunityStatus.new,
            )
            session.add(uo)
        uo.fit_score = round(composite, 3)
        uo.fit_level = level
        uo.fit_explanation = explanation
        uo.rank_position = rank

    await session.commit()
    return len(scored)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def days_until(deadline: Optional[datetime]) -> Optional[int]:
    if not deadline:
        return None
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - now).days


def urgency_label(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    if days < 0:
        return "expired"
    if days == 0:
        return "today"
    if days <= 7:
        return f"{days} days left"
    if days <= 14:
        return f"{days // 7} week{'s' if days // 7 > 1 else ''}"
    return f"{days // 7} weeks"
