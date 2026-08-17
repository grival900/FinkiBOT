"""Shared polite HTTP client for static-HTML scrapers (official_site).

finki_hub scrapers use Playwright instead since that site is client-rendered.
"""

import time

import httpx

from backend.core.config import get_settings

_settings = get_settings()
_last_request_at: float = 0.0


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": _settings.scrape_user_agent},
        timeout=20.0,
        follow_redirects=True,
    )


def get(client: httpx.Client, url: str) -> httpx.Response:
    """GET with a fixed delay between requests, applied globally across scrapers
    sharing this module, to stay polite to finki.ukim.mk."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = _settings.scrape_request_delay_seconds - elapsed
    if wait > 0:
        time.sleep(wait)
    response = client.get(url)
    _last_request_at = time.monotonic()
    response.raise_for_status()
    return response
