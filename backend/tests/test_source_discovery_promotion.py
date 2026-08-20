"""Tests for source discovery promotion validation."""

import pytest

from app.source_discovery.promotion import _validate_registry_entry


def test_validate_registry_entry_requires_discover():
    with pytest.raises(ValueError, match="parser_config.discover"):
        _validate_registry_entry(
            {
                "id": "test",
                "name": "Test",
                "url": "https://example.edu/feed",
                "type": "rss",
                "parser_config": {"version": 1},
            }
        )


def test_validate_registry_entry_accepts_rss():
    _validate_registry_entry(
        {
            "id": "test",
            "name": "Test",
            "url": "https://example.edu/feed",
            "type": "rss",
            "parser_config": {
                "version": 1,
                "discover": {"kind": "rss", "feed_urls": ["https://example.edu/feed"]},
            },
        }
    )
