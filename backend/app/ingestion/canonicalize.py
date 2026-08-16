"""Canonicalize URLs and field normalization."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def canonicalize_url(url: str, parser_config: dict[str, Any] | None = None) -> str:
    if not url:
        return url
    parsed = urlparse(url.strip())
    strip_params = []
    if parser_config:
        canonical = parser_config.get("canonical") or {}
        strip_params = canonical.get("strip_query_params") or []

    qs = parse_qs(parsed.query, keep_blank_values=False)
    for param in strip_params:
        qs.pop(param, None)
    clean_query = urlencode({k: v[0] for k, v in qs.items() if v}, doseq=False)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") or "/", "", clean_query, ""))
