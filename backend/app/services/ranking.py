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
from app.services.eligibility_scoring import evaluate_eligibility
from app.services.embeddings import (
    calibrate_cosine_similarity,
    cosine_similarity_vectors,
    embed_text,
    lexical_similarity,
)
from app.services.profile_intake import compiled_dir
from app.services.profile_storage import load_eligibility_rules as load_eligibility_rules_db
from app.services.profile_storage import load_ranking_config as load_ranking_config_db

logger = get_logger(__name__)

SEMANTIC_WEIGHT = 0.45
ELIGIBILITY_WEIGHT = 0.30
URGENCY_WEIGHT = 0.15
AFFINITY_WEIGHT = 0.10

# Calibrated against score_distribution.py on composite outputs (post-renormalization).
STRONG_FIT_THRESHOLD = 0.62
MODERATE_FIT_THRESHOLD = 0.42


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
        return 0.0
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


def fit_level_from_score(score: float, *, hard_eligibility_failed: bool = False) -> FitLevel:
    if hard_eligibility_failed:
        if score >= MODERATE_FIT_THRESHOLD:
            return FitLevel.moderate
        return FitLevel.weak
    if score >= STRONG_FIT_THRESHOLD:
        return FitLevel.strong
    if score >= MODERATE_FIT_THRESHOLD:
        return FitLevel.moderate
    return FitLevel.weak


def build_explanation(
    profile: UserProfile,
    opportunity: Opportunity,
    semantic: float,
    eligibility_eval: Any,
    *,
    affinity: float = 0.5,
) -> str:
    parts: list[str] = []
    for reason in eligibility_eval.reasons:
        if reason.direction == "positive":
            parts.append(reason.label)
        if len(parts) >= 2:
            break

    if semantic > 0.7:
        parts.append("strong semantic alignment with your profile goals")
    elif semantic > 0.45:
        parts.append("relevant field, moderate semantic fit")
    elif semantic > 0.0:
        parts.append("lower semantic fit than top matches")

    if affinity >= 0.75:
        parts.append("aligned with your saved interests")
    elif affinity <= 0.35:
        parts.append("similar to opportunities you archived")

    if opportunity.deadline:
        days = (opportunity.deadline.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
        if days <= 7:
            parts.append(f"deadline in {days} days")

    if eligibility_eval.hard_failed:
        parts.append("hard eligibility mismatch — capped fit level")

    return "; ".join(parts[:4]) if parts else "Exploring fit based on available signals"


def compute_composite(
    components: dict[str, tuple[float, bool]],
) -> tuple[float, dict[str, float]]:
    """Renormalize weights over available components only."""
    weight_map = {
        "semantic": SEMANTIC_WEIGHT,
        "eligibility": ELIGIBILITY_WEIGHT,
        "urgency": URGENCY_WEIGHT,
        "affinity": AFFINITY_WEIGHT,
    }
    applied: dict[str, float] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for name, (score, available) in components.items():
        if not available:
            continue
        w = weight_map[name]
        applied[name] = w
        weighted_sum += w * score
        weight_total += w
    if weight_total == 0:
        return 0.0, applied
    return weighted_sum / weight_total, applied


def build_score_breakdown(
    semantic: float,
    eligibility: float,
    urgency: float,
    affinity: float,
    composite: float,
    *,
    semantic_raw: Optional[float] = None,
    semantic_method: Optional[str] = None,
    components_available: list[str],
    weights_applied: dict[str, float],
    eligibility_reasons: list[dict[str, Any]],
    hard_eligibility_failed: bool = False,
    expired: bool = False,
) -> dict[str, Any]:
    return {
        "semantic": round(semantic, 4),
        "semantic_raw": round(semantic_raw, 4) if semantic_raw is not None else None,
        "semantic_method": semantic_method,
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
        "weights_applied": weights_applied,
        "components_available": components_available,
        "eligibility_reasons": eligibility_reasons,
        "hard_eligibility_failed": hard_eligibility_failed,
        "expired": expired,
    }


def _is_expired(deadline: Optional[datetime], now: datetime) -> bool:
    if not deadline:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - now).days < 0


async def _semantic_score(
    profile: UserProfile,
    opportunity: Opportunity,
    profile_text: str,
    profile_embedding: Optional[list[float]],
) -> tuple[float, Optional[float], str, bool]:
    opp_text = f"{opportunity.title}. {opportunity.summary or ''}"

    if profile_embedding and opportunity.embedding:
        raw = cosine_similarity_vectors(profile_embedding, opportunity.embedding)
        return calibrate_cosine_similarity(raw), raw, "cosine", True

    if profile_embedding and (opportunity.summary or opportunity.title):
        opp_embedding = await embed_text(opp_text)
        if opp_embedding:
            opportunity.embedding = opp_embedding
            raw = cosine_similarity_vectors(profile_embedding, opp_embedding)
            return calibrate_cosine_similarity(raw), raw, "cosine", True

    if profile_text.strip() and opp_text.strip():
        raw_lex = lexical_similarity(profile_text, opp_text)
        return raw_lex, raw_lex, "lexical", True

    return 0.0, None, None, False


async def rank_opportunities_for_user(session: AsyncSession, profile_id: str) -> int:
    profile = await session.get(UserProfile, profile_id)
    if not profile:
        return 0

    ranking_cfg = await load_ranking_config_db(session, profile.user_id)
    eligibility_rules = await load_eligibility_rules_db(session, profile.user_id)
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
    if profile_embedding:
        profile.embedding = profile_embedding

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
        semantic, semantic_raw, semantic_method, semantic_available = await _semantic_score(
            profile, opp, profile_text, profile_embedding
        )
        if semantic_method == "cosine" and not opp.embedding and opp.summary:
            embedding_calls += 1

        elig_eval = evaluate_eligibility(profile, opp, eligibility_rules, ranking_cfg)
        elig = elig_eval.score
        urg = urgency_score(opp.deadline)
        urg_available = opp.deadline is not None
        aff = affinity_score(opp, uo_by_opp_id.get(opp.id), affinity_profile)

        composite, weights_applied = compute_composite(
            {
                "semantic": (semantic, semantic_available),
                "eligibility": (elig, True),
                "urgency": (urg, urg_available),
                "affinity": (aff, True),
            }
        )
        components_available = list(weights_applied.keys())

        level = fit_level_from_score(composite, hard_eligibility_failed=elig_eval.hard_failed)
        explanation = build_explanation(profile, opp, semantic, elig_eval, affinity=aff)
        breakdown = build_score_breakdown(
            semantic,
            elig,
            urg if urg_available else 0.0,
            aff,
            composite,
            semantic_raw=semantic_raw,
            semantic_method=semantic_method,
            components_available=components_available,
            weights_applied=weights_applied,
            eligibility_reasons=elig_eval.reason_dicts(),
            hard_eligibility_failed=elig_eval.hard_failed,
            expired=False,
        )
        scored.append((opp, composite, level, explanation, breakdown))

    if not profile_embedding and not profile_text.strip():
        logger.warning(
            "ranking_semantic_degraded",
            profile_id=profile_id,
            reason="profile_text_empty",
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
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            components_available=[],
            weights_applied={},
            eligibility_reasons=[],
            expired=True,
        )

    await session.commit()
    return len(scored)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return cosine_similarity_vectors(a, b)


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
