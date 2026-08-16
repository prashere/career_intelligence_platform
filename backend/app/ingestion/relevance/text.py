"""Text normalisation and term matching for the relevance gate.

The old prefilter used naive `substring in text` checks, which both over-matched
("ai" inside "chair", "ms" inside "programs") and under-matched (no stemming, so
"Women in Tech" never hit a "technology" keyword). Everything here matches on
word boundaries and expands a small synonym table before comparing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Sequence

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s$€£%.,/+-]", re.UNICODE)

# Currency amounts such as "$10,000", "€5.000", "USD 25000", "up to £2,500".
_AMOUNT_RE = re.compile(
    r"(?:(?:us\$|\$|€|£|usd|eur|gbp|inr|chf|cad|aud)\s?\d[\d,.]*\d|\d[\d,.]*\d\s?(?:usd|eur|gbp|dollars?|euros?))",
    re.IGNORECASE,
)


def normalize(text: str | None) -> str:
    """Lowercase, strip accents and collapse punctuation to spaces."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_text.lower()
    spaced = _PUNCT_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", spaced).strip()


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern[str] | None:
    """Word-boundary pattern for a term, tolerating internal punctuation."""
    cleaned = normalize(term)
    if not cleaned:
        return None
    parts = [re.escape(p) for p in cleaned.split(" ") if p]
    if not parts:
        return None
    body = r"[\s\-/]*".join(parts)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def term_matches(term: str, normalized_text: str) -> bool:
    pattern = _term_pattern(term)
    return bool(pattern and pattern.search(normalized_text))


def find_terms(terms: Iterable[str], normalized_text: str, *, limit: int = 8) -> list[str]:
    """Return the subset of `terms` present in the text, preserving input order."""
    if not normalized_text:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not term:
            continue
        key = normalize(term)
        if not key or key in seen:
            continue
        if term_matches(term, normalized_text):
            seen.add(key)
            hits.append(term)
            if len(hits) >= limit:
                break
    return hits


def find_amounts(text: str, *, limit: int = 3) -> list[str]:
    """Monetary amounts are a strong funding signal that the old filter ignored."""
    if not text:
        return []
    out: list[str] = []
    for match in _AMOUNT_RE.finditer(text):
        value = match.group(0).strip()
        if value not in out:
            out.append(value)
        if len(out) >= limit:
            break
    return out


def expand_terms(terms: Sequence[str], synonyms: dict[str, list[str]]) -> list[str]:
    """Expand each term with its configured synonyms, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        key = normalize(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)

    for term in terms:
        if not term:
            continue
        _add(term)
        for synonym in synonyms.get(normalize(term), []):
            _add(synonym)
    return out


@dataclass
class TextFields:
    """Normalised view of everything known about a candidate item."""

    title: str = ""
    summary: str = ""
    content: str = ""
    url: str = ""

    _norm: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._norm = {
            "title": normalize(self.title),
            "summary": normalize(self.summary),
            "content": normalize(self.content),
            "url": normalize(self.url.replace("/", " ").replace("-", " ") if self.url else ""),
        }
        self._norm["all"] = " ".join(v for v in self._norm.values() if v)

    def normalized(self, field_name: str) -> str:
        return self._norm.get(field_name, "")

    @property
    def blob(self) -> str:
        return self._norm["all"]

    @property
    def raw_blob(self) -> str:
        return " ".join(p for p in (self.title, self.summary, self.content) if p)

    @property
    def text_length(self) -> int:
        """Characters of real prose, excluding the URL."""
        return len(self.title or "") + len(self.summary or "") + len(self.content or "")
