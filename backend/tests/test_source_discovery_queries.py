"""Tests for discovery query fallback."""

from app.source_discovery.queries import _fallback_queries


def test_fallback_queries_cover_categories():
    ctx = {
        "target_fields": ["robotics"],
        "target_regions": ["Germany"],
        "target_degree": "PhD",
    }
    plan = _fallback_queries(ctx, 1)
    categories = {q.category for q in plan.queries}
    assert "aggregator" in categories
    assert "institutional" in categories
    assert "government_ngo" in categories
    assert "professional_association" in categories
