"""Structured eligibility evaluation for ranking (replaces substring-only matching)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.models import Opportunity, UserProfile

Direction = Literal["positive", "negative", "hard_fail"]

DEGREE_TOKENS: dict[str, set[str]] = {
    "high_school": {"high school", "secondary", "k-12", "k12"},
    "undergraduate": {"undergraduate", "bachelor", "bsc", "bs", "ba", "undergrad"},
    "master": {"master", "masters", "msc", "ms", "m.sc", "ma", "meng"},
    "phd": {"phd", "ph.d", "doctoral", "doctorate", "postdoc", "postdoctoral"},
}

CITIZENSHIP_HARD_PHRASES: list[tuple[str, re.Pattern[str]]] = [
    ("us_citizens_only", re.compile(r"\bus\s+citizen[s]?\s+only\b", re.I)),
    ("eu_citizens_only", re.compile(r"\beu\s+citizen[s]?\s+only\b", re.I)),
    ("uk_citizens_only", re.compile(r"\buk\s+citizen[s]?\s+only\b", re.I)),
    ("domestic_only", re.compile(r"\bdomestic\s+student[s]?\s+only\b", re.I)),
]


@dataclass
class EligibilityReason:
    code: str
    label: str
    direction: Direction
    weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "direction": self.direction,
            "weight": round(self.weight, 4),
        }


@dataclass
class EligibilityEvaluation:
    score: float
    reasons: list[EligibilityReason] = field(default_factory=list)
    hard_failed: bool = False

    def reason_dicts(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.reasons]


def _normalize_degree_token(raw: str) -> Optional[str]:
    low = raw.lower().strip().replace(".", "")
    for level, tokens in DEGREE_TOKENS.items():
        if low in tokens or any(t in low for t in tokens):
            return level
    return None


def _profile_target_degree(profile: UserProfile) -> Optional[str]:
    if profile.degree_level:
        return _normalize_degree_token(profile.degree_level)
    constraints = profile.constraints or {}
    raw = constraints.get("target_degree") or constraints.get("degree_level")
    if raw:
        return _normalize_degree_token(str(raw))
    return None


def _opportunity_degree_levels(opp: Opportunity) -> set[str]:
    levels: set[str] = set()
    for raw in opp.degree_levels or []:
        norm = _normalize_degree_token(str(raw))
        if norm:
            levels.add(norm)
    text = f"{opp.title} {opp.summary or ''} {' '.join(opp.requirements or [])}".lower()
    if re.search(r"\bphd\s+only\b", text):
        levels.add("phd")
    if re.search(r"\bundergraduate\s+only\b", text):
        levels.add("undergraduate")
    return levels


def _combined_text(opp: Opportunity) -> str:
    return f"{opp.title} {opp.summary or ''} {opp.institution or ''} {' '.join(opp.requirements or [])}".lower()


def _citizenship_hard_fail(
    opp: Opportunity,
    nationality: Optional[str],
    reasons: list[EligibilityReason],
) -> bool:
    text = _combined_text(opp)
    for code, pattern in CITIZENSHIP_HARD_PHRASES:
        if not pattern.search(text):
            continue
        nat = (nationality or "").strip().lower()
        if code == "us_citizens_only" and nat and nat not in ("united states", "usa", "us", "u.s."):
            reasons.append(
                EligibilityReason(
                    code=code,
                    label="Listing restricted to US citizens",
                    direction="hard_fail",
                    weight=0.0,
                )
            )
            return True
        if code == "eu_citizens_only" and nat:
            eu_hints = ("germany", "france", "italy", "spain", "netherlands", "poland", "europe")
            if not any(h in nat for h in eu_hints):
                reasons.append(
                    EligibilityReason(
                        code=code,
                        label="Listing restricted to EU citizens",
                        direction="hard_fail",
                        weight=0.0,
                    )
                )
                return True
        if code == "uk_citizens_only" and nat and "uk" not in nat and "britain" not in nat:
            reasons.append(
                EligibilityReason(
                    code=code,
                    label="Listing restricted to UK citizens",
                    direction="hard_fail",
                    weight=0.0,
                )
            )
            return True
        if code == "domestic_only" and nat:
            reasons.append(
                EligibilityReason(
                    code=code,
                    label="Domestic students only",
                    direction="hard_fail",
                    weight=0.0,
                )
            )
            return True
    return False


def evaluate_eligibility(
    profile: UserProfile,
    opportunity: Opportunity,
    eligibility_rules: dict[str, Any],
    ranking_cfg: dict[str, Any] | None = None,
) -> EligibilityEvaluation:
    """Score 0–1 plus structured reasons; hard_failed blocks strong fit level."""
    cfg = ranking_cfg or {}
    reasons: list[EligibilityReason] = []
    hard_failed = False

    discovery_mode = (profile.constraints or {}).get("discovery_mode", cfg.get("discovery_mode", "open"))
    uni_weight = float(cfg.get("university_match_weight", 0.2))
    if discovery_mode == "target_list" and uni_weight < 0.35:
        uni_weight = 0.35
    region_weight = float(cfg.get("region_match_weight", 0.1))
    interest_weight = float(cfg.get("interest_match_weight", 0.15))
    language_weight = float(cfg.get("language_match_weight", 0.08))

    text = _combined_text(opportunity)
    score = 0.35

    # Reject phrases from compiled rules
    for phrase in eligibility_rules.get("reject_if_text_contains") or []:
        if phrase and phrase.lower() in text:
            reasons.append(
                EligibilityReason(
                    code="reject_phrase",
                    label=f"Contains exclusion phrase: {phrase}",
                    direction="hard_fail",
                    weight=0.0,
                )
            )
            hard_failed = True

    nationality = eligibility_rules.get("nationality") or (profile.constraints or {}).get("nationality")
    if _citizenship_hard_fail(opportunity, nationality, reasons):
        hard_failed = True

    target_degree = _profile_target_degree(profile)
    opp_degrees = _opportunity_degree_levels(opportunity)
    if target_degree and opp_degrees:
        if target_degree not in opp_degrees:
            if target_degree == "master" and opp_degrees == {"phd"}:
                reasons.append(
                    EligibilityReason(
                        code="degree_mismatch",
                        label="PhD-only listing for MSc applicant",
                        direction="hard_fail",
                        weight=0.0,
                    )
                )
                hard_failed = True
            elif target_degree == "undergraduate" and "phd" in opp_degrees and len(opp_degrees) == 1:
                reasons.append(
                    EligibilityReason(
                        code="degree_mismatch",
                        label="Doctoral-only listing",
                        direction="hard_fail",
                        weight=0.0,
                    )
                )
                hard_failed = True
            else:
                reasons.append(
                    EligibilityReason(
                        code="degree_partial",
                        label="Degree level may not align with listing",
                        direction="negative",
                        weight=0.12,
                    )
                )
                score -= 0.12
        else:
            reasons.append(
                EligibilityReason(
                    code="degree_match",
                    label="Open to your degree level",
                    direction="positive",
                    weight=uni_weight,
                )
            )
            score += 0.12

    require_funding = eligibility_rules.get("require_funding") or "full_only"
    funding = (opportunity.funding_type or "").lower()
    if require_funding == "full_only":
        if funding == "partial":
            reasons.append(
                EligibilityReason(
                    code="funding_partial",
                    label="Partial funding — you require full funding",
                    direction="negative",
                    weight=0.18,
                )
            )
            score -= 0.18
        elif funding == "self":
            reasons.append(
                EligibilityReason(
                    code="funding_self",
                    label="Self-funded — you require full funding",
                    direction="hard_fail",
                    weight=0.0,
                )
            )
            hard_failed = True
        elif funding == "full" or any(
            p in text for p in ("fully funded", "full funding", "tuition waiver", "stipend")
        ):
            reasons.append(
                EligibilityReason(
                    code="funding_full",
                    label="Fully funded opportunity",
                    direction="positive",
                    weight=0.15,
                )
            )
            score += 0.15

    for interest in profile.research_interests or []:
        if interest.lower() in text:
            reasons.append(
                EligibilityReason(
                    code="interest_match",
                    label=f"Matches your {interest} focus",
                    direction="positive",
                    weight=interest_weight,
                )
            )
            score += interest_weight * 0.85
            break

    for uni in profile.target_universities or []:
        if uni.lower() in text:
            reasons.append(
                EligibilityReason(
                    code="university_match",
                    label=f"Aligns with {uni}",
                    direction="positive",
                    weight=uni_weight,
                )
            )
            score += uni_weight * 0.85
            break

    region_hits: list[str] = []
    for region in profile.target_regions or []:
        if region.lower() in text:
            region_hits.append(region)
        for country in opportunity.countries or []:
            if region.lower() in str(country).lower():
                region_hits.append(region)
    if region_hits:
        reasons.append(
            EligibilityReason(
                code="region_match",
                label=f"Region fit: {', '.join(region_hits[:2])}",
                direction="positive",
                weight=region_weight,
            )
        )
        score += region_weight * 0.85

    langs = eligibility_rules.get("other_languages") or (profile.constraints or {}).get("other_languages") or []
    for lang in langs:
        if lang and lang.lower() in text:
            reasons.append(
                EligibilityReason(
                    code="language_match",
                    label=f"Language requirement met: {lang}",
                    direction="positive",
                    weight=language_weight,
                )
            )
            score += language_weight * 0.85
            break

    for phrase in eligibility_rules.get("boost_if_text_contains") or []:
        if phrase and phrase.lower() in text:
            reasons.append(
                EligibilityReason(
                    code="boost_phrase",
                    label=f"Profile boost: {phrase}",
                    direction="positive",
                    weight=0.05,
                )
            )
            score += 0.05

    score = max(0.0, min(1.0, score))
    return EligibilityEvaluation(score=round(score, 4), reasons=reasons, hard_failed=hard_failed)
