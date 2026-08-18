"""Canonicalize URLs and field normalization."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def _normalize_host(netloc: str) -> str:
    host = netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonicalize_url(url: str, parser_config: dict[str, Any] | None = None) -> str:
    if not url or not url.strip():
        return ""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = _normalize_host(parsed.netloc)
    strip_params = []
    if parser_config:
        canonical = parser_config.get("canonical") or {}
        strip_params = canonical.get("strip_query_params") or []

    qs = parse_qs(parsed.query, keep_blank_values=False)
    for param in strip_params:
        qs.pop(param, None)
    clean_query = urlencode({k: v[0] for k, v in qs.items() if v}, doseq=False)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", clean_query, ""))
