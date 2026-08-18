"""URL and domain helpers for verification."""

from __future__ import annotations

import re
from urllib.parse import urlparse

INSTITUTIONAL_TLD_PATTERNS = (
    ".edu",
    ".ac.uk",
    ".ac.jp",
    ".ac.nz",
    ".ac.za",
    ".gov",
    ".gov.uk",
    ".gouv.",
)

ALLOWLIST_DOMAINS_SUFFIX = INSTITUTIONAL_TLD_PATTERNS


def normalize_org_key(name: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", (name or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()[:255]


def extract_domain(url: str) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or parsed.path).lower()
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def is_institutional_domain(domain: str) -> bool:
    if not domain:
        return False
    d = domain.lower()
    return any(token in d for token in INSTITUTIONAL_TLD_PATTERNS)


def domain_from_url(url: str) -> str | None:
    return extract_domain(url)


def guess_org_name(title: str, institution: str | None, summary: str | None) -> str:
    if institution and len(institution.strip()) > 2:
        return institution.strip()
    # Strip common opportunity suffixes from title
    t = (title or "").strip()
    for suffix in (" - Scholarship", " Scholarship", " Fellowship", " PhD", " MSc"):
        if suffix.lower() in t.lower():
            t = t.split(suffix)[0]
    return t[:255] if t else "Unknown organization"
