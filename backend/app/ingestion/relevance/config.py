"""Typed access to relevance-config.yaml with safe in-code defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.ingestion.relevance.editorial import (
    DEFAULT_EDITORIAL_TITLE_PATTERNS,
    DEFAULT_EDITORIAL_URL_PATTERNS,
)
from app.source_registry_paths import load_relevance_config

DEFAULT_THRESHOLDS: dict[str, float] = {
    "admit": 0.55,
    "reject": 0.22,
    "no_signal": 0.05,
    "min_sufficiency_to_reject": 0.5,
    "hard_negative": 0.8,
}

DEFAULT_SUFFICIENCY: dict[str, float] = {
    "full_text_chars": 1200,
    "title_only_chars": 120,
    "after_detail_fetch": 1.0,
}

DEFAULT_SIGNAL_WEIGHTS: dict[str, float] = {
    "opportunity_type": 0.95,
    "funding": 0.7,
    "application": 0.5,
    "discipline": 0.6,
    "region": 0.5,
    "degree": 0.4,
}

DEFAULT_FIELD_CONFIDENCE: dict[str, float] = {
    "title": 1.0,
    "url": 0.9,
    "summary": 0.85,
    "content": 0.75,
    "registry": 0.8,
}

DEFAULT_TYPE_LEXICON: dict[str, list[str]] = {
    "scholarship": ["scholarship", "scholarships", "bursary", "bursaries", "tuition award"],
    "fellowship": ["fellowship", "fellowships"],
    "grant": ["grant", "grants", "research grant", "seed funding", "funding call"],
    "internship": ["internship", "internships", "traineeship", "placement"],
    "phd": ["phd", "doctoral", "doctorate", "doctoral position"],
    "graduate_program": ["masters programme", "masters program", "graduate program", "postgraduate program"],
    "competition": ["competition", "contest", "hackathon", "challenge", "prize"],
    "conference": ["conference", "symposium", "summit"],
    "workshop": ["workshop", "summer school", "winter school", "training program"],
    "exchange": ["exchange program", "mobility program", "study abroad"],
}

DEFAULT_FUNDING_LEXICON: list[str] = [
    "fully funded",
    "full funding",
    "tuition",
    "tuition waiver",
    "stipend",
    "living allowance",
    "travel allowance",
    "award amount",
    "financial aid",
    "paid",
    "salary",
    "up to",
    "worth",
    "covers",
]

DEFAULT_APPLICATION_LEXICON: list[str] = [
    "deadline",
    "apply now",
    "how to apply",
    "application deadline",
    "applications open",
    "apply by",
    "closing date",
    "eligibility",
    "eligible",
    "requirements",
    "selection criteria",
    "application form",
]

DEFAULT_HARD_NEGATIVE: list[str] = [
    "applications are closed",
    "application closed",
    "no longer accepting",
    "winners announced",
    "results announced",
    "this opportunity has expired",
    "deadline has passed",
]

DEFAULT_SOFT_NEGATIVE: list[str] = [
    "privacy policy",
    "terms of service",
    "cookie policy",
    "about us",
    "contact us",
    "advertise with us",
    "newsletter signup",
    "sitemap",
]

DEFAULT_GLOBAL_MARKERS: list[str] = [
    "global",
    "worldwide",
    "international",
    "any country",
    "all nationalities",
    "all countries",
    "open to all",
]

DEFAULT_SYNONYMS: dict[str, list[str]] = {
    "tech": ["technology", "technical", "engineering", "it", "software", "computing"],
    "ai": ["artificial intelligence", "machine learning", "deep learning"],
    "machine learning": ["ml", "ai", "artificial intelligence"],
    "data science": ["data analytics", "analytics", "big data"],
    "computer science": ["cs", "computing", "informatics", "software engineering"],
    "msc": ["master", "masters", "graduate", "postgraduate"],
    "phd": ["doctoral", "doctorate", "dphil"],
    "women": ["female", "gender", "girls"],
}


def _merge_floats(defaults: dict[str, float], override: Any) -> dict[str, float]:
    out = dict(defaults)
    if isinstance(override, dict):
        for key, value in override.items():
            if isinstance(value, (int, float)):
                out[key] = float(value)
    return out


def _as_str_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(v) for v in value if v]
        if items:
            return items
    return list(fallback)


def _as_str_map(value: Any, fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    if isinstance(value, dict):
        out = {
            str(key): [str(v) for v in values if v]
            for key, values in value.items()
            if isinstance(values, list)
        }
        if out:
            return out
    return {k: list(v) for k, v in fallback.items()}


def symmetrize_synonyms(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Make synonym lookup work from any member of a group.

    The YAML lists `tech: [technology, engineering]`, but a profile that says
    "technology" must expand back to "tech" just as readily.
    """
    groups: list[set[str]] = []
    for key, values in raw.items():
        group = {key.strip().lower()} | {v.strip().lower() for v in values if v}
        group = {g for g in group if g}
        if not group:
            continue
        merged = group
        remaining: list[set[str]] = []
        for existing in groups:
            if existing & merged:
                merged = merged | existing
            else:
                remaining.append(existing)
        remaining.append(merged)
        groups = remaining

    index: dict[str, list[str]] = {}
    for group in groups:
        members = sorted(group)
        for member in members:
            index[member] = [m for m in members if m != member]
    return index


