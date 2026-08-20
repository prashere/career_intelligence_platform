"""Domain normalization and deduplication for source discovery."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.verification.domain_utils import extract_domain, is_institutional_domain, is_non_primary_domain

_ARTICLE_PATH_RE = re.compile(
    r"/(blog|news|article|post|fellowship|scholarship|grant|opportunity)/[^/]+/?$",
    re.I,
)


def normalize_registrable_domain(url: str) -> str | None:
    domain = extract_domain(url)
    if not domain:
        return None
    parts = domain.split(".")
    if len(parts) >= 2 and parts[0] == "www":
        domain = ".".join(parts[1:])
    return domain.lower()


def is_likely_article_url(url: str) -> bool:
    path = urlparse(url).path or ""
    if len(path) > 80 and path.count("/") >= 3:
        return True
    return bool(_ARTICLE_PATH_RE.search(path))


def score_domain_candidate(domain: str, snippet: str, title: str) -> float:
    score = 0.0
    text = f"{title} {snippet}".lower()
    if is_institutional_domain(domain):
        score += 0.35
    if any(t in domain for t in (".edu", ".gov", ".org")):
        score += 0.1
    if is_non_primary_domain(domain):
        score -= 0.25
    listing_terms = ("scholarship", "fellowship", "funding", "graduate", "phd", "opportunities", "grants")
    score += min(0.3, sum(0.05 for t in listing_terms if t in text))
    if "listing" in text or "database" in text or "search" in text:
        score += 0.1
    return max(0.0, min(1.0, score))


def pick_best_url_for_domain(url: str, title: str, snippet: str) -> str:
    """Prefer site root or section listing over deep article paths when possible."""
    parsed = urlparse(url)
    if not is_likely_article_url(url):
        return url
    root = f"{parsed.scheme}://{parsed.netloc}/"
    return root
