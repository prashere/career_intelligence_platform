"""Tests for profile-driven opportunity_sources selection helpers."""

from app.models import OpportunitySource, SourceType
from app.services.profile_source_seeding import _selection_keys, _source_matches_selection


def test_selection_keys_from_ingestion_sources():
    sources = [
        {"id": "opportunitydesk", "url": "https://opportunitydesk.org/feed/"},
        {"id": "youthop", "url": "https://www.youthop.com/feed/"},
    ]
    registry_ids, urls = _selection_keys(sources)
    assert registry_ids == {"opportunitydesk", "youthop"}
    assert "https://opportunitydesk.org/feed/" in urls
    assert "https://www.youthop.com/feed/" in urls


def test_source_matches_selection_excludes_stale_seed_rows():
    sources = [{"id": "profellow", "url": "https://www.profellow.com/fellowship/"}]
    registry_ids, urls = _selection_keys(sources)

    daad = OpportunitySource(
        name="DAAD Scholarships RSS",
        url="https://www.daad.de/en/rss/rss.xml",
        source_type=SourceType.rss,
        is_active=True,
    )
    scholars = OpportunitySource(
        name="Scholars4Dev",
        url="https://www.scholars4dev.com/feed/",
        source_type=SourceType.rss,
        is_active=True,
    )
    profellow = OpportunitySource(
        name="ProFellow",
        url="https://www.profellow.com/fellowship/",
        source_type=SourceType.html,
        is_active=True,
        registry_id="profellow",
    )

    assert not _source_matches_selection(daad, registry_ids, urls)
    assert not _source_matches_selection(scholars, registry_ids, urls)
    assert _source_matches_selection(profellow, registry_ids, urls)
