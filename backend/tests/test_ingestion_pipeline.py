"""Tests for ingestion envelope and extraction."""

from app.ingestion.envelope import default_envelope, merge_envelopes, passes_prefilter_item
from app.ingestion.extract.heuristic import extract_from_feed_item, should_fetch_detail


def test_prefilter_hard_drop():
    env = default_envelope()
    ok, reason = passes_prefilter_item("Webinar only event", "Join us", "https://x.com/a", env)
    assert not ok
    assert reason.startswith("hard_drop")


def test_prefilter_must_match():
    env = default_envelope()
    ok, _ = passes_prefilter_item("Generic news", "Nothing relevant", "https://x.com/a", env)
    assert not ok


def test_prefilter_passes_scholarship():
    env = default_envelope()
    ok, _ = passes_prefilter_item("Fully funded MSc scholarship", "Apply now", "https://x.com/a", env)
    assert ok


def test_merge_envelopes_intersects_hard_drop():
    a = {**default_envelope(), "hard_drop_any": ["webinar", "high school"]}
    b = {**default_envelope(), "hard_drop_any": ["webinar", "conference"]}
    merged = merge_envelopes([a, b])
    assert "webinar" in merged["hard_drop_any"]
    assert "high school" not in merged["hard_drop_any"]


def test_extract_from_feed_item():
    cfg = {"feed": {"strip_html": True}}
    extracted = extract_from_feed_item("PhD fellowship in AI", "Deadline: 1 Jan 2027", cfg)
    assert "fellowship" in extracted.title.lower() or extracted.opportunity_type == "fellowship"
    assert extracted.summary


def test_youthop_api_parses_custom_json():
    from app.ingestion.discover.strategies import probe_youthop_api

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "id": 1,
                    "title": "Test Fellowship 2026",
                    "has-deadline": True,
                    "deadline": 1786895940,
                    "category": {"name": "Fellowships", "link": "https://www.youthop.com/fellowships"},
                    "region": "USA",
                    "thumbnail": {
                        "medium": "https://static.youthop.com/uploads/2026/08/test-fellowship-2026-160x160.jpg"
                    },
                }
            ]

    class FakeClient:
        def get(self, url, params=None):
            return FakeResp()

    items = probe_youthop_api(FakeClient(), {"max_pages": 1})
    assert len(items) == 1
    assert "fellowship" in items[0].url
    assert items[0].title == "Test Fellowship 2026"


def test_merge_registry_fields_adds_parser_config():
    from app.ingestion.registry_config import merge_registry_fields

    entry = {
        "id": "scholars4dev",
        "name": "Scholars4Dev",
        "url": "https://www.scholars4dev.com/feed/",
        "source_type": "rss",
    }
    merged = merge_registry_fields(entry)
    discover = (merged.get("parser_config") or {}).get("discover") or {}
    assert discover.get("kind") == "rss"
    assert len(discover.get("feed_urls") or []) >= 2
    assert merged.get("adapter_id")


def test_resolve_parser_config_falls_back_to_registry():
    from app.ingestion.registry_config import resolve_parser_config

    pc = resolve_parser_config(
        parser_config={},
        registry_id="scholars4dev",
        source_url="https://www.scholars4dev.com/feed/",
    )
    discover = pc.get("discover") or {}
    assert len(discover.get("feed_urls") or []) >= 2


def test_resolve_parser_config_falls_back_to_source_url():
    from app.ingestion.registry_config import resolve_parser_config

    pc = resolve_parser_config(
        parser_config={},
        registry_id="unknown_source",
        source_url="https://example.com/feed/",
    )
    discover = pc.get("discover") or {}
    assert discover.get("feed_urls") == ["https://example.com/feed/"]


def test_tracer_emits_sequential_events():
    from app.ingestion.tracing import IngestionTracer
    from app.models.ingestion import TraceLevel

    class FakeSession:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

    session = FakeSession()
    tracer = IngestionTracer(session, run_id="run-1", source_id="src-1", source_name="Test")

    import asyncio

    async def _run():
        await tracer.emit("run", "run_start", "started")
        await tracer.strategy_attempt("rss", ok=True, item_count=5, filtered_count=5)
        await tracer.emit("discover", "discover_ok", "found items", count=5)

    asyncio.run(_run())
    assert len(session.rows) == 3
    assert session.rows[0].seq == 1
    assert session.rows[1].event == "strategy_attempt"
    assert session.rows[1].level == TraceLevel.info
