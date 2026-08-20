"""Detect listing structure evidence on candidate pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.source_discovery.contracts import StructureEvidence

_RSS_LINK_RE = re.compile(r"application/(rss|atom)", re.I)
_DATE_IN_PATH_RE = re.compile(r"/20\d{2}/|/\d{4}-\d{2}-\d{2}")
_LISTING_PATH_RE = re.compile(
    r"(scholarship|fellowship|funding|opportunit|grant|program|vacancy|position)",
    re.I,
)


def analyze_page_structure(base_url: str, html: str) -> StructureEvidence:
    soup = BeautifulSoup(html, "lxml")
    evidence = StructureEvidence()

    for link in soup.find_all("link", href=True):
        typ = (link.get("type") or "").lower()
        rel = " ".join(link.get("rel") or []).lower()
        href = link["href"]
        if _RSS_LINK_RE.search(typ) or "alternate" in rel and "rss" in typ or href.endswith("/feed"):
            full = urljoin(base_url, href)
            evidence.has_rss_feed = True
            evidence.rss_urls.append(full)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc != urlparse(base_url).netloc:
            continue
        path = parsed.path or ""
        if _LISTING_PATH_RE.search(path) or _DATE_IN_PATH_RE.search(path):
            evidence.listing_link_count += 1
            if len(evidence.sample_listing_urls) < 8:
                evidence.sample_listing_urls.append(full)

    text_lower = soup.get_text(" ", strip=True).lower()
    if "next page" in text_lower or "pagination" in str(soup).lower():
        evidence.has_pagination = True
    if soup.select("nav a, .pagination a, .page-numbers a"):
        evidence.has_pagination = True
    if soup.select("ul.categories a, .category a, nav.menu a"):
        evidence.has_category_nav = True

    if evidence.listing_link_count >= 5:
        evidence.suggested_link_selector = "article h2 a, h2.entry-title a, .post-title a, main a"

    return evidence


def has_recurring_structure(evidence: StructureEvidence) -> bool:
    if evidence.has_rss_feed and evidence.rss_urls:
        return True
    if evidence.listing_link_count >= 5:
        return True
    if evidence.listing_link_count >= 3 and (evidence.has_pagination or evidence.has_category_nav):
        return True
    return False
