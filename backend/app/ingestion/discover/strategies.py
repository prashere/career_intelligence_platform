"""Discover strategy implementations for registry validation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.ingestion.contracts import DiscoverItem

DEFAULT_JINA_PREFIX = "https://r.jina.ai/"
COLLEGEBOARD_SCHOLARSHIP_HEADERS = {
    "Origin": "https://bigfuture.collegeboard.org",
    "Referer": "https://bigfuture.collegeboard.org/scholarship-search",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _jina_proxy_url(target_url: str, proxy_prefix: str | None = None) -> str:
    prefix = (proxy_prefix or DEFAULT_JINA_PREFIX).rstrip("/") + "/"
    return prefix + target_url.lstrip("/")


def _jina_markdown_body(text: str) -> str:
    if "Markdown Content:" in text:
        return text.split("Markdown Content:", 1)[1].strip()
    return text


def _fetch_jina_text(client: httpx.Client, target_url: str, *, proxy_prefix: str | None = None) -> str:
    response = client.get(
        _jina_proxy_url(target_url, proxy_prefix),
        headers={"User-Agent": "Mozilla/5.0 CareerIntelligence/1.0", "Accept": "text/plain"},
    )
    response.raise_for_status()
    return response.text


def _fetch_jina_json(client: httpx.Client, target_url: str, *, proxy_prefix: str | None = None) -> Any:
    response = client.get(
        _jina_proxy_url(target_url, proxy_prefix),
        headers={"User-Agent": "Mozilla/5.0 CareerIntelligence/1.0", "Accept": "application/json"},
    )
    response.raise_for_status()
    wrapper = response.json()
    content = ((wrapper.get("data") or {}).get("content")) if isinstance(wrapper, dict) else None
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(wrapper, list):
        return wrapper
    return wrapper


def _slug_from_youthop_thumbnail(thumbnail: dict[str, Any]) -> str:
    for key in ("thumbnail-square", "medium", "full"):
        url = thumbnail.get(key) or ""
        if not url:
            continue
        name = url.rsplit("/", 1)[-1]
        name = re.sub(r"-\d+x\d+(?=\.\w+$)", "", name)
        name = re.sub(r"\.\w+$", "", name)
        if name:
            return name
    return ""


def _youthop_post_url(row: dict[str, Any]) -> str:
    if row.get("link"):
        return str(row["link"]).strip()
    category = row.get("category") or {}
    base = str(category.get("link") or "https://www.youthop.com/").rstrip("/")
    slug = row.get("slug") or _slug_from_youthop_thumbnail(row.get("thumbnail") or {})
    if slug:
        return f"{base}/{slug}/"
    return ""


def _youthop_summary(row: dict[str, Any]) -> str:
    parts = []
    if row.get("region"):
        parts.append(f"Region: {row['region']}")
    if row.get("has-deadline") and row.get("deadline"):
        try:
            ts = int(row["deadline"])
            parts.append(f"Deadline: {datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()}")
        except (TypeError, ValueError, OSError):
            pass
    category = row.get("category") or {}
    if category.get("name"):
        parts.append(str(category["name"]))
    return " · ".join(parts)


def probe_youthop_api(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    """YouthOp custom REST list — works over plain HTTP (no browser)."""
    base_url = config.get("base_url") or "https://www.youthop.com/wp-json/wp/v2/posts"
    per_page = int(config.get("per_page") or 50)
    max_pages = int(config.get("max_pages") or 2)
    items: list[DiscoverItem] = []

    for page in range(1, max_pages + 1):
        response = client.get(base_url, params={"per_page": per_page, "page": page})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            url = _youthop_post_url(row)
            if not url:
                continue
            title = row.get("title") or {}
            if isinstance(title, dict):
                title_text = str(title.get("rendered") or "")
            else:
                title_text = str(title)
            items.append(
                DiscoverItem(
                    url=url,
                    title=title_text,
                    published=str(row.get("date") or ""),
                    summary=_youthop_summary(row),
                    source_strategy="youthop_api",
                )
            )
    return dedupe_items(items)


def dedupe_items(items: list[DiscoverItem], key: str = "link") -> list[DiscoverItem]:
    seen: set[str] = set()
    out: list[DiscoverItem] = []
    for item in items:
        if key == "link":
            k = item.url.strip().lower()
        else:
            k = item.url.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


def probe_rss(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    feed_urls = config.get("feed_urls") or []
    max_entries = int(config.get("max_entries") or 50)
    items: list[DiscoverItem] = []
    for feed_url in feed_urls:
        try:
            response = client.get(feed_url)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            for entry in parsed.entries[:max_entries]:
                link = str(entry.get("link") or "").strip()
                if not link:
                    continue
                items.append(
                    DiscoverItem(
                        url=link,
                        title=str(entry.get("title") or "").strip(),
                        published=str(entry.get("published") or entry.get("updated") or ""),
                        summary=str(entry.get("summary") or entry.get("description") or ""),
                        source_strategy="rss",
                    )
                )
        except Exception:
            if not config.get("fallback_on_http_error"):
                raise
            continue
    dedupe_by = config.get("dedupe_by") or "link"
    return dedupe_items(items, dedupe_by)


def probe_html(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    index_urls = config.get("index_urls") or config.get("entry_urls") or []
    link_selector = config.get("link_selector") or "a"
    title_selector = config.get("title_selector") or "h2, h3"
    max_items = int(config.get("max_items") or config.get("max_entries") or 80)
    items: list[DiscoverItem] = []

    for index_url in index_urls:
        response = client.get(index_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        for anchor in soup.select(link_selector):
            href = anchor.get("href")
            if not href:
                continue
            url = urljoin(str(response.url), href)
            if not url.startswith("http"):
                continue
            title = anchor.get_text(" ", strip=True)
            if not title:
                parent = anchor.find_parent(title_selector.split(",")[0].strip())
                if parent:
                    title = parent.get_text(" ", strip=True)
            items.append(DiscoverItem(url=url, title=title, source_strategy="html"))
            if len(items) >= max_items:
                break
        if len(items) >= max_items:
            break
    return dedupe_items(items)


def probe_html_paginated(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    items: list[DiscoverItem] = []

    index_urls = config.get("index_urls") or config.get("entry_urls") or []
    pagination = config.get("pagination") or {}
    path_suffix = pagination.get("path_suffix")
    max_pages = int(pagination.get("max_pages") or 1)

    if index_urls:
        for index_url in index_urls:
            pages = [index_url]
            if path_suffix:
                base = index_url if index_url.endswith("/") else f"{index_url}/"
                pages.extend(base + path_suffix.format(page=p) for p in range(2, max_pages + 1))
            for page_url in pages:
                page_items = probe_html(
                    client,
                    {
                        **config,
                        "index_urls": [page_url],
                        "max_items": config.get("max_items") or 80,
                    },
                )
                items.extend(page_items)
        return dedupe_items(items)

    base_url = config.get("base_url") or ""
    query_params: dict[str, str] = dict(config.get("query_params") or {})
    pagination = config.get("pagination") or {}
    param = pagination.get("param") or "page"
    start = int(pagination.get("start") or 1)
    max_pages = int(pagination.get("max_pages") or 1)
    link_pattern = config.get("link_pattern")
    detail_template = config.get("detail_url_template") or ""
    link_selector = config.get("link_selector")
    title_selector = config.get("title_selector") or "h2, h3, a"

    for page in range(start, start + max_pages):
        params = {**query_params, param: str(page)}
        retries = int(config.get("retry_connect") or 0)
        last_exc: Exception | None = None
        text = ""
        for attempt in range(retries + 1):
            try:
                response = client.get(base_url, params=params)
                response.raise_for_status()
                text = response.text
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= retries:
                    raise
        if last_exc:
            raise last_exc

        if link_pattern:
            ids = sorted(set(re.findall(link_pattern, text)))
            for detail_id in ids:
                url = detail_template.format(id=detail_id) if detail_template else ""
                if not url and link_selector:
                    continue
                if not url:
                    parsed = urlparse(str(response.url))
                    url = urlunparse(parsed._replace(query=f"detail={detail_id}"))
                items.append(DiscoverItem(url=url, title="", source_strategy="html_paginated"))
        elif link_selector:
            soup = BeautifulSoup(text, "lxml")
            for anchor in soup.select(link_selector):
                href = anchor.get("href")
                if not href:
                    continue
                url = urljoin(str(response.url), href)
                title = anchor.get_text(" ", strip=True)
                items.append(DiscoverItem(url=url, title=title, source_strategy="html_paginated"))

        if not link_pattern and not link_selector:
            soup = BeautifulSoup(text, "lxml")
            for anchor in soup.select(title_selector):
                href = anchor.get("href") if anchor.name == "a" else None
                if href:
                    url = urljoin(str(response.url), href)
                    items.append(
                        DiscoverItem(
                            url=url,
                            title=anchor.get_text(" ", strip=True),
                            source_strategy="html_paginated",
                        )
                    )

    return dedupe_items(items, config.get("dedupe_by") or "link")


def _resolve_category_ids(client: httpx.Client, categories: dict[str, Any]) -> list[int]:
    resolve_from = categories.get("resolve_from")
    slugs = categories.get("slugs") or []
    if not resolve_from or not slugs:
        return list(categories.get("ids") or [])

    response = client.get(resolve_from, params={"per_page": 100})
    response.raise_for_status()
    data = response.json()
    slug_set = {s.lower() for s in slugs}
    ids: list[int] = []
    for row in data:
        slug = str(row.get("slug") or "").lower()
        if slug in slug_set:
            ids.append(int(row["id"]))
    return ids


def _discover_item_from_wp_row(row: dict[str, Any], *, source_strategy: str) -> DiscoverItem | None:
    link = str(row.get("link") or "").strip()
    if not link:
        return None
    title = row.get("title") or {}
    if isinstance(title, dict):
        title_text = str(title.get("rendered") or "")
    else:
        title_text = str(title)
    excerpt = row.get("excerpt") or {}
    summary = excerpt.get("rendered", "") if isinstance(excerpt, dict) else str(excerpt)
    return DiscoverItem(
        url=link,
        title=title_text,
        published=str(row.get("date") or ""),
        summary=summary,
        source_strategy=source_strategy,
    )


def probe_wp_json(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    base_url = config.get("base_url") or ""
    per_page = int(config.get("per_page") or 50)
    max_pages = int(config.get("max_pages") or 1)
    proxy_prefix = config.get("proxy_prefix")
    items: list[DiscoverItem] = []

    category_ids: list[int] = []
    if config.get("categories"):
        category_ids = _resolve_category_ids(client, config["categories"])

    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if category_ids:
            params["categories"] = ",".join(str(i) for i in category_ids)
        if proxy_prefix:
            query = urlencode_params(params)
            target = f"{base_url}?{query}" if query else base_url
            rows = _fetch_jina_json(client, target, proxy_prefix=proxy_prefix)
        else:
            response = client.get(base_url, params=params)
            response.raise_for_status()
            rows = response.json()
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            item = _discover_item_from_wp_row(row, source_strategy="jina_wp_json" if proxy_prefix else "wp_json")
            if item:
                items.append(item)
    return dedupe_items(items)


def urlencode_params(params: dict[str, Any]) -> str:
    return urlencode({k: str(v) for k, v in params.items()})


def title_from_url_slug(url: str) -> str:
    """Humanize the last path segment for sitemap-only discover rows."""
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    slug = path.rsplit("/", 1)[-1]
    if not slug or slug in {"fellowship", "fellowships", "scholarships"}:
        return ""
    return slug.replace("-", " ").strip().title()


def _loc_urls_from_sitemap_text(text: str) -> list[str]:
    locs = re.findall(r"<loc>([^<]+)</loc>", text)
    if locs:
        return locs
    body = _jina_markdown_body(text) if "Markdown Content:" in text else text
    links = re.findall(r"\((https?://[^)]+)\)", body)
    if not links:
        links = re.findall(r"https?://[^\s\])\"'<>]+", body)
    seen: set[str] = set()
    ordered: list[str] = []
    for link in links:
        cleaned = link.split("#", 1)[0].strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


def _fetch_sitemap_xml(client: httpx.Client, url: str, config: dict[str, Any]) -> str:
    proxy_prefix = config.get("proxy_prefix")
    if proxy_prefix:
        return _fetch_jina_text(client, url, proxy_prefix=proxy_prefix)
    response = client.get(url)
    response.raise_for_status()
    return response.text


def probe_sitemap(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    index_url = config.get("index_url") or ""
    include_pattern = config.get("include_path_regex")
    max_urls = int(config.get("max_urls") or 100)
    patterns = include_pattern if isinstance(include_pattern, list) else ([include_pattern] if include_pattern else [])
    include_res = [re.compile(p) for p in patterns if p]
    items: list[DiscoverItem] = []
    strategy = "jina_sitemap" if config.get("proxy_prefix") else "sitemap"

    text = _fetch_sitemap_xml(client, index_url, config)
    locs = _loc_urls_from_sitemap_text(text)

    # Follow nested sitemaps (post-sitemap, etc.)
    nested = [loc for loc in locs if loc.endswith(".xml")]
    content_locs = [loc for loc in locs if loc not in nested]

    for nested_url in nested[:5]:
        try:
            nested_text = _fetch_sitemap_xml(client, nested_url, config)
            content_locs.extend(_loc_urls_from_sitemap_text(nested_text))
        except Exception:
            continue

    for loc in content_locs:
        if include_res and not any(r.search(loc) for r in include_res):
            continue
        title = title_from_url_slug(loc)
        items.append(DiscoverItem(url=loc, title=title, source_strategy=strategy))
        if len(items) >= max_urls:
            break
    return dedupe_items(items)


def _absolute_url(raw: str, base_url: str) -> str:
    cleaned = raw.strip().strip('"').strip("'")
    if cleaned.startswith("http"):
        url = cleaned.split('"', 1)[0].split("'", 1)[0].strip()
    else:
        url = urljoin(base_url, cleaned)
    return url.split("#", 1)[0]


def probe_jina_html(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    """Fetch bot-protected HTML listings through the Jina reader proxy."""
    entry_urls = config.get("entry_urls") or config.get("index_urls") or []
    link_selector = config.get("link_selector")
    link_pattern = config.get("link_pattern")
    url_base = config.get("url_base") or ""
    max_items = int(config.get("max_items") or config.get("max_entries") or 80)
    proxy_prefix = config.get("proxy_prefix") or DEFAULT_JINA_PREFIX
    pagination = config.get("pagination") or {}
    max_pages = int(pagination.get("max_pages") or 1)
    page_param = pagination.get("param") or "curPage"
    page_start = int(pagination.get("start") or 1)
    items: list[DiscoverItem] = []

    for entry_url in entry_urls:
        pages = [entry_url]
        if max_pages > 1:
            sep = "&" if "?" in entry_url else "?"
            pages = [entry_url] + [
                f"{entry_url}{sep}{page_param}={page_num}"
                for page_num in range(page_start + 1, page_start + max_pages)
            ]
        for page_url in pages:
            text = _fetch_jina_text(client, page_url, proxy_prefix=proxy_prefix)
            body = _jina_markdown_body(text)
            base = url_base or page_url
            if link_pattern:
                pattern = re.compile(link_pattern)
                for match in pattern.findall(body):
                    url = _absolute_url(match, base)
                    items.append(DiscoverItem(url=url, title="", source_strategy="jina_html"))
            if link_selector:
                soup = BeautifulSoup(body, "lxml")
                for anchor in soup.select(link_selector):
                    href = anchor.get("href")
                    if not href:
                        continue
                    url = _absolute_url(href, base)
                    title = anchor.get_text(" ", strip=True)
                    items.append(DiscoverItem(url=url, title=title, source_strategy="jina_html"))
            if len(items) >= max_items:
                break
        if len(items) >= max_items:
            break
    return dedupe_items(items[:max_items])


def probe_collegeboard_scholarships(client: httpx.Client, config: dict[str, Any]) -> list[DiscoverItem]:
    """BigFuture scholarship search JSON API (College Board)."""
    api_url = config.get("api_url") or "https://scholarshipsearch-api.collegeboard.org/scholarships"
    body = dict(
        config.get("body")
        or {"pageSize": 50, "pageNumber": 0, "sortBy": "DEADLINE_ASC"}
    )
    url_template = (
        config.get("url_template") or "https://bigfuture.collegeboard.org/scholarships/{slug}"
    )
    headers = {**COLLEGEBOARD_SCHOLARSHIP_HEADERS, **(config.get("headers") or {})}
    response = client.post(api_url, json=body, headers=headers)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    items: list[DiscoverItem] = []
    for row in rows:
        slug = str(row.get("programTitleSlug") or "").strip()
        if not slug:
            continue
        items.append(
            DiscoverItem(
                url=url_template.format(slug=slug),
                title=str(row.get("programName") or "").strip(),
                published=str(row.get("openDate") or row.get("closeDate") or ""),
                summary=str(row.get("blurb") or row.get("programSelfDescription") or ""),
                source_strategy="collegeboard_scholarships",
            )
        )
    return dedupe_items(items)
