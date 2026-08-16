"""Evidence-based relevance gate.

Verdict semantics (after editorial tightening):

  admit       — clearly a single applyable opportunity.
  reject      — editorial/hub content, closed listings, boilerplate, or no
                opportunity signal at all.
  investigate — only when the item plausibly is one opportunity but the feed
                did not provide enough text to confirm (fetch detail page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from app.ingestion.relevance.config import RelevanceConfig, get_relevance_config
from app.ingestion.relevance.editorial import title_looks_like_single_opportunity
from app.ingestion.relevance.signals import (
    CORPUS_SIGNALS,
    FIT_SIGNALS,
    Candidate,
    ProfileTerms,
    Signal,
    collect_signals,
    detect_type_label,
)
from app.ingestion.relevance.text import find_amounts


class Verdict(str, Enum):
    admit = "admit"
    investigate = "investigate"
    reject = "reject"


@dataclass
class Decision:
    verdict: Verdict
    score: float
    corpus_score: float
    fit_score: float
    sufficiency: float
    reason: str
    stage: str = "discover"
    type_label: str | None = None
    signals: dict[str, Signal] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.verdict is not Verdict.reject

    def matched_signals(self) -> list[str]:
        return [
            name
            for name, sig in self.signals.items()
            if sig.matched and name not in ("negative", "editorial")
        ]

    def evidence_summary(self, limit: int = 6) -> list[str]:
        out: list[str] = []
        for name in ("opportunity_type", "funding", "discipline", "region", "degree", "application"):
            sig = self.signals.get(name)
            if sig and sig.matched:
                for term in sig.evidence[:2]:
                    label = f"{name}:{term}"
                    if label not in out:
                        out.append(label)
                    if len(out) >= limit:
                        return out
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "score": round(self.score, 3),
            "corpus_score": round(self.corpus_score, 3),
            "fit_score": round(self.fit_score, 3),
            "sufficiency": round(self.sufficiency, 3),
            "reason": self.reason,
            "stage": self.stage,
            "type_label": self.type_label,
            "matched": self.matched_signals(),
            "evidence": self.evidence_summary(),
            "signals": {name: sig.to_dict() for name, sig in self.signals.items()},
        }


def _noisy_or(parts: Iterable[float]) -> float:
    product = 1.0
    for value in parts:
        product *= 1.0 - max(0.0, min(1.0, value))
    return 1.0 - product


def _group_score(signals: dict[str, Signal], names: Iterable[str], cfg: RelevanceConfig) -> float:
    return _noisy_or(
        cfg.signal_weight(name) * signals[name].strength
        for name in names
        if name in signals and signals[name].matched
    )


def information_sufficiency(candidate: Candidate, cfg: RelevanceConfig) -> float:
    if candidate.detail_fetched:
        return float(cfg.sufficiency.get("after_detail_fetch", 1.0))

    length = candidate.fields().text_length
    floor = float(cfg.sufficiency.get("title_only_chars", 120))
    ceiling = float(cfg.sufficiency.get("full_text_chars", 1200))
    if length <= floor:
        return 0.15
    if length >= ceiling:
        return 1.0
    span = max(1.0, ceiling - floor)
    return 0.15 + 0.85 * ((length - floor) / span)


def _has_corpus_evidence(signals: dict[str, Signal], title: str) -> bool:
    """Enough signal to treat the item as a possible single opportunity."""
    if signals["opportunity_type"].matched or signals["funding"].matched:
        return True
    if signals["application"].matched and title_looks_like_single_opportunity(title):
        return True
    if title_looks_like_single_opportunity(title):
        return True
    return False


def _title_has_amount(title: str) -> bool:
    return bool(find_amounts(title))


def _can_admit_at_discover(
    candidate: Candidate,
    signals: dict[str, Signal],
    sufficiency: float,
    cfg: RelevanceConfig,
) -> bool:
    """High scores from keyword soup alone are not enough on a bare title."""
    if sufficiency >= cfg.threshold("min_sufficiency_to_reject"):
        return True
    if signals["application"].matched:
        return True
    if _title_has_amount(candidate.title or ""):
        return True
    single = title_looks_like_single_opportunity(candidate.title or "")
    if single and signals["opportunity_type"].matched:
        return True
    return False


def evaluate(
    candidate: Candidate,
    *,
    profile: ProfileTerms | None = None,
    config: RelevanceConfig | None = None,
    stage: str = "discover",
) -> Decision:
    cfg = config or get_relevance_config()
    terms = profile or ProfileTerms()

    signals = collect_signals(candidate, cfg, terms)
    sufficiency = information_sufficiency(candidate, cfg)

    corpus = _group_score(signals, CORPUS_SIGNALS, cfg)
    fit = _group_score(signals, FIT_SIGNALS, cfg)
    score = cfg.corpus_weight * corpus + cfg.fit_weight * fit

    negative = signals["negative"]
    if negative.matched:
        score = max(0.0, score - negative.strength * 0.5)

    editorial = signals["editorial"]
    type_label = detect_type_label(candidate.fields(), cfg)

    def _decide() -> tuple[Verdict, str]:
        if editorial.matched:
            term = editorial.evidence[0] if editorial.evidence else "editorial"
            return Verdict.reject, f"editorial:{term}"

        if negative.matched and negative.strength >= cfg.threshold("hard_negative"):
            term = negative.evidence[0] if negative.evidence else "negative phrase"
            return Verdict.reject, f"hard_negative:{term}"

        if not _has_corpus_evidence(signals, candidate.title or ""):
            return Verdict.reject, "no_opportunity_signal"

        application = signals["application"]

        if score >= cfg.threshold("admit"):
            if not _can_admit_at_discover(candidate, signals, sufficiency, cfg):
                return Verdict.investigate, "needs_detail_confirmation"
            return Verdict.admit, "score_above_admit"

        if negative.matched and score <= cfg.threshold("reject"):
            term = negative.evidence[0] if negative.evidence else "boilerplate"
            return Verdict.reject, f"boilerplate:{term}"

        if sufficiency >= cfg.threshold("min_sufficiency_to_reject") and score <= cfg.threshold("reject"):
            return Verdict.reject, "low_score_with_full_text"

        # Investigate only when the feed suggests one opportunity but we still
        # need the detail page to confirm applyability.
        if not application.matched and sufficiency < cfg.threshold("min_sufficiency_to_reject"):
            return Verdict.investigate, "needs_detail_for_application"

        if (
            score > cfg.threshold("reject")
            and sufficiency < cfg.threshold("min_sufficiency_to_reject")
            and title_looks_like_single_opportunity(candidate.title or "")
        ):
            return Verdict.investigate, "ambiguous_listing_title"

        return Verdict.reject, "below_admit_threshold"

    verdict, reason = _decide()

    return Decision(
        verdict=verdict,
        score=score,
        corpus_score=corpus,
        fit_score=fit,
        sufficiency=sufficiency,
        reason=reason,
        stage=stage,
        type_label=type_label,
        signals=signals,
    )


def explain(decision: Decision) -> str:
    parts = [f"{decision.verdict.value} score={decision.score:.2f}"]
    if decision.reason:
        parts.append(decision.reason)
    evidence = decision.evidence_summary(limit=4)
    if evidence:
        parts.append("evidence=" + ", ".join(evidence))
    else:
        parts.append("no positive signals")
    return " | ".join(parts)
