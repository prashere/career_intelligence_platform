"""Derive structured facts from opportunity title/summary text.

Ingestion often leaves degree_levels, countries, funding_type, tags and deadline
empty even though the listing text states them plainly. These deterministic
parsers recover those facts so ranking can explain itself. No LLM, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from dateutil import parser as date_parser

from app.models import Opportunity

_DEADLINE_LINE = re.compile(
    r"(?:application\s+)?(?:deadline|closing\s+date|apply\s+by|applications?\s+close)"
    r"\s*(?:is|on|:|\-|–)\s*([^\n\r.;]{2,60})",
    re.I,
)
_MONTH = (
    r"january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_DATE_IN_TEXT = re.compile(
    rf"\b(?:\d{{1,2}}\s+)?(?:{_MONTH})\.?(?:\s+\d{{1,2}}(?:st|nd|rd|th)?)?,?\s*(20\d{{2}})\b",
    re.I,
)
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_ROLLING_HINTS = ("rolling", "ongoing", "continuous", "no deadline", "open until filled")
_UNKNOWN_HINTS = ("unspecified", "not specified", "tbd", "to be announced", "varies", "n/a")

_MONEY = re.compile(r"(?:US)?\$\s?([\d,]{3,12})|€\s?([\d,]{3,12})|£\s?([\d,]{3,12})", re.I)

FULL_FUNDING_PHRASES = (
    "fully funded",
    "full funding",
    "fully-funded",
    "full scholarship",
    "tuition waiver",
    "tuition and living",
    "covers tuition",
    "all expenses paid",
    "all-expenses-paid",
    "free of charge",
)
PARTIAL_FUNDING_PHRASES = (
    "partial funding",
    "partial scholarship",
    "partially funded",
    "tuition support",
    "contribution towards",
    "travel grant",
)
SELF_FUNDING_PHRASES = (
    "self-funded",
    "self funded",
    "participants must cover",
    "at your own cost",
    "unpaid",
    "voluntary basis",
    "volunteer position",
)
STIPEND_PHRASES = ("stipend", "monthly allowance", "salary", "paid position", "honorarium", "remuneration")

DEGREE_PATTERNS: dict[str, tuple[str, ...]] = {
    "phd": ("phd", "ph.d", "doctoral", "doctorate", "postdoc", "post-doctoral"),
    "master": ("master", "masters", "master's", "msc", "m.sc", "graduate programme", "graduate program"),
    "undergraduate": ("undergraduate", "bachelor", "bachelor's", "bsc", "b.sc", "college student"),
    "high_school": ("high school", "secondary school", "sixth form"),
}

REGION_PATTERNS: dict[str, tuple[str, ...]] = {
    "Global": ("worldwide", "globally", "any country", "all nationalities", "international applicants", "global"),
    "Africa": ("africa", "african", "nigeria", "kenya", "ghana", "ethiopia", "south africa", "uganda"),
    "Asia": ("asia", "asian", "india", "nepal", "bangladesh", "pakistan", "japan", "china", "singapore"),
    "Europe": ("europe", "european", "germany", "france", "netherlands", "sweden", "italy", "spain", "poland"),
    "North America": ("united states", "usa", "u.s.", "canada", "american"),
    "United Kingdom": ("united kingdom", "uk ", "britain", "british", "england", "scotland"),
    "Latin America": ("latin america", "brazil", "mexico", "argentina", "colombia", "chile"),
    "Middle East": ("middle east", "uae", "qatar", "saudi", "jordan", "lebanon", "syria", "syrian"),
    "Oceania": ("australia", "new zealand"),
}

THEME_PATTERNS: dict[str, tuple[str, ...]] = {
    "technology": ("software", "engineering", "digital", "technology", "computing", "programming", "developer"),
    "artificial intelligence": ("artificial intelligence", " ai ", "machine learning", "deep learning", "nlp", "data science"),
    "research": ("research", "thesis", "dissertation", "publication", "laboratory", "academic"),
    "media": ("journalism", "media", "reporting", "storytelling", "communications", "broadcast"),
    "climate": ("climate", "environment", "sustainability", "renewable", "green", "conservation"),
    "health": ("health", "medical", "public health", "clinical", "medicine", "nursing"),
    "entrepreneurship": ("startup", "entrepreneur", "venture", "innovation", "business", "incubator"),
    "policy": ("policy", "governance", "diplomacy", "public administration", "development"),
    "human rights": ("human rights", "conflict", "peacebuilding", "humanitarian", "refugee", "advocacy"),
    "education": ("education", "teaching", "curriculum", "learning", "training", "mentorship"),
    "leadership": ("leadership", "ambassador", "fellowship programme", "leadership development"),
    "arts": ("arts", "creative", "design", "film", "music", "culture"),
}

FORMAT_PATTERNS: dict[str, tuple[str, ...]] = {
    "fellowship": ("fellowship", "fellow "),
    "scholarship": ("scholarship", "bursary", "studentship"),
    "internship": ("internship", "intern "),
    "bootcamp": ("bootcamp", "boot camp"),
    "competition": ("competition", "challenge", "hackathon"),
    "ambassador programme": ("ambassador programme", "ambassador program"),
    "exchange programme": ("exchange program", "cultural exchange"),
    "conference": ("conference", "summit", "symposium"),
    "grant": ("grant", "award", "prize"),
}

# "online" alone matches "apply online" on nearly every listing, so remote work
# has to be stated about the role itself.
REMOTE_PHRASES = (
    "fully remote",
    "work remotely",
    "remote position",
    "remote role",
    "remote work",
    "virtual programme",
    "virtual program",
    "work from home",
    "remotely from",
)
ONSITE_PHRASES = ("on-site", "onsite", "in person", "in-person", "relocate")


@dataclass
class OpportunityFacts:
    """Facts recovered from listing text, merged with any stored column values."""

    deadline: Optional[datetime] = None
    deadline_note: Optional[str] = None  # "rolling", "unspecified", or None
    deadline_source: str = "column"  # column | text | none
    funding_type: Optional[str] = None
    funding_evidence: Optional[str] = None
    funding_amount: Optional[str] = None
    degree_levels: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    remote: Optional[bool] = None
    text_length: int = 0

    @property
    def has_degree_info(self) -> bool:
        return bool(self.degree_levels)

    @property
    def has_funding_info(self) -> bool:
        return bool(self.funding_type)

    @property
    def has_deadline_info(self) -> bool:
        return self.deadline is not None or self.deadline_note is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "deadline_note": self.deadline_note,
            "deadline_source": self.deadline_source,
            "funding_type": self.funding_type,
            "funding_amount": self.funding_amount,
            "degree_levels": self.degree_levels,
            "regions": self.regions,
            "themes": self.themes,
            "formats": self.formats,
            "remote": self.remote,
        }


def _listing_text(opp: Opportunity) -> str:
    parts = [
        opp.title or "",
        opp.summary or "",
        " ".join(str(r) for r in (opp.requirements or [])),
        opp.institution or "",
        opp.program or "",
    ]
    return " ".join(parts)


def parse_deadline_from_text(text: str) -> tuple[Optional[datetime], Optional[str]]:
    """Return (deadline, note). note is 'rolling'/'unspecified' when no date exists."""
    match = _DEADLINE_LINE.search(text)
    candidate = match.group(1).strip() if match else ""

    if candidate:
        low = candidate.lower()
        if any(h in low for h in _ROLLING_HINTS):
            return None, "rolling"
        if any(h in low for h in _UNKNOWN_HINTS):
            return None, "unspecified"
        parsed = _try_parse_date(candidate)
        if parsed:
            return parsed, None

    iso = _ISO_DATE.search(text)
    if iso:
        parsed = _try_parse_date(iso.group(0))
        if parsed:
            return parsed, None

    inline = _DATE_IN_TEXT.search(text)
    if inline:
        parsed = _try_parse_date(inline.group(0))
        if parsed:
            return parsed, None

    if any(h in text.lower() for h in _ROLLING_HINTS):
        return None, "rolling"

    return None, None


def _try_parse_date(raw: str) -> Optional[datetime]:
    cleaned = re.sub(r"[^\w\s,/-]", " ", raw).strip()
    if not cleaned:
        return None
    try:
        parsed = date_parser.parse(cleaned, fuzzy=True, default=datetime(2026, 1, 1, tzinfo=timezone.utc))
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    # Reject nonsense years produced by fuzzy parsing.
    if parsed.year < 2020 or parsed.year > 2035:
        return None
    return parsed


def _detect_funding(text_low: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (funding_type, evidence_phrase, amount)."""
    amount = None
    money = _MONEY.search(text_low)
    if money:
        raw = next((g for g in money.groups() if g), None)
        if raw:
            amount = money.group(0).strip()

    for phrase in FULL_FUNDING_PHRASES:
        if phrase in text_low:
            return "full", phrase, amount
    for phrase in SELF_FUNDING_PHRASES:
        if phrase in text_low:
            return "self", phrase, amount
    for phrase in PARTIAL_FUNDING_PHRASES:
        if phrase in text_low:
            return "partial", phrase, amount
    for phrase in STIPEND_PHRASES:
        if phrase in text_low:
            return "stipend", phrase, amount
    if amount:
        return "award", f"award of {amount}", amount
    return None, None, None


