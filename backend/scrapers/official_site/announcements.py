"""Scrapes the official announcement board (`/mk/student-announcement`).

This is the highest-value source per the project brief: exam schedules and other
time-sensitive notices are posted here. Structure (a Drupal "views" listing) confirmed
by inspecting the live DOM:

    div.view-oglasna-tabla .views-row
        h4 span.field-content a[href]     -> title, relative detail URL
        .date.pull-right span.field-content -> "DD.MM.YYYY" (listing date, approximate)

Detail page (`/mk/content/<slug>`):
    .field-name-post-date .field-item     -> "DD/MM/YYYY" (authoritative published date)
    .field-name-body .field-item          -> full announcement HTML body
"""

import logging
from collections.abc import Iterator
from urllib.parse import urljoin

import httpx

from backend.core.config import get_settings
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, element_to_text, parse_drupal_date, parse_html

logger = logging.getLogger(__name__)

LISTING_PATH = "/mk/student-announcement"
MAX_PAGES = 200  # safety cap; Drupal pager stops earlier once a page has zero rows


def parse_listing_html(html: bytes | str) -> list[tuple[str, str, str | None]]:
    """Pure parsing step, kept separate from the network call so it can be unit-tested
    against a saved HTML fixture. Returns (title, absolute_detail_url, listing_date_text)."""
    soup = parse_html(html)
    rows = soup.select(".view-oglasna-tabla .views-row")
    results = []
    for row in rows:
        link = row.select_one("h4 span.field-content a[href]")
        if not link:
            continue
        title = link.get_text(strip=True)
        detail_url = urljoin(BASE_URL, link["href"])
        date_el = row.select_one(".date.pull-right span.field-content")
        date_text = date_el.get_text(strip=True) if date_el else None
        results.append((title, detail_url, date_text))
    return results


def parse_detail_html(html: bytes | str) -> tuple[str, str | None]:
    """Pure parsing step (see `parse_listing_html`). Returns (content_text, published_date_text)."""
    soup = parse_html(html)
    body_el = soup.select_one(".field-name-body .field-item")
    content = element_to_text(body_el) if body_el else ""
    date_el = soup.select_one(".field-name-post-date .field-item")
    date_text = date_el.get_text(strip=True) if date_el else None
    return content, date_text


def _iter_listing_rows(client: httpx.Client) -> Iterator[tuple[str, str, str | None]]:
    """Yields (title, absolute_detail_url, listing_date_text) across all pager pages."""
    for page_num in range(MAX_PAGES):
        url = f"{BASE_URL}{LISTING_PATH}" if page_num == 0 else f"{BASE_URL}{LISTING_PATH}?page={page_num}"
        response = get(client, url)
        rows = parse_listing_html(response.content)
        if not rows:
            return
        yield from rows


def _fetch_detail(client: httpx.Client, url: str) -> tuple[str, str | None]:
    response = get(client, url)
    return parse_detail_html(response.content)


def scrape_announcements() -> Iterator[NormalizedDocument]:
    """The listing is sorted newest-first, so `scrape_announcement_limit` (if set) caps
    this to the N most recent announcements — the ones actually relevant to students —
    rather than backfilling the entire historical board on every run."""
    limit = get_settings().scrape_announcement_limit
    yielded = 0

    with make_client() as client:
        for title, detail_url, listing_date_text in _iter_listing_rows(client):
            if limit is not None and yielded >= limit:
                break

            try:
                content, detail_date_text = _fetch_detail(client, detail_url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch announcement detail: %s", detail_url)
                continue

            published_at = parse_drupal_date(detail_date_text or "") or parse_drupal_date(listing_date_text or "")

            yield NormalizedDocument(
                source="official",
                type="announcement",
                title=title,
                url=detail_url,
                content=content or title,
                published_at=published_at,
            ).clean()
            yielded += 1
