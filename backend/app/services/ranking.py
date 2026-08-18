"""Ranking service — composite fit scores for user opportunities."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models import FitLevel, Opportunity, UserOpportunity, UserOpportunityStatus, UserProfile
from app.services.affinity import (
    AffinityProfile,
    affinity_score,
    build_affinity_profile,
)
from app.services.embeddings import embed_text
from app.services.profile_intake import compiled_dir
from app.services.profile_storage import load_ranking_config as load_ranking_config_db

logger = get_logger(__name__)

SEMANTIC_WEIGHT = 0.45
ELIGIBILITY_WEIGHT = 0.30
URGENCY_WEIGHT = 0.15
AFFINITY_WEIGHT = 0.10


def load_ranking_config() -> dict[str, Any]:
    path = compiled_dir() / "ranking_config.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "discovery_mode": "open",
        "university_match_weight": 0.2,
        "region_match_weight": 0.1,
        "interest_match_weight": 0.15,
        "language_match_weight": 0.08,
        "open_to_relocation": True,
        "manual_channels": [],
    }


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


def eligibility_score(
    profile: UserProfile,
    opportunity: Opportunity,
    ranking_cfg: dict[str, Any] | None = None,
) -> float:
    cfg = ranking_cfg or load_ranking_config()
    constraints = profile.constraints or {}
    discovery_mode = constraints.get("discovery_mode", cfg.get("discovery_mode", "open"))
    uni_weight = float(cfg.get("university_match_weight", 0.2))
    if discovery_mode == "target_list" and uni_weight < 0.35:
        uni_weight = 0.35
    region_weight = float(cfg.get("region_match_weight", 0.1))
    interest_weight = float(cfg.get("interest_match_weight", 0.15))
    language_weight = float(cfg.get("language_match_weight", 0.08))

    score = 0.5
    text = f"{opportunity.title} {opportunity.summary or ''} {opportunity.institution or ''}".lower()
    for interest in profile.research_interests or []:
        if interest.lower() in text:
            score += interest_weight
    for uni in profile.target_universities or []:
        if uni.lower() in text:
            score += uni_weight
    for region in profile.target_regions or []:
        if region.lower() in text:
            score += region_weight
    for lang in constraints.get("other_languages") or []:
        if lang.lower() in text:
            score += language_weight
    return min(score, 1.0)


def fit_level_from_score(score: float) -> FitLevel:
    if score >= 0.75:
        return FitLevel.strong
    if score >= 0.5:
        return FitLevel.moderate
    return FitLevel.weak


def build_explanation(
    profile: UserProfile,
    opportunity: Opportunity,
    semantic: float,
    eligibility: float,
    *,
    affinity: float = 0.5,
) -> str:
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

    if affinity >= 0.75:
        parts.append("aligned with your saved interests")
    elif affinity <= 0.35:
        parts.append("similar to opportunities you archived")

    if opportunity.deadline:
        days = (opportunity.deadline.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
        if days <= 7:
            parts.append(f"deadline in {days} days")

    return "; ".join(parts[:3])


def build_score_breakdown(
    semantic: float,
    eligibility: float,
    urgency: float,
    affinity: float,
    composite: float,
    *,
    semantic_degraded: bool = False,
    expired: bool = False,
) -> dict[str, Any]:
    return {
        "semantic": round(semantic, 4),
        "eligibility": round(eligibility, 4),
        "urgency": round(urgency, 4),
        "affinity": round(affinity, 4),
        "composite": round(composite, 4),
        "weights": {
            "semantic": SEMANTIC_WEIGHT,
            "eligibility": ELIGIBILITY_WEIGHT,
            "urgency": URGENCY_WEIGHT,
            "affinity": AFFINITY_WEIGHT,
        },
        "semantic_degraded": semantic_degraded,
        "expired": expired,
    }


def _is_expired(deadline: Optional[datetime], now: datetime) -> bool:
    if not deadline:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - now).days < 0


async def rank_opportunities_for_user(session: AsyncSession, profile_id: str) -> int:
    profile = await session.get(UserProfile, profile_id)
    if not profile:
        return 0

    ranking_cfg = await load_ranking_config_db(session, profile.user_id)
    now = datetime.now(timezone.utc)

    uo_result = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity, UserOpportunity.opportunity_id == Opportunity.id)
        .where(UserOpportunity.user_id == profile_id)
    )
    uo_rows = uo_result.all()
    uo_by_opp_id = {opp.id: uo for uo, opp in uo_rows}
    affinity_profile = build_affinity_profile(uo_rows)

    profile_text = " ".join(
        [
            profile.long_term_goals or "",
            " ".join(profile.research_interests or []),
            " ".join(profile.skills or []),
            " ".join(profile.target_universities or []),
        ]
    )
    profile_embedding = await embed_text(profile_text)
    profile_embedding_missing = profile_embedding is None
    if profile_embedding:
        profile.embedding = profile_embedding

    # Canonical opportunities only — duplicates sink to canonical via duplicate_of.
    result = await session.execute(
        select(Opportunity).where(
            Opportunity.duplicate_of.is_(None),
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
            or_(
                Opportunity.verification_status.is_(None),
                Opportunity.verification_status != "stale",
            ),
        )
    )
    active_opportunities = result.scalars().all()

    expired_result = await session.execute(
        select(Opportunity).where(
            Opportunity.duplicate_of.is_(None),
            Opportunity.deadline.isnot(None),
            Opportunity.deadline < now,
        )
    )
    expired_opportunities = expired_result.scalars().all()

    scored: list[tuple[Opportunity, float, FitLevel, str, dict[str, Any]]] = []
    embedding_calls = 0

    for opp in active_opportunities:
        semantic_degraded = False
        if not opp.embedding and (opp.summary or opp.title):
            opp.embedding = await embed_text(f"{opp.title}. {opp.summary or ''}")
            if opp.embedding:
                embedding_calls += 1

        semantic = 0.5
        if profile.embedding and opp.embedding:
            semantic = cosine_similarity(profile.embedding, opp.embedding)
        elif profile_embedding_missing or not opp.embedding:
            semantic_degraded = True

        elig = eligibility_score(profile, opp, ranking_cfg)
        urg = urgency_score(opp.deadline)
        aff = affinity_score(opp, uo_by_opp_id.get(opp.id), affinity_profile)
        composite = (
            semantic * SEMANTIC_WEIGHT
            + elig * ELIGIBILITY_WEIGHT
            + urg * URGENCY_WEIGHT
            + aff * AFFINITY_WEIGHT
        )
        level = fit_level_from_score(composite)
        explanation = build_explanation(profile, opp, semantic, elig, affinity=aff)
        breakdown = build_score_breakdown(
            semantic, elig, urg, aff, composite,
            semantic_degraded=semantic_degraded,
            expired=False,
        )
        scored.append((opp, composite, level, explanation, breakdown))

    if profile_embedding_missing:
        logger.warning(
            "ranking_semantic_degraded",
            profile_id=profile_id,
            reason="profile_embedding_missing",
        )

    scored.sort(key=lambda x: x[1], reverse=True)

    for rank, (opp, composite, level, explanation, breakdown) in enumerate(scored, start=1):
        existing = await session.execute(
            select(UserOpportunity).where(
                UserOpportunity.user_id == profile_id,
                UserOpportunity.opportunity_id == opp.id,
            )
        )
        uo = existing.scalar_one_or_none()
        if not uo:
            uo = UserOpportunity(
                user_id=profile_id,
                opportunity_id=opp.id,
                status=UserOpportunityStatus.new,
            )
            session.add(uo)
        uo.fit_score = round(composite, 3)
        uo.fit_level = level
        uo.fit_explanation = explanation
        uo.rank_position = rank
        uo.score_breakdown = breakdown

    for opp in expired_opportunities:
        existing = await session.execute(
            select(UserOpportunity).where(
                UserOpportunity.user_id == profile_id,
                UserOpportunity.opportunity_id == opp.id,
            )
        )
        uo = existing.scalar_one_or_none()
        if not uo:
            uo = UserOpportunity(
                user_id=profile_id,
                opportunity_id=opp.id,
                status=UserOpportunityStatus.new,
            )
            session.add(uo)
        uo.fit_score = 0.0
        uo.fit_level = FitLevel.weak
        uo.fit_explanation = "deadline has passed"
        uo.rank_position = None
        uo.score_breakdown = build_score_breakdown(
            0.0, 0.0, 0.0, 0.0, 0.0,
            semantic_degraded=profile_embedding_missing,
            expired=True,
        )

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
