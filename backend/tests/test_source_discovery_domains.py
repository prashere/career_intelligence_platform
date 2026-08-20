"""Tests for source discovery domain utilities."""

from app.source_discovery.domains import (
    is_likely_article_url,
    normalize_registrable_domain,
    score_domain_candidate,
)


def test_normalize_registrable_domain_strips_www():
    assert normalize_registrable_domain("https://www.example.edu/funding") == "example.edu"


def test_is_likely_article_url_deep_path():
    assert is_likely_article_url("https://uni.edu/fellowship/fully-funded-phd-2026")


def test_institutional_domain_scores_higher():
    inst = score_domain_candidate("mit.edu", "graduate funding scholarships", "MIT Funding")
    agg = score_domain_candidate("random-blog.com", "graduate funding scholarships", "MIT Funding")
    assert inst > agg