@dataclass(frozen=True)
class RelevanceConfig:
    thresholds: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    sufficiency: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SUFFICIENCY))
    signal_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SIGNAL_WEIGHTS))
    field_confidence: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_FIELD_CONFIDENCE))
    corpus_weight: float = 0.7
    fit_weight: float = 0.3
    type_lexicon: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_TYPE_LEXICON))
    funding_lexicon: list[str] = field(default_factory=lambda: list(DEFAULT_FUNDING_LEXICON))
    application_lexicon: list[str] = field(default_factory=lambda: list(DEFAULT_APPLICATION_LEXICON))
    hard_negative: list[str] = field(default_factory=lambda: list(DEFAULT_HARD_NEGATIVE))
    soft_negative: list[str] = field(default_factory=lambda: list(DEFAULT_SOFT_NEGATIVE))
    global_markers: list[str] = field(default_factory=lambda: list(DEFAULT_GLOBAL_MARKERS))
    editorial_title_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EDITORIAL_TITLE_PATTERNS))
    editorial_url_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EDITORIAL_URL_PATTERNS))
    # Symmetric index: every member of a synonym group maps to the others.
    synonyms: dict[str, list[str]] = field(default_factory=lambda: symmetrize_synonyms(DEFAULT_SYNONYMS))

    def threshold(self, name: str) -> float:
        return float(self.thresholds.get(name, DEFAULT_THRESHOLDS.get(name, 0.0)))

    def signal_weight(self, name: str) -> float:
        return float(self.signal_weights.get(name, DEFAULT_SIGNAL_WEIGHTS.get(name, 0.5)))

    def confidence_for(self, field_name: str) -> float:
        return float(self.field_confidence.get(field_name, 0.75))

    @property
    def all_type_terms(self) -> list[str]:
        terms: list[str] = []
        for values in self.type_lexicon.values():
            terms.extend(values)
        return terms


def build_config(raw: dict[str, Any] | None) -> RelevanceConfig:
    raw = raw or {}
    weights = raw.get("weights") or {}
    lexicons = raw.get("lexicons") or {}
    negative = lexicons.get("negative") or {}
    editorial = lexicons.get("editorial") or {}

    corpus_weight = weights.get("corpus")
    fit_weight = weights.get("fit")

    return RelevanceConfig(
        thresholds=_merge_floats(DEFAULT_THRESHOLDS, raw.get("thresholds")),
        sufficiency=_merge_floats(DEFAULT_SUFFICIENCY, raw.get("sufficiency")),
        signal_weights=_merge_floats(DEFAULT_SIGNAL_WEIGHTS, weights.get("signals")),
        field_confidence=_merge_floats(DEFAULT_FIELD_CONFIDENCE, raw.get("field_confidence")),
        corpus_weight=float(corpus_weight) if isinstance(corpus_weight, (int, float)) else 0.7,
        fit_weight=float(fit_weight) if isinstance(fit_weight, (int, float)) else 0.3,
        type_lexicon=_as_str_map(lexicons.get("opportunity_type"), DEFAULT_TYPE_LEXICON),
        funding_lexicon=_as_str_list(lexicons.get("funding"), DEFAULT_FUNDING_LEXICON),
        application_lexicon=_as_str_list(lexicons.get("application"), DEFAULT_APPLICATION_LEXICON),
        hard_negative=_as_str_list(negative.get("hard"), DEFAULT_HARD_NEGATIVE),
        soft_negative=_as_str_list(negative.get("soft"), DEFAULT_SOFT_NEGATIVE),
        global_markers=_as_str_list(lexicons.get("region_global_markers"), DEFAULT_GLOBAL_MARKERS),
        editorial_title_patterns=_as_str_list(editorial.get("title_patterns"), DEFAULT_EDITORIAL_TITLE_PATTERNS),
        editorial_url_patterns=_as_str_list(editorial.get("url_patterns"), DEFAULT_EDITORIAL_URL_PATTERNS),
        synonyms=symmetrize_synonyms(_as_str_map(raw.get("synonyms"), DEFAULT_SYNONYMS)),
    )


@lru_cache(maxsize=1)
def get_relevance_config() -> RelevanceConfig:
    return build_config(load_relevance_config())
