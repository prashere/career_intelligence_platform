"""Signal extraction for the relevance gate.

Each signal reports *what* it found and *where*, so a rejection can always be
explained to the operator instead of collapsing into a bare "must_match_any".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.ingestion.relevance.config import RelevanceConfig
from app.ingestion.relevance.editorial import (
    detect_editorial,
    title_looks_like_single_opportunity,
)
from app.ingestion.relevance.text import (
    TextFields,
    expand_terms,
    find_amounts,
    find_terms,
    normalize,
)

# Search order matters: a term in the title is stronger evidence than the same
# term buried in boilerplate at the bottom of a detail page.
FIELD_PRIORITY = ("title", "url", "summary", "content")

CORPUS_SIGNALS = ("opportunity_type", "funding", "application")
FIT_SIGNALS = ("discipline", "region", "degree")


@dataclass
class Signal:
    name: str
    matched: bool = False
    strength: float = 0.0
    evidence: list[str] = field(default_factory=list)
    found_in: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "matched": self.matched,
            "strength": round(self.strength, 3),
            "evidence": self.evidence[:6],
            "found_in": self.found_in,
            "note": self.note,
        }


@dataclass
class Candidate:
    """Everything known about one item at the moment it is scored."""

    url: str = ""
    title: str = ""
    summary: str = ""
    content: str = ""
    source_regions: list[str] = field(default_factory=list)
    source_tags: list[str] = field(default_factory=list)
    detail_fetched: bool = False

    def fields(self) -> TextFields:
        return TextFields(title=self.title, summary=self.summary, content=self.content, url=self.url)


@dataclass
class ProfileTerms:
    """Operator preferences, used only to raise scores, never to gate."""

    disciplines: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    degrees: list[str] = field(default_factory=list)
    hard_drop: list[str] = field(default_factory=list)
    extra_type_terms: list[str] = field(default_factory=list)


_DEGREE_HINTS = ("msc", "master", "masters", "phd", "doctoral", "bachelor", "undergraduate", "postgraduate")


def profile_terms_from_envelope(envelope: dict[str, Any] | None) -> ProfileTerms:
    """Adapt the legacy interest envelope into scoring inputs.

    The envelope keys keep their original names so existing compiled profiles
    keep working, but none of them gate any more.
    """
    env = envelope or {}

    disciplines = [t for t in (env.get("profile_match_any") or []) if t]
    disciplines += [t for t in (env.get("institution_match_any") or []) if t]

    degrees = [t for t in (env.get("target_degree_levels") or []) if t]
    extra_types: list[str] = []
    for term in env.get("must_match_any") or []:
        if not term:
            continue
        if any(hint in normalize(term) for hint in _DEGREE_HINTS):
            degrees.append(term)
        else:
            extra_types.append(term)

    return ProfileTerms(
        disciplines=list(dict.fromkeys(disciplines)),
        regions=list(dict.fromkeys(t for t in (env.get("region_match_any") or []) if t)),
        degrees=list(dict.fromkeys(degrees)),
        hard_drop=list(dict.fromkeys(t for t in (env.get("hard_drop_any") or []) if t)),
        extra_type_terms=list(dict.fromkeys(extra_types)),
    )


def _scan(
    name: str,
    terms: Sequence[str],
    fields: TextFields,
    cfg: RelevanceConfig,
    *,
    note: str | None = None,
) -> Signal:
    """Find `terms` across all fields and score by the strongest field hit."""
    if not terms:
        return Signal(name=name, note=note or "no terms configured")

    best_field: str | None = None
    best_confidence = 0.0
    all_hits: list[str] = []

    for field_name in FIELD_PRIORITY:
        text = fields.normalized(field_name)
        if not text:
            continue
        hits = find_terms(terms, text)
        if not hits:
            continue
        confidence = cfg.confidence_for(field_name)
        if confidence > best_confidence:
            best_confidence = confidence
            best_field = field_name
        for hit in hits:
            if hit not in all_hits:
                all_hits.append(hit)

    if not all_hits:
        return Signal(name=name, note=note)

    multi_bonus = min(len(all_hits) - 1, 2) * 0.05
    return Signal(
        name=name,
        matched=True,
        strength=min(1.0, best_confidence + multi_bonus),
        evidence=all_hits,
        found_in=best_field,
        note=note,
    )


def opportunity_type_signal(fields: TextFields, cfg: RelevanceConfig, profile: ProfileTerms) -> Signal:
    terms = cfg.all_type_terms + list(profile.extra_type_terms)
    return _scan("opportunity_type", terms, fields, cfg)


def detect_type_label(fields: TextFields, cfg: RelevanceConfig) -> str | None:
    """Which taxonomy bucket the item belongs to, title first."""
    for field_name in FIELD_PRIORITY:
        text = fields.normalized(field_name)
        if not text:
            continue
        for label, terms in cfg.type_lexicon.items():
            if find_terms(terms, text, limit=1):
                return label
    return None


def funding_signal(fields: TextFields, cfg: RelevanceConfig) -> Signal:
    signal = _scan("funding", cfg.funding_lexicon, fields, cfg)

    # A concrete amount ("up to $10,000") is the strongest funding evidence
    # available and is invisible to keyword lists.
    amounts = find_amounts(fields.raw_blob)
    if amounts:
        signal.matched = True
        signal.strength = min(1.0, max(signal.strength, cfg.confidence_for("title")))
        signal.evidence = amounts + [e for e in signal.evidence if e not in amounts]
        signal.found_in = signal.found_in or "title"
        signal.note = "monetary amount detected"
    return signal


def application_signal(fields: TextFields, cfg: RelevanceConfig) -> Signal:
    return _scan("application", cfg.application_lexicon, fields, cfg)


def discipline_signal(fields: TextFields, cfg: RelevanceConfig, profile: ProfileTerms) -> Signal:
    if not profile.disciplines:
        return Signal(name="discipline", note="no profile disciplines configured")
    terms = expand_terms(profile.disciplines, cfg.synonyms)
    return _scan("discipline", terms, fields, cfg)


def degree_signal(fields: TextFields, cfg: RelevanceConfig, profile: ProfileTerms) -> Signal:
    if not profile.degrees:
        return Signal(name="degree", note="no profile degrees configured")
    terms = expand_terms(profile.degrees, cfg.synonyms)
    return _scan("degree", terms, fields, cfg)


def region_signal(
    fields: TextFields,
    cfg: RelevanceConfig,
    profile: ProfileTerms,
    source_regions: Iterable[str],
) -> Signal:
    """Region evidence from the text, the source registry, or a global marker.

    The old filter only looked at the item text, so any listing whose title did
    not name a country was dropped. The aggregator's own declared regions are a
    far better signal and were being ignored entirely.
    """
    if not profile.regions:
        return Signal(name="region", note="no profile regions configured")

    terms = expand_terms(profile.regions, cfg.synonyms)
    signal = _scan("region", terms, fields, cfg)
    if signal.matched:
        return signal

    registry_regions = [r for r in source_regions if r]
    if registry_regions:
        overlap = find_terms(terms, normalize(" ".join(registry_regions)))
        if overlap:
            return Signal(
                name="region",
                matched=True,
                strength=cfg.confidence_for("registry"),
                evidence=overlap,
                found_in="registry",
                note="matched source registry regions",
            )

    global_hits = find_terms(cfg.global_markers, fields.blob, limit=2)
    if global_hits:
        return Signal(
            name="region",
            matched=True,
            strength=cfg.confidence_for("summary"),
            evidence=global_hits,
            found_in="text",
            note="open to all regions",
        )

    return Signal(name="region", note="no region evidence yet")


def negative_signal(fields: TextFields, cfg: RelevanceConfig, profile: ProfileTerms) -> Signal:
    """Hard negatives reject outright; soft negatives only pull the score down.

    Both are scoped to the title and summary. A live scholarship page routinely
    mentions "2024 winners announced" or links a privacy policy in its footer,
    so scanning full page content here would reject valid opportunities.
    """
    headline = " ".join(p for p in (fields.normalized("title"), fields.normalized("summary")) if p)
    if not headline:
        return Signal(name="negative")

    hard_terms = list(cfg.hard_negative) + list(profile.hard_drop)
    hard_hits = find_terms(hard_terms, headline)
    if hard_hits:
        return Signal(
            name="negative",
            matched=True,
            strength=1.0,
            evidence=hard_hits,
            found_in="title" if find_terms(hard_terms, fields.normalized("title"), limit=1) else "summary",
            note="hard negative",
        )

    soft_hits = find_terms(cfg.soft_negative, headline)
    if soft_hits:
        in_title = bool(find_terms(cfg.soft_negative, fields.normalized("title"), limit=1))
        return Signal(
            name="negative",
            matched=True,
            strength=0.6 if in_title else 0.2,
            evidence=soft_hits,
            found_in="title" if in_title else "summary",
            note="boilerplate page wording" if in_title else "boilerplate wording in body",
        )

    return Signal(name="negative")


def editorial_signal(fields: TextFields, cfg: RelevanceConfig) -> Signal:
    """Listicles, guides, reviews, and hub pages — not applyable listings."""
    matched, evidence, found_in = detect_editorial(
        fields,
        title_patterns=cfg.editorial_title_patterns,
        url_patterns=cfg.editorial_url_patterns,
    )
    if not matched:
        return Signal(name="editorial", note="not editorial content")
    return Signal(
        name="editorial",
        matched=True,
        strength=1.0,
        evidence=[evidence or "editorial pattern"],
        found_in=found_in,
        note="editorial or hub page",
    )


def collect_signals(
    candidate: Candidate,
    cfg: RelevanceConfig,
    profile: ProfileTerms,
) -> dict[str, Signal]:
    fields = candidate.fields()
    return {
        "opportunity_type": opportunity_type_signal(fields, cfg, profile),
        "funding": funding_signal(fields, cfg),
        "application": application_signal(fields, cfg),
        "discipline": discipline_signal(fields, cfg, profile),
        "degree": degree_signal(fields, cfg, profile),
        "region": region_signal(fields, cfg, profile, candidate.source_regions),
        "editorial": editorial_signal(fields, cfg),
        "negative": negative_signal(fields, cfg, profile),
    }
