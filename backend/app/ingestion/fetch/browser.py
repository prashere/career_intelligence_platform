"""Optional Playwright-based fetch for Cloudflare / JS-rendered pages."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_playwright_ready: Optional[bool] = None


def playwright_available() -> bool:
    global _playwright_ready
    if _playwright_ready is not None:
        return _playwright_ready
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        _playwright_ready = True
    except ImportError:
        _playwright_ready = False
    return _playwright_ready


def fetch_page(url: str, *, timeout_ms: int = 45000, wait_selector: str | None = None) -> tuple[int, str, str]:
    """Return (status_code, final_url, html). Raises on launch failure."""
    if not playwright_available():
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 20000))
                except Exception:
                    pass
            html = page.content()
            status = response.status if response else 0
            final_url = page.url
            context.close()
            return status, final_url, html
        finally:
            browser.close()


def make_browser_client(timeout: float = 45.0):
    """Minimal httpx-like client interface for discover strategies."""

    class BrowserClient:
        def get(self, url: str, **kwargs):
            timeout_ms = int((kwargs.get("timeout") or timeout) * 1000)
            params = kwargs.get("params") or {}
            if params:
                from urllib.parse import urlencode

                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urlencode(params)}"
            status, final_url, html = fetch_page(url, timeout_ms=timeout_ms)
            return BrowserResponse(status, final_url, html)

    return BrowserClient()


class BrowserResponse:
    def __init__(self, status_code: int, url: str, text: str):
        self.status_code = status_code
        self.url = url
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code} for {self.url}")

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")
