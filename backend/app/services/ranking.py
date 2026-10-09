"""Ranking service — composite fit scores for user opportunities."""

import json
import math
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlalchemy import not_, or_, select
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
    embed_text_with_provider,
    lexical_similarity,
    matched_terms,
)
from app.services.opportunity_facts import apply_facts_to_opportunity, derive_facts
from app.services.profile_intake import compiled_dir
from app.services.profile_storage import load_eligibility_rules as load_eligibility_rules_db
from app.services.profile_storage import load_ranking_config as load_ranking_config_db
from app.services.catalog_privacy import FICTIONAL_DEMO_URL_HASH_PREFIX

logger = get_logger(__name__)

CLOSING_SOON_WINDOW_DAYS = 14

DeadlineBucket = Literal[
    "overdue",
    "today",
    "within_3_days",
    "within_7_days",
    "within_30_days",
    "later",
    "unknown",
]

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
    days = days_until(deadline)
    if days is None or days < 0:
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


NEUTRAL_FIT_REASON = "Not enough information to explain this match"


def _reason(code: str, label: str, direction: str, weight: float, source: str) -> dict[str, Any]:
    return {"code": code, "label": label, "direction": direction, "weight": weight, "source": source}


def build_fit_reasons(
    profile: UserProfile,
    opportunity: Opportunity,
    semantic: float,
    semantic_available: bool,
    semantic_method: Optional[str],
    eligibility_eval: Any,
    urgency_available: bool,
    affinity: float,
    *,
    facts: Any = None,
    evidence_terms: Optional[list[str]] = None,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Ordered explainability reasons plus a one-line summary.

    Reasons are layered so a card is never unexplained: profile matches first,
    then listing facts, then honest statements about what the listing omits.
    """
    reasons: list[dict[str, Any]] = []
    evidence_terms = evidence_terms or []

    for er in eligibility_eval.reasons:
        direction = "negative" if er.direction == "hard_fail" else er.direction
        reasons.append(_reason(er.code, er.label, direction, er.weight, "eligibility"))

    have_codes = {r["code"] for r in reasons}

    # A configured boost phrase often restates a reason we already surfaced.
    if "funding_full" in have_codes:
        reasons = [
            r
            for r in reasons
            if not (r["code"] == "boost_phrase" and "fund" in r["label"].lower())
        ]
        have_codes = {r["code"] for r in reasons}

    # Semantic evidence — name the overlapping terms rather than quoting a score.
    if semantic_available and semantic > 0:
        term_suffix = f": {', '.join(evidence_terms[:3])}" if evidence_terms else ""
        if semantic >= 0.55:
            reasons.append(
                _reason(
                    "semantic_strong",
                    f"Strong topical overlap with your profile{term_suffix}",
                    "positive",
                    round(semantic, 4),
                    "semantic",
                )
            )
        elif semantic >= 0.30:
            reasons.append(
                _reason(
                    "semantic_moderate",
                    f"Related to your stated interests{term_suffix}",
                    "positive",
                    round(semantic, 4),
                    "semantic",
                )
            )
        elif evidence_terms:
            reasons.append(
                _reason(
                    "semantic_partial",
                    f"Partial keyword overlap{term_suffix}",
                    "neutral",
                    round(semantic, 4),
                    "semantic",
                )
            )
        else:
            reasons.append(
                _reason(
                    "semantic_weak",
                    "None of your profile keywords appear in this listing",
                    "negative",
                    round(semantic, 4),
                    "semantic",
                )
            )

    # Listing facts — true regardless of profile, still useful context.
    if facts is not None:
        if facts.formats:
            fmt = facts.formats[0]
            article = "an" if fmt[0] in "aeiou" else "a"
            reasons.append(_reason("format", f"Listed as {article} {fmt}", "neutral", 0.0, "listing"))
        if facts.themes and "interest_match" not in have_codes:
            reasons.append(
                _reason(
                    "theme",
                    f"Focus areas: {', '.join(facts.themes[:3])}",
                    "neutral",
                    0.0,
                    "listing",
                )
            )
        if facts.remote is True:
            reasons.append(_reason("remote", "Can be done remotely", "positive", 0.05, "listing"))

    if opportunity.verification_status == "primary_confirmed":
        reasons.append(
            _reason("verified", "Confirmed against the official source page", "positive", 0.1, "verification")
        )

    if affinity >= 0.75:
        reasons.append(
            _reason(
                "affinity_positive",
                "Similar to opportunities you saved or started",
                "positive",
                round(affinity, 4),
                "affinity",
            )
        )
    elif affinity <= 0.35:
        reasons.append(
            _reason(
                "affinity_negative",
                "Similar to opportunities you archived",
                "negative",
                round(affinity, 4),
                "affinity",
            )
        )

    # Deadline: state the date, the rolling status, or the absence of one.
    if urgency_available and opportunity.deadline:
        days = (opportunity.deadline.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
        if days <= 14:
            reasons.append(
                _reason(
                    "urgency",
                    f"Deadline in {days} day{'s' if days != 1 else ''}",
                    "positive",
                    1.0 if days <= 7 else 0.7,
                    "urgency",
                )
            )
        elif days <= 60:
            reasons.append(
                _reason("deadline_known", f"Applications close in {days} days", "neutral", 0.3, "urgency")
            )
    elif facts is not None and facts.deadline_note == "rolling":
        reasons.append(
            _reason("deadline_rolling", "Rolling deadline. Apply any time", "neutral", 0.0, "urgency")
        )
    else:
        reasons.append(
            _reason(
                "deadline_missing",
                "No deadline published. Ranked without urgency",
                "negative",
                0.0,
                "urgency",
            )
        )

    # Degradation note is informational, never the whole story.
    semantic_degraded = not semantic_available
    if semantic_method == "lexical":
        reasons.append(
            _reason(
                "semantic_keyword_only",
                "Keyword matching used. Semantic model not configured",
                "neutral",
                0.0,
                "system",
            )
        )
    elif semantic_degraded:
        reasons.append(
            _reason(
                "semantic_unavailable",
                "This listing has too little text to compare against your profile",
                "negative",
                0.0,
                "system",
            )
        )

    direction_rank = {"positive": 0, "negative": 1, "neutral": 2}
    reasons.sort(key=lambda r: (direction_rank.get(r["direction"], 3), -(r.get("weight") or 0)))

    # A card is unexplainable only when the listing carries no usable text at all.
    substantive = [r for r in reasons if r["source"] != "system"]
    hide_percent = len(substantive) == 0

    positive_labels = [r["label"] for r in reasons if r["direction"] == "positive"]
    neutral_labels = [r["label"] for r in reasons if r["direction"] == "neutral"]
    urgency_labels = [r["label"] for r in reasons if r["code"] in ("urgency", "deadline_rolling")]

    summary_parts = positive_labels[:2]
    if not summary_parts:
        summary_parts = neutral_labels[:2]
    if urgency_labels and urgency_labels[0] not in summary_parts:
        summary_parts.append(urgency_labels[0])

    fit_reason = "; ".join(summary_parts) if summary_parts else NEUTRAL_FIT_REASON
    if not summary_parts:
        hide_percent = True

    return reasons, fit_reason, hide_percent


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
    reasons: list[dict[str, Any]] | None = None,
    hide_match_percent: bool = False,
    semantic_degraded: bool = False,
    evidence_terms: list[str] | None = None,
    derived_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "semantic": round(semantic, 4),
        "semantic_raw": round(semantic_raw, 4) if semantic_raw is not None else None,
        "semantic_method": semantic_method,
        "semantic_degraded": semantic_degraded,
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
        "reasons": reasons or [],
        "evidence_terms": evidence_terms or [],
        "derived_facts": derived_facts or {},
        "hide_match_percent": hide_match_percent,
        "hard_eligibility_failed": hard_eligibility_failed,
        "expired": expired,
    }


def _is_expired(deadline: Optional[datetime], now: datetime) -> bool:
    if not deadline:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - now).days < 0


# opportunities.embedding is Vector(1536); local providers emit other sizes.
STORED_EMBEDDING_DIMENSIONS = 1536


async def batch_embedding_cosine_similarities(
    session: AsyncSession,
    profile_embedding: list[float],
    opportunity_ids: list[str],
) -> dict[str, float]:
    """Fetch raw cosine similarities via pgvector for all stored opportunity embeddings."""
    if len(profile_embedding) != STORED_EMBEDDING_DIMENSIONS or not opportunity_ids:
        return {}
    dist = Opportunity.embedding.cosine_distance(profile_embedding)
    sim_expr = (1 - dist).label("cosine_sim")
    result = await session.execute(
        select(Opportunity.id, sim_expr).where(
            Opportunity.id.in_(opportunity_ids),
            Opportunity.embedding.isnot(None),
        )
    )
    return {row.id: float(row.cosine_sim) for row in result}


async def _semantic_score(
    profile: UserProfile,
    opportunity: Opportunity,
    profile_text: str,
    profile_embedding: Optional[list[float]],
    provider_name: Optional[str] = None,
    *,
    precomputed_cosine: Optional[float] = None,
) -> tuple[float, Optional[float], Optional[str], bool]:
    opp_text = f"{opportunity.title}. {opportunity.summary or ''}"

    if profile_embedding:
        if precomputed_cosine is not None:
            return (
                calibrate_cosine_similarity(precomputed_cosine, provider_name),
                precomputed_cosine,
                "cosine",
                True,
            )

        stored = opportunity.embedding
        if stored and len(stored) == len(profile_embedding):
            raw = cosine_similarity_vectors(profile_embedding, stored)
            return calibrate_cosine_similarity(raw, provider_name), raw, "cosine", True

        if opportunity.summary or opportunity.title:
            opp_embedding, opp_provider = await embed_text_with_provider(opp_text)
            if opp_embedding:
                # Only persist when the vector matches the column width.
                if len(opp_embedding) == STORED_EMBEDDING_DIMENSIONS:
                    opportunity.embedding = opp_embedding
                raw = cosine_similarity_vectors(profile_embedding, opp_embedding)
                return calibrate_cosine_similarity(raw, opp_provider or provider_name), raw, "cosine", True

    if profile_text.strip() and opp_text.strip():
        raw_lex = lexical_similarity(profile_text, opp_text)
        return raw_lex, raw_lex, "lexical", True

    return 0.0, None, None, False


async def recompute_affinity_for_opportunity(
    session: AsyncSession,
    user_id: str,
    opportunity_id: str,
) -> Optional[UserOpportunity]:
    """Cheap in-place affinity + composite update for a single row after status feedback."""
    result = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity, UserOpportunity.opportunity_id == Opportunity.id)
        .where(
            UserOpportunity.user_id == user_id,
            UserOpportunity.opportunity_id == opportunity_id,
        )
    )
    row = result.one_or_none()
    if not row:
        return None
    uo, opp = row

    uo_result = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity, UserOpportunity.opportunity_id == Opportunity.id)
        .where(UserOpportunity.user_id == user_id)
    )
    affinity_profile = build_affinity_profile(uo_result.all())

    breakdown = dict(uo.score_breakdown or {})
    semantic = float(breakdown.get("semantic") or 0.0)
    eligibility = float(breakdown.get("eligibility") or 0.0)
    urgency = float(breakdown.get("urgency") or 0.0)
    components_available = list(breakdown.get("components_available") or [])
    hard_failed = bool(breakdown.get("hard_eligibility_failed"))

    semantic_avail = "semantic" in components_available
    urgency_avail = "urgency" in components_available
    affinity_avail = True

    aff = affinity_score(opp, uo, affinity_profile)
    composite, weights_applied = compute_composite(
        {
            "semantic": (semantic, semantic_avail),
            "eligibility": (eligibility, "eligibility" in components_available),
            "urgency": (urgency, urgency_avail),
            "affinity": (aff, affinity_avail),
        }
    )
    if "affinity" not in components_available:
        components_available.append("affinity")

    breakdown["affinity"] = round(aff, 4)
    breakdown["composite"] = round(composite, 4)
    breakdown["weights_applied"] = weights_applied
    breakdown["components_available"] = components_available

    uo.score_breakdown = breakdown
    uo.fit_score = round(composite, 3)
    uo.fit_level = fit_level_from_score(composite, hard_eligibility_failed=hard_failed)
    return uo


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
    # Topical evidence only. Regions are excluded because they are already
    # explained by the region_match reason and would otherwise crowd out the
    # interest and skill matches that actually justify the score.
    profile_terms = [
        *(profile.research_interests or []),
        *(profile.target_universities or []),
        *(profile.skills or []),
    ]

    profile_embedding, provider_name = await embed_text_with_provider(profile_text)
    if profile_embedding and len(profile_embedding) == STORED_EMBEDDING_DIMENSIONS:
        profile.embedding = profile_embedding

    result = await session.execute(
        select(Opportunity).where(
            Opportunity.duplicate_of.is_(None),
            not_(Opportunity.url_hash.startswith(FICTIONAL_DEMO_URL_HASH_PREFIX)),
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
            or_(
                Opportunity.verification_status.is_(None),
                Opportunity.verification_status != "stale",
            ),
        )
    )
    active_opportunities = result.scalars().all()

    precomputed_cosines: dict[str, float] = {}
    if profile_embedding and len(profile_embedding) == STORED_EMBEDDING_DIMENSIONS:
        precomputed_cosines = await batch_embedding_cosine_similarities(
            session,
            profile_embedding,
            [o.id for o in active_opportunities],
        )

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

    facts_backfilled = 0

    for opp in active_opportunities:
        # Recover deadline/funding/degree/region facts the extractor left empty.
        facts = derive_facts(opp)
        if apply_facts_to_opportunity(opp, facts):
            facts_backfilled += 1

        semantic, semantic_raw, semantic_method, semantic_available = await _semantic_score(
            profile,
            opp,
            profile_text,
            profile_embedding,
            provider_name,
            precomputed_cosine=precomputed_cosines.get(opp.id),
        )
        if semantic_method == "cosine":
            embedding_calls += 1

        evidence = matched_terms(profile_terms, f"{opp.title} {opp.summary or ''}")

        elig_eval = evaluate_eligibility(profile, opp, eligibility_rules, ranking_cfg, facts=facts)
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
        semantic_degraded = not semantic_available
        fit_reasons, fit_reason, hide_percent = build_fit_reasons(
            profile,
            opp,
            semantic,
            semantic_available,
            semantic_method,
            elig_eval,
            urg_available,
            aff,
            facts=facts,
            evidence_terms=evidence,
        )
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
            reasons=fit_reasons,
            hide_match_percent=hide_percent,
            semantic_degraded=semantic_degraded,
            evidence_terms=evidence,
            derived_facts=facts.to_dict(),
        )
        scored.append((opp, composite, level, fit_reason, breakdown))

    if not profile_embedding and not profile_text.strip():
        logger.warning(
            "ranking_semantic_degraded",
            profile_id=profile_id,
            reason="profile_text_empty",
        )

    scored.sort(key=lambda x: x[1], reverse=True)

    for rank, (opp, composite, level, fit_reason, breakdown) in enumerate(scored, start=1):
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
        uo.fit_explanation = fit_reason
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
            reasons=[
                _reason("expired", "The application deadline has passed", "negative", 0.0, "urgency")
            ],
            hide_match_percent=True,
            expired=True,
        )

    logger.info(
        "ranking_completed",
        profile_id=profile_id,
        scored=len(scored),
        embedding_calls=embedding_calls,
        facts_backfilled=facts_backfilled,
    )

    await session.commit()
    return len(scored)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return cosine_similarity_vectors(a, b)


def days_until(deadline: Optional[datetime]) -> Optional[int]:
    """Whole days remaining, rounded up so a deadline 23 hours away reads as 1 day."""
    if not deadline:
        return None
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    seconds = (deadline - now).total_seconds()
    if seconds <= 0:
        return 0 if seconds == 0 else -math.ceil(abs(seconds) / 86400)
    return math.ceil(seconds / 86400)


def deadline_bucket(days: Optional[int]) -> DeadlineBucket:
    if days is None:
        return "unknown"
    if days < 0:
        return "overdue"
    if days == 0:
        return "today"
    if days <= 3:
        return "within_3_days"
    if days <= 7:
        return "within_7_days"
    if days <= 30:
        return "within_30_days"
    return "later"


def urgency_label(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    if days < 0:
        return "Expired"
    if days == 0:
        return "Due today"
    if days == 1:
        return "1 day left"
    if days <= 30:
        return f"{days} days left"
    weeks = days // 7
    return f"{weeks} week{'s' if weeks != 1 else ''} left"