def _detect_multi(text_low: str, patterns: dict[str, tuple[str, ...]], limit: int) -> list[str]:
    hits: list[str] = []
    for label, needles in patterns.items():
        if any(n in text_low for n in needles):
            hits.append(label)
        if len(hits) >= limit:
            break
    return hits


def derive_facts(opp: Opportunity) -> OpportunityFacts:
    """Merge stored columns with facts parsed from the listing text."""
    text = _listing_text(opp)
    text_low = text.lower()

    facts = OpportunityFacts(text_length=len(text.strip()))

    if opp.deadline:
        facts.deadline = opp.deadline if opp.deadline.tzinfo else opp.deadline.replace(tzinfo=timezone.utc)
        facts.deadline_source = "column"
    else:
        parsed, note = parse_deadline_from_text(text)
        facts.deadline = parsed
        facts.deadline_note = note
        facts.deadline_source = "text" if parsed else "none"

    if opp.funding_type:
        facts.funding_type = opp.funding_type
        facts.funding_evidence = "listed funding type"
        _, _, amount = _detect_funding(text_low)
        facts.funding_amount = amount
    else:
        facts.funding_type, facts.funding_evidence, facts.funding_amount = _detect_funding(text_low)

    stored_degrees = [str(d).lower() for d in (opp.degree_levels or [])]
    derived_degrees = _detect_multi(text_low, DEGREE_PATTERNS, limit=4)
    facts.degree_levels = list(dict.fromkeys(stored_degrees + derived_degrees))

    stored_regions = [str(c) for c in (opp.countries or [])]
    facts.regions = list(dict.fromkeys(stored_regions + _detect_multi(text_low, REGION_PATTERNS, limit=4)))

    stored_tags = [str(t).lower() for t in (opp.tags or [])]
    facts.themes = list(dict.fromkeys(stored_tags + _detect_multi(text_low, THEME_PATTERNS, limit=5)))

    # The title names the format far more reliably than the body text.
    title_low = (opp.title or "").lower()
    facts.formats = _detect_multi(title_low, FORMAT_PATTERNS, limit=2) or _detect_multi(
        text_low, FORMAT_PATTERNS, limit=2
    )

    if any(p in text_low for p in REMOTE_PHRASES):
        facts.remote = True
    elif any(p in text_low for p in ONSITE_PHRASES):
        facts.remote = False

    return facts


def apply_facts_to_opportunity(opp: Opportunity, facts: OpportunityFacts) -> list[str]:
    """Backfill empty columns from derived facts. Returns names of fields written."""
    written: list[str] = []

    if opp.deadline is None and facts.deadline is not None:
        opp.deadline = facts.deadline
        written.append("deadline")

    if not opp.funding_type and facts.funding_type:
        opp.funding_type = facts.funding_type
        written.append("funding_type")

    if not (opp.degree_levels or []) and facts.degree_levels:
        opp.degree_levels = facts.degree_levels
        written.append("degree_levels")

    if not (opp.countries or []) and facts.regions:
        opp.countries = facts.regions
        written.append("countries")

    if not (opp.tags or []) and facts.themes:
        opp.tags = facts.themes
        written.append("tags")

    return written
