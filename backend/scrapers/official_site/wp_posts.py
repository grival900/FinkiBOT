"""Live WordPress REST scrapers sharing one paginated-listing implementation — events,
projects, and job/internship postings are each a single custom post type
(`event`/`project`/`jobs-and-internships`) whose `/wp-json/wp/v2/<rest_base>` listing
already returns full `content.rendered` HTML inline, confirmed live. Unlike
`nastaven_kadar` (professors — `content.rendered` is always empty, bio/email are
ACF fields the REST API never exposes) or `schedule` (2 link-cards, no content field
at all — see `schedule_links.py`), these three post types actually carry everything a
caller needs in the listing response itself, so no per-item detail fetch is needed:
one paginated GET per ~100 items covers title + body + published date at once.

Pagination: WP reports `X-WP-TotalPages` on every response and 400s past the last
page — cleaner to key off than announcements.py's "empty page" heuristic, which this
API doesn't reliably give (an out-of-range page here is an error, not an empty list).
"""

import html
import logging
from collections.abc import Iterator
from datetime import datetime

import httpx

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import DocumentType, NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, element_to_text, parse_html

logger = logging.getLogger(__name__)

PER_PAGE = 100
# Safety cap in case X-WP-TotalPages is ever missing/wrong — 50 * 100 = 5000 items is
# far beyond any of these post types' current size (a few hundred at most).
MAX_PAGES = 50


def _html_to_text(html: str) -> str:
    return element_to_text(parse_html(html))


def parse_wp_post_row(row: dict) -> tuple[str, str, str, str | None]:
    """Pure parsing step, unit-testable against a saved fixture row. Returns
    (title, url, content_text, iso_date_text)."""
    # Unlike `content.rendered`, which goes through an HTML parser below (decoding
    # entities as a side effect of extracting text), `title.rendered` is used as a bare
    # string — WP still HTML-entity-encodes it (confirmed live: "&#8211;"/"&#8217;" for
    # en-dash/apostrophe in ordinary titles), so it needs its own explicit unescape.
    title = html.unescape(row.get("title", {}).get("rendered", ""))
    url = row.get("link", "")
    content_html = row.get("content", {}).get("rendered", "")
    content = _html_to_text(content_html)
    date_text = row.get("date")
    return title, url, content, date_text


def _iter_listing(client: httpx.Client, rest_base: str) -> Iterator[dict]:
    """Yields raw WP REST post objects across every page of `rest_base`'s listing."""
    page_num = 1
    total_pages = 1
    while page_num <= total_pages and page_num <= MAX_PAGES:
        url = f"{BASE_URL}/wp-json/wp/v2/{rest_base}?per_page={PER_PAGE}&page={page_num}"
        response = get(client, url)
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        yield from response.json()
        page_num += 1


def scrape_wp_post_type(
    rest_base: str, doc_type: DocumentType, skip_urls: set[str] | None = None
) -> Iterator[NormalizedDocument]:
    with make_client() as client:
        try:
            rows = list(_iter_listing(client, rest_base))
        except httpx.HTTPError:
            logger.exception("Failed to list WordPress post type: %s", rest_base)
            return

        for row in rows:
            title, url, content, date_text = parse_wp_post_row(row)
            if not url or not content:
                continue
            if skip_urls is not None and url in skip_urls:
                continue

            published_at = datetime.fromisoformat(date_text) if date_text else None

            yield NormalizedDocument(
                source="official",
                type=doc_type,
                title=title or url,
                url=url,
                content=content,
                published_at=published_at,
            ).clean()


def scrape_events(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    return scrape_wp_post_type("event", "event", skip_urls)


def scrape_projects(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    return scrape_wp_post_type("project", "project", skip_urls)


def scrape_jobs_and_internships(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    return scrape_wp_post_type("jobs-and-internships", "job", skip_urls)
