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

# Domains that can never act as a primary source: opportunity aggregators we
# ingest from, plus social and user-generated pages. Confirming a listing
# against one of these would just be the aggregator agreeing with itself.
NON_PRIMARY_DOMAINS = (
    "opportunitydesk.org",
    "opportunitiescorners.com",
    "opportunitiesforafricans.com",
    "opportunitiesforyouth.org",
    "profellow.com",
    "scholarshiptab.com",
    "scholarships.com",
    "scholarshiproar.com",
    "youthop.com",
    "youthopportunities.org",
    "globalsouthopportunities.com",
    "careerflora.com",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "reddit.com",
    "medium.com",
    "wikipedia.org",
    "t.me",
    "pinterest.com",
)


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


_ORG_STOPWORDS = {
    "the", "of", "and", "for", "in", "at", "a", "an", "to", "on",
    "program", "programme", "programs", "fellowship", "fellowships",
    "scholarship", "scholarships", "grant", "grants", "award", "awards",
    "opportunity", "opportunities", "international", "students", "student",
    "apply", "application", "applications", "call", "cohort", "edition",
}


def domain_matches_org(domain: str, org_name: str) -> bool:
    """True when a domain plausibly belongs to the named organization.

    Used to decide whether a page is the organization's own site rather than a
    third-party republisher, without relying on an ever-growing blocklist.
    """
    if not domain or not org_name:
        return False

    core = re.sub(r"[^a-z0-9]", "", domain.lower().rsplit(".", 1)[0])
    if not core:
        return False

    tokens = [
        t
        for t in re.split(r"[^a-z0-9]+", org_name.lower())
        if len(t) >= 4 and t not in _ORG_STOPWORDS and not t.isdigit()
    ]
    if not tokens:
        return False

    present = [t for t in tokens if t in core]
    if any(len(t) >= 8 for t in present):
        return True
    if len(present) >= 2:
        return True
    if len(tokens) >= 2 and (tokens[0] + tokens[1]) in core:
        return True
    return False


def is_non_primary_domain(domain: str) -> bool:
    """True for aggregator and social domains that cannot confirm a listing."""
    d = (domain or "").lower()
    if not d:
        return True
    return any(d == known or d.endswith(f".{known}") for known in NON_PRIMARY_DOMAINS)


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
