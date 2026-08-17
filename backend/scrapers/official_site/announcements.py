"""Scrapes the official announcement board (`/announcements/`).

This is the highest-value source per the project brief: exam schedules and other
time-sensitive notices are posted here. Structure (a WordPress theme) confirmed by
inspecting the live DOM on 2026-08-17 — the site migrated off the old Drupal design
that used to live at `/mk/student-announcement`; that path now server-redirects to a
legacy mirror at oldsite.finki.ukim.mk and must not be scraped:

    div.announcements__items a.ann-card[href]
        h3.ann-card__title            -> title
        time.ann-card__date[datetime] -> ISO 8601 published date

Detail page (`<card href>`):
    div.page-content__body -> full announcement HTML body (minus the
                               .addtoany_share_save_container share-button noise
                               injected at the top)

Pagination: `?pg=N` (1-indexed); an out-of-range page responds 200 with zero
`.ann-card` rows, which is our stop signal — same handling as the old Drupal pager.
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from urllib.parse import urljoin

import httpx

from backend.core.config import get_settings
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, extract_page_body_text, parse_html

logger = logging.getLogger(__name__)

LISTING_PATH = "/announcements/"
MAX_PAGES = 200  # safety cap; the pager stops earlier once a page has zero rows


def parse_listing_html(html: bytes | str) -> list[tuple[str, str, str | None]]:
    """Pure parsing step, kept separate from the network call so it can be unit-tested
    against a saved HTML fixture. Returns (title, absolute_detail_url, iso_datetime_text)."""
    soup = parse_html(html)
    cards = soup.select(".announcements__items a.ann-card[href]")
    results = []
    for card in cards:
        title_el = card.select_one(".ann-card__title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        detail_url = urljoin(BASE_URL, card["href"])
        date_el = card.select_one(".ann-card__date")
        date_text = date_el.get("datetime") if date_el else None
        results.append((title, detail_url, date_text))
    return results


def parse_detail_html(html: bytes | str) -> str:
    """Pure parsing step (see `parse_listing_html`). Returns the announcement body text."""
    return extract_page_body_text(parse_html(html))


def _iter_listing_rows(client: httpx.Client) -> Iterator[tuple[str, str, str | None]]:
    """Yields (title, absolute_detail_url, iso_datetime_text) across all pager pages."""
    for page_num in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}{LISTING_PATH}" if page_num == 1 else f"{BASE_URL}{LISTING_PATH}?pg={page_num}"
        response = get(client, url)
        rows = parse_listing_html(response.content)
        if not rows:
            return
        yield from rows


def _fetch_detail(client: httpx.Client, url: str) -> str:
    response = get(client, url)
    return parse_detail_html(response.content)


def scrape_announcements() -> Iterator[NormalizedDocument]:
    """The listing is sorted newest-first, so `scrape_announcement_limit` (if set) caps
    this to the N most recent announcements — the ones actually relevant to students —
    rather than backfilling the entire historical board on every run."""
    limit = get_settings().scrape_announcement_limit
    yielded = 0

    with make_client() as client:
        for title, detail_url, date_text in _iter_listing_rows(client):
            if limit is not None and yielded >= limit:
                break

            try:
                content = _fetch_detail(client, detail_url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch announcement detail: %s", detail_url)
                continue

            published_at = datetime.fromisoformat(date_text) if date_text else None

            yield NormalizedDocument(
                source="official",
                type="announcement",
                title=title,
                url=detail_url,
                content=content or title,
                published_at=published_at,
            ).clean()
            yielded += 1
