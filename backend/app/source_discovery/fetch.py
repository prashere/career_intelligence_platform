"""Safe HTTP/browser fetch for candidate source pages."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.ingestion.fetch.browser import fetch_page, playwright_available
from app.ingestion.http_client import make_client
from app.source_discovery.constants import FETCH_TIMEOUT_S, MAX_FETCH_BYTES
from app.logging_config import get_logger

logger = get_logger(__name__)


def _is_public_host(host: str) -> bool:
    if not host:
        return False
    host = host.lower().strip()
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return False
    try:
        addr = ipaddress.ip_address(host)
        return not (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        try:
            resolved = socket.gethostbyname(host)
            addr = ipaddress.ip_address(resolved)
            return not (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
                or addr.is_multicast
            )
        except OSError:
            return False


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http(s) URLs are allowed")
    host = parsed.hostname
    if not host or not _is_public_host(host):
        raise ValueError("URL host is not allowed")
    return url.strip()


def fetch_page_text(url: str, *, use_browser: bool = False) -> tuple[str, str]:
    """Return (final_url, text/html)."""
    safe_url = validate_public_url(url)

    if not use_browser:
        try:
            with make_client(timeout=FETCH_TIMEOUT_S) as client:
                resp = client.get(safe_url, follow_redirects=True)
                final = str(resp.url)
                validate_public_url(final)
                content = resp.content[:MAX_FETCH_BYTES]
                text = content.decode(resp.encoding or "utf-8", errors="replace")
                if len(text.strip()) >= 200:
                    return final, text
        except Exception as exc:
            logger.debug("discovery_http_fetch_failed", url=safe_url, error=str(exc))

    if playwright_available():
        status, final_url, html = fetch_page(safe_url)
        validate_public_url(final_url)
        if status >= 400:
            raise RuntimeError(f"HTTP {status} for {final_url}")
        return final_url, html[:MAX_FETCH_BYTES]

    raise RuntimeError("Could not fetch page (HTTP failed and browser unavailable)")
