"""Detect editorial content — listicles, guides, reviews, hub pages.

These pages mention scholarships constantly but are not a single applyable
opportunity. They were scoring highly on opportunity_type + funding alone.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Sequence

from app.ingestion.relevance.text import TextFields, normalize

# Title/summary patterns → hard reject. Order matters for evidence strings.
DEFAULT_EDITORIAL_TITLE_PATTERNS: list[str] = [
    r"^top\s+\d+",
    r"^best\s+\d+",
    r"\bultimate guide\b",
    r"\bcomplete guide\b",
    r"\beverything you need to know\b",
    r"\bfully funded\b.*\b(programs|programmes)\s+in\b",
    r"\b(master|masters|msc|ma|phd|doctoral)\s+(programs|programmes)\s+in\b",
    r"\b(programs|programmes)\s+in\s+[a-z]",  # field roundup, not "program in partnership"
    r"\bquick apply scholarships\b",
    r"\beasy scholarships to apply\b",
    r"\bscholarships to apply for\b",
    r"\b\d+\s+(easy|quick|best|top)\s+scholarships\b",
    r"\bscholarships from\b",
    r"\bfellowships in \d{4} for\b",
    r"\bfor students professionals and\b",
    r"\btechnology policy fellowships in \d{4}\b",
    r"\btest page\b",
    r"\bsample test\b",
    r"\bpeople's reviews\b",
    r"\buser reviews\b",
    r"\bstudent reviews\b",
    r"\breviews of\b",
    r"\bwrite a review\b",
    r"\bhow i\b",  # blog: "How I passed my IELTS"
    r"\btips for\b",
    r"\bwhat is a\b.*\bscholarship\b",
]

DEFAULT_EDITORIAL_URL_PATTERNS: list[str] = [
    r"/reviews?/",
    r"quick-apply-scholarships",
    r"/scholarship-search",
    r"/scholarship-list",
    r"/blog/",
    r"/category/",
    r"/tag/",
    r"/advertise",
    r"/research/",
]

# When the title is clearly a named single opportunity, do not treat field
# roundup patterns in the body as editorial.
_SINGLE_OPP_TITLE_HINTS: list[str] = [
    r"\bscholarship\s+\d{4}\b",
    r"\bfellowship\s+\d{4}\b",
    r"\b(up to|worth)\s+[\$€£]",
    r"\bapply (now|by|before)\b",
    r"\bdeadline\b",
    r"\b(project|program|programme|initiative)\s+\d{4}\b",
    r"\b\w+\s+award\b",
    r"\b\w+\s+scholarship\b",
    r"\b\w+\s+fellowship\b",
]


@lru_cache(maxsize=64)
def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    out: list[re.Pattern[str]] = []
    for raw in patterns:
        try:
            out.append(re.compile(raw, re.IGNORECASE))
        except re.error:
            continue
    return tuple(out)


def _first_match(text: str, patterns: Sequence[re.Pattern[str]]) -> str | None:
    if not text:
        return None
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()[:60]
    return None


def title_looks_like_single_opportunity(title: str) -> bool:
    """Named listing with a year, amount, or explicit apply/deadline language."""
    norm = normalize(title)
    if not norm:
        return False
    # Long plural headlines are almost always roundups.
    if re.search(r"\b(scholarships|fellowships|programs|programmes)\b", norm):
        if re.search(r"^(top|best)\s+\d+", norm):
            return False
        if re.search(r"\b(programs|programmes)\s+in\b", norm):
            return False
        if re.search(r"\b\d+\s+(easy|quick|best|top)\s+scholarships\b", norm):
            return False
    hints = _compile_patterns(tuple(_SINGLE_OPP_TITLE_HINTS))
    return _first_match(norm, hints) is not None


def detect_editorial(
    fields: TextFields,
    *,
    title_patterns: Sequence[str] | None = None,
    url_patterns: Sequence[str] | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Returns (matched, evidence, found_in).

    Title and summary are checked for editorial phrasing. URL paths catch hub
    pages even when the title is empty (e.g. Bold sitemap entries).
    """
    title_pats = _compile_patterns(tuple(title_patterns or DEFAULT_EDITORIAL_TITLE_PATTERNS))
    url_pats = _compile_patterns(tuple(url_patterns or DEFAULT_EDITORIAL_URL_PATTERNS))

    headline = " ".join(p for p in (fields.normalized("title"), fields.normalized("summary")) if p)
    single_opp = title_looks_like_single_opportunity(fields.title or "")

    if headline and not single_opp:
        hit = _first_match(headline, title_pats)
        if hit:
            where = "title" if _first_match(fields.normalized("title"), title_pats) else "summary"
            return True, hit, where

    url_norm = fields.normalized("url")
    if url_norm:
        hit = _first_match(url_norm.replace(" ", "/"), url_pats)
        if hit and not single_opp:
            return True, hit, "url"

    # WordPress draft/test posts: ?p= numeric id with generic title
    raw_url = (fields.url or "").lower()
    title_norm = fields.normalized("title")
    if "?p=" in raw_url and (
        not title_norm
        or title_norm in ("test page", "sample test")
        or len(title_norm.split()) <= 3
    ):
        return True, "wordpress draft url", "url"

    return False, None, None
