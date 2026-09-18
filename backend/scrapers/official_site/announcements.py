"""Scrapes the official announcement board via WordPress's own REST API
(`/wp-json/wp/v2/announcement`) rather than the HTML board (`/announcements/`) this
used to scrape. Confirmed live: unlike `nastaven_kadar` (professors — REST
`content.rendered` is always empty) or `schedule` (2 link-cards, no content field at
all), `announcement` posts carry their full body in the listing response itself —
no per-item detail-page fetch needed, cutting this from ~2 requests per new
announcement (1 listing row + 1 detail page) to ~1 request per page of 100. See
`wp_posts.py`'s docstring for the sibling scrapers (events/projects/jobs) that
established this endpoint is safe to rely on, and `parse_wp_post_row` (reused here)
for the shared row-parsing logic.

This is the highest-value source per the project brief: exam schedules and other
time-sensitive notices are posted here.

Pagination: WP reports `X-WP-TotalPages` on every response — the loop below stops
once it's paged through that many, same stop condition `wp_posts.py` uses. Unlike
that module's three scrapers, this one can't just list every page up front: the old
HTML pager's "stop after N known announcements in a row" (incremental runs) and
"cap to the N most recent" (full runs) both need to short-circuit page fetches, not
just filter results after the fact — `_iter_rows` stays a lazy generator so a caller
`break`-ing out of it (both cases below do) skips ever requesting the remaining
pages.
"""

import logging
from collections.abc import Iterator
from datetime import datetime

import httpx

from backend.core.config import get_settings
from backend.core.site_settings import get_setting_cached, parse_int_or_none
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL
from backend.scrapers.official_site.wp_posts import parse_wp_post_row

logger = logging.getLogger(__name__)

REST_BASE = "announcement"
PER_PAGE = 100
MAX_PAGES = 200  # safety cap; ~1008 announcements today, comfortably under 200*100
# On an incremental run the listing is newest-first (WP's default post ordering), so a
# run of already-indexed URLs means we've passed the new ones — stop paging rather than
# walk the whole history. A small buffer (not "stop at the first known one") tolerates
# the odd back-dated post.
INCREMENTAL_STOP_AFTER_KNOWN = 10


def _iter_rows(client: httpx.Client) -> Iterator[dict]:
    """Yields raw WP REST announcement objects, newest first, across every listing
    page — lazily, so a caller that stops early never fetches the remaining pages."""
    page_num = 1
    total_pages = 1
    while page_num <= total_pages and page_num <= MAX_PAGES:
        url = f"{BASE_URL}/wp-json/wp/v2/{REST_BASE}?per_page={PER_PAGE}&page={page_num}"
        try:
            response = get(client, url)
        except httpx.HTTPError:
            logger.exception("Failed to fetch announcement listing page %d", page_num)
            return
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        yield from response.json()
        page_num += 1


def scrape_announcements(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    """The listing is newest-first, so `scrape_announcement_limit` (if set) caps this
    to the N most recent announcements — the ones actually relevant to students —
    rather than backfilling the entire historical board on every run. Admin-editable
    (site_settings) — the env value is only the fallback default.

    `skip_urls` (incremental run): don't re-yield announcements already indexed, and
    stop paging once `INCREMENTAL_STOP_AFTER_KNOWN` known ones have gone by in a row."""
    limit = get_setting_cached("scrape_announcement_limit", get_settings().scrape_announcement_limit, parse_int_or_none)
    yielded = 0
    consecutive_known = 0

    with make_client() as client:
        for row in _iter_rows(client):
            if limit is not None and yielded >= limit:
                break

            title, url, content, date_text = parse_wp_post_row(row)
            if not url:
                continue

            if skip_urls is not None and url in skip_urls:
                consecutive_known += 1
                if consecutive_known >= INCREMENTAL_STOP_AFTER_KNOWN:
                    break
                continue
            consecutive_known = 0

            published_at = datetime.fromisoformat(date_text) if date_text else None

            yield NormalizedDocument(
                source="official",
                type="announcement",
                title=title or url,
                url=url,
                content=content or title,
                published_at=published_at,
            ).clean()
            yielded += 1
