"""Tests for recurring structure detection."""

from app.source_discovery.contracts import StructureEvidence
from app.source_discovery.structure import analyze_page_structure, has_recurring_structure


def test_has_recurring_structure_rss():
    evidence = StructureEvidence(has_rss_feed=True, rss_urls=["https://example.edu/feed"])
    assert has_recurring_structure(evidence)


def test_has_recurring_structure_listing_links():
    evidence = StructureEvidence(listing_link_count=6)
    assert has_recurring_structure(evidence)


def test_analyze_page_structure_finds_rss():
    html = """
    <html><head>
    <link rel="alternate" type="application/rss+xml" href="/feed" />
    </head><body>
    <a href="/scholarships/phd-2026">PhD</a>
    <a href="/scholarships/msc-2026">MSc</a>
  </body></html>
    """
    evidence = analyze_page_structure("https://example.edu/", html)
    assert evidence.has_rss_feed
    assert evidence.listing_link_count >= 1
