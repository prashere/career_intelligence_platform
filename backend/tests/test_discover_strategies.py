"""Unit tests for discover strategy probes (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.ingestion.discover.runner import validate_aggregator
from app.ingestion.discover.strategies import (
    probe_collegeboard_scholarships,
    probe_html,
    probe_html_paginated,
    probe_jina_html,
    probe_rss,
    probe_sitemap,
    probe_wp_json,
)
from app.services.profile_pipeline import load_source_registry


RSS_XML = b"""<?xml version="1.0"?>
<rss><channel>
<title>Test</title>
<item><title>Alpha Fellowship</title><link>https://www.profellow.com/fellowships/alpha/</link></item>
<item><title>Tips post</title><link>https://www.profellow.com/tips/ignore/</link></item>
</channel></rss>"""

DESK_RSS_XML = b"""<?xml version="1.0"?>
<rss><channel>
<item><title>Desk opp</title><link>https://opportunitydesk.org/2026/08/07/sample/</link></item>
</channel></rss>"""

HTML_LISTING = """
<html><body>
<h2 class="entry-title"><a href="/scholarships/foo-2026/">Foo Scholarship</a></h2>
<h2><a href="/scholarships/page/2/">Next</a></h2>
</body></html>
"""

SITEMAP = """<?xml version="1.0"?>
<urlset>
<loc>https://example.com/scholarships/foo-2026/</loc>
<loc>https://example.com/about/</loc>
</urlset>"""

PROFELLOW_SITEMAP = """<?xml version="1.0"?>
<urlset>
<loc>https://www.profellow.com/fellowship/alpha-fellowship/</loc>
<loc>https://www.profellow.com/tips/ignore/</loc>
</urlset>"""


def _mock_response(url: str, *, text: str = "", content: bytes = b"", status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.content = content or text.encode()
    resp.url = url
    resp.raise_for_status = MagicMock()

    def _json():
        return json.loads(text)

    resp.json = _json
    return resp


def test_probe_rss_dedupes_links():
    client = MagicMock()
    client.get.return_value = _mock_response(
        "https://feed.test/feed/",
        content=RSS_XML,
    )
    items = probe_rss(client, {"feed_urls": ["https://feed.test/feed/"], "max_entries": 10})
    assert len(items) == 2
    assert items[0].url.endswith("/fellowships/alpha/")


def test_probe_html_extracts_links():
    client = MagicMock()
    client.get.return_value = _mock_response(
        "https://example.com/scholarships/",
        text=HTML_LISTING,
    )
    items = probe_html(
        client,
        {
            "index_urls": ["https://example.com/scholarships/"],
            "link_selector": "h2 a",
            "max_items": 10,
        },
    )
    assert any("foo-2026" in i.url for i in items)


def test_probe_html_paginated_with_path_suffix():
    client = MagicMock()

    def _get(url, **kwargs):
        if "page/2" in url:
            return _mock_response(url, text="<html><a href='/scholarships/bar/'>Bar</a></html>")
        return _mock_response(url, text=HTML_LISTING)

    client.get.side_effect = _get
    items = probe_html_paginated(
        client,
        {
            "index_urls": ["https://example.com/scholarships/"],
            "pagination": {"path_suffix": "page/{page}/", "max_pages": 2},
            "link_selector": "a",
            "max_items": 20,
        },
    )
    urls = {i.url for i in items}
    assert any("foo-2026" in u for u in urls)
    assert any("bar" in u for u in urls)


def test_probe_sitemap_include_regex_list():
    client = MagicMock()
    client.get.return_value = _mock_response(
        "https://example.com/sitemap.xml",
        text=SITEMAP,
    )
    items = probe_sitemap(
        client,
        {
            "index_url": "https://example.com/sitemap.xml",
            "include_path_regex": ["/scholarships/[a-z0-9-]+/?$"],
            "max_urls": 10,
        },
    )
    assert len(items) == 1
    assert "foo-2026" in items[0].url


def test_probe_sitemap_jina_markdown_links():
    client = MagicMock()
    jina_body = (
        "Markdown Content:\n"
        "[https://www.profellow.com/fellowship/alpha/](https://www.profellow.com/fellowship/alpha/)\n"
        "2026-08-16\n"
        "[https://www.profellow.com/fellowship/beta/](https://www.profellow.com/fellowship/beta/)\n"
    )
    client.get.return_value = _mock_response(
        "https://r.jina.ai/https://www.profellow.com/fellowship-sitemap.xml",
        text=jina_body,
    )
    items = probe_sitemap(
        client,
        {
            "index_url": "https://www.profellow.com/fellowship-sitemap.xml",
            "proxy_prefix": "https://r.jina.ai/",
            "include_path_regex": "^https://www\\.profellow\\.com/fellowship/[a-z0-9-]+/$",
            "max_urls": 10,
        },
    )
    assert len(items) == 2
    assert items[0].title == "Alpha"


def test_probe_wp_json_parses_posts():
    client = MagicMock()
    payload = [
        {
            "link": "https://example.com/p/1",
            "title": {"rendered": "One"},
            "date": "2026-01-01",
            "excerpt": {"rendered": ""},
        }
    ]
    resp = _mock_response("https://example.com/wp-json/wp/v2/posts", text="[]")
    resp.json = MagicMock(return_value=payload)
    client.get.return_value = resp
    items = probe_wp_json(
        client,
        {"base_url": "https://example.com/wp-json/wp/v2/posts", "per_page": 10, "max_pages": 1},
    )
    assert len(items) == 1
    assert items[0].title == "One"


@pytest.mark.parametrize(
    "aggregator_id,rss_bytes",
    [
        ("opportunitydesk", DESK_RSS_XML),
        ("scholarships360", RSS_XML),
        ("opportunitiescorners", DESK_RSS_XML),
    ],
)
def test_registry_aggregator_passes_with_mocked_rss(
    aggregator_id: str, rss_bytes: bytes, monkeypatch: pytest.MonkeyPatch
):
    registry = load_source_registry()
    entry = next(a for a in registry["aggregators"] if a["id"] == aggregator_id)

    def fake_get(url, **kwargs):
        return _mock_response(url, content=rss_bytes)

    monkeypatch.setattr(
        "app.ingestion.discover.runner.make_client",
        lambda timeout=30: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None, get=fake_get),
    )
    result = validate_aggregator(entry, skip_browser=True)
    assert result.ok, result.errors


def test_profollow_filters_non_fellowship_links(monkeypatch: pytest.MonkeyPatch):
    registry = load_source_registry()
    entry = next(a for a in registry["aggregators"] if a["id"] == "profellow")

    def fake_get(url, **kwargs):
        if "jina.ai" in url:
            return _mock_response(
                url,
                text=(
                    "Markdown Content:\n"
                    "[https://www.profellow.com/fellowship/alpha-fellowship/]"
                    "(https://www.profellow.com/fellowship/alpha-fellowship/)\n"
                    "[https://www.profellow.com/tips/ignore/](https://www.profellow.com/tips/ignore/)\n"
                ),
            )
        return _mock_response(url, text=PROFELLOW_SITEMAP)

    monkeypatch.setattr(
        "app.ingestion.discover.runner.make_client",
        lambda timeout=30: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None, get=fake_get),
    )
    result = validate_aggregator(entry, skip_browser=True, timeout=90.0)
    assert result.ok
    assert result.filtered_items >= 1
    assert all("/fellowship/" in u and "/fellowships/" not in u for u in result.sample_urls)


def test_probe_collegeboard_scholarships():
    client = MagicMock()
    client.post.return_value = _mock_response(
        "https://scholarshipsearch-api.collegeboard.org/scholarships",
        text='{"data":[{"programTitleSlug":"alpha-scholarship","programName":"Alpha","openDate":"2026-01-01","blurb":"Test"}]}',
    )
    items = probe_collegeboard_scholarships(client, {})
    assert len(items) == 1
    assert items[0].url.endswith("/scholarships/alpha-scholarship")
    assert items[0].title == "Alpha"


def test_probe_jina_html_link_pattern():
    client = MagicMock()
    client.get.return_value = _mock_response(
        "https://r.jina.ai/https://example.com/",
        text=(
            "Markdown Content:\n"
            "[Detail](https://www.careeronestop.org/Toolkit/Training/"
            "find-scholarships-detail.aspx?curPage=1&scholarshipId=123)"
        ),
    )
    items = probe_jina_html(
        client,
        {
            "entry_urls": ["https://www.careeronestop.org/Toolkit/Training/find-scholarships.aspx"],
            "link_pattern": r"find-scholarships-detail\.aspx\?[^)\s]+",
            "url_base": "https://www.careeronestop.org/Toolkit/Training/",
        },
    )
    assert len(items) == 1
    assert "scholarshipId=123" in items[0].url


def test_probe_wp_json_via_jina_proxy():
    client = MagicMock()
    client.get.return_value = _mock_response(
        "https://r.jina.ai/https://scholarpositions.com/wp-json/wp/v2/posts",
        text=json.dumps(
            {
                "data": {
                    "content": json.dumps(
                        [
                            {
                                "link": "https://scholarpositions.com/sample-post/",
                                "title": {"rendered": "Sample"},
                                "date": "2026-01-01",
                                "excerpt": {"rendered": "Summary"},
                            }
                        ]
                    )
                }
            }
        ),
    )
    items = probe_wp_json(
        client,
        {
            "base_url": "https://scholarpositions.com/wp-json/wp/v2/posts",
            "proxy_prefix": "https://r.jina.ai/",
            "per_page": 5,
            "max_pages": 1,
        },
    )
    assert len(items) == 1
    assert items[0].url.endswith("/sample-post/")


def test_registry_list_normalizes_url_lists():
    from app.ingestion.playground import list_registry_aggregators

    rows = list_registry_aggregators()
    assert len(rows) >= 7
    for row in rows:
        assert isinstance(row["url"], (str, type(None)))
        if row["id"] == "opportunitydesk":
            assert row["url"] == "https://opportunitydesk.org/feed/"


def test_scholarpositions_passes_via_jina_wp_json(monkeypatch: pytest.MonkeyPatch):
    registry = load_source_registry()
    entry = next(a for a in registry["aggregators"] if a["id"] == "scholarpositions")

    def fake_get(url, **kwargs):
        return _mock_response(
            url,
            text=json.dumps(
                {
                    "data": {
                        "content": json.dumps(
                            [
                                    {
                                        "link": "https://scholarpositions.com/wipo-fellowship-2026-in-switzerland/",
                                    "title": {"rendered": "WIPO Fellowship"},
                                    "date": "2026-08-04",
                                    "excerpt": {"rendered": "Fully funded"},
                                }
                            ]
                        )
                    }
                }
            ),
        )

    monkeypatch.setattr(
        "app.ingestion.discover.runner.make_client",
        lambda timeout=30: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None, get=fake_get),
    )
    result = validate_aggregator(entry, skip_browser=True, timeout=90)
    assert result.ok
    assert result.winning_strategy == "wp_json"
    assert result.filtered_items >= 1
