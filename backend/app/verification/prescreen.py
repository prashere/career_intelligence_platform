"""Tier 1 deterministic pre-screen — no LLM."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.verification.contracts import AggregatorClaims, PrescreenResult
from app.verification.domain_utils import extract_domain, is_institutional_domain

logger = logging.getLogger(__name__)

SCAM_PHRASES = [
    "processing fee",
    "pay to apply",
    "guaranteed acceptance",
    "guaranteed admission",
    "wire transfer",
    "send money",
    "whatsapp only",
    "telegram only",
    "crypto payment",
    "registration fee required",
]

LOW_TRUST_THRESHOLD = 0.25
HIGH_TRUST_THRESHOLD = 0.72


def scan_scam_phrases(text: str) -> list[str]:
    lower = (text or "").lower()
    return [p for p in SCAM_PHRASES if p in lower]


def source_precision_bonus(outcome_stats: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not outcome_stats:
        return 0.0, []
    rate = outcome_stats.get("admit_rate")
    if rate is None:
        return 0.0, []
    if rate >= 0.25:
        return 0.15, ["source_high_admit_rate"]
    if rate < 0.08 and int(outcome_stats.get("runs") or 0) >= 3:
        return -0.2, ["source_low_admit_rate"]
    return 0.0, []


def run_prescreen(
    claims: AggregatorClaims,
    *,
    domain_trust: float | None = None,
    domain_flags: list[str] | None = None,
    cached_org_confidence: float | None = None,
    source_outcome_stats: dict[str, Any] | None = None,
    allowlisted_domain: bool = False,
) -> PrescreenResult:
    flags: list[str] = list(domain_flags or [])
    score = 0.5

    listing_domain = extract_domain(claims.url)
    if listing_domain:
        if is_institutional_domain(listing_domain):
            score += 0.2
            flags.append("institutional_listing_domain")
        if allowlisted_domain:
            score += 0.15
            flags.append("allowlisted_domain")

    if domain_trust is not None:
        score = 0.4 * score + 0.6 * domain_trust

    scam_hits = scan_scam_phrases(
        f"{claims.title} {claims.summary or ''} {claims.url}"
    )
    if scam_hits:
        score -= 0.35
        flags.extend([f"scam_phrase:{h}" for h in scam_hits[:3]])

    bonus, bonus_flags = source_precision_bonus(source_outcome_stats)
    score += bonus
    flags.extend(bonus_flags)

    if cached_org_confidence is not None and cached_org_confidence >= 0.7:
        score += 0.1
        flags.append("cached_org_domain")

    score = max(0.0, min(1.0, score))

    if score <= LOW_TRUST_THRESHOLD or scam_hits:
        action = "stop"
    elif score >= HIGH_TRUST_THRESHOLD and is_institutional_domain(listing_domain or ""):
        action = "light_tier2"
    else:
        action = "continue"

    return PrescreenResult(
        trust_score=round(score, 3),
        action=action,
        flags=flags,
        listing_domain=listing_domain,
        domain_trust=domain_trust,
    )
