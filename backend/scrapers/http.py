"""Shared polite HTTP client for scrapers (official_site, finki_hub)."""

import time

import httpx

from backend.core.config import get_settings
from backend.core.site_settings import get_setting_cached

_last_request_at: float = 0.0


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": get_settings().scrape_user_agent},
        timeout=20.0,
        follow_redirects=True,
    )


def get(client: httpx.Client, url: str) -> httpx.Response:
    """GET with a fixed delay between requests, applied globally across scrapers
    sharing this module, to stay polite to finki.ukim.mk. The delay is admin-editable
    (site_settings, cached for a few seconds) rather than a frozen startup value, since
    this fires once per request — hundreds of times per reindex — so it can't afford a
    DB round trip on every call."""
    global _last_request_at
    delay = get_setting_cached("scrape_request_delay_seconds", get_settings().scrape_request_delay_seconds, float)
    elapsed = time.monotonic() - _last_request_at
    wait = delay - elapsed
    if wait > 0:
        time.sleep(wait)
    response = client.get(url)
    _last_request_at = time.monotonic()
    response.raise_for_status()
    return response
