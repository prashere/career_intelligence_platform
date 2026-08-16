"""Apply parser_config.filters to discovered items."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.contracts import DiscoverItem


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns if p]


def apply_filters(items: list[DiscoverItem], filters: dict[str, Any] | None) -> list[DiscoverItem]:
    if not filters:
        return items

    include_link = _compile_patterns(filters.get("include_link_regex") or [])
    exclude_link = _compile_patterns(filters.get("exclude_link_regex") or [])
    require_link = _compile_patterns(filters.get("require_link_regex") or [])
    include_title = _compile_patterns(filters.get("include_title_regex") or [])

    result: list[DiscoverItem] = []
    for item in items:
        url = item.url or ""
        title = item.title or ""

        if require_link and not any(p.search(url) for p in require_link):
            continue
        if include_link and not any(p.search(url) for p in include_link):
            continue
        if exclude_link and any(p.search(url) for p in exclude_link):
            continue
        if include_title and not any(p.search(title) for p in include_title):
            continue
        result.append(item)
    return result
