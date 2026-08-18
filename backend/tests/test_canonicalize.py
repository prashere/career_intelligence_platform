"""Tests for URL canonicalization (Task 4)."""

from app.ingestion.canonicalize import canonicalize_url


def test_canonicalize_strips_www_and_query():
    url = "https://www.Example.com/path/?utm_source=x"
    out = canonicalize_url(url, {"canonical": {"strip_query_params": ["utm_source"]}})
    assert out == "https://example.com/path"
