"""Scrapes static informational pages (student service hours, procedures, org
structure, contacts, etc.) — content that lives outside both the announcement board
and the schedule-links widget, e.g. https://finki.ukim.mk/studii-2/poddrshka/studentska-sluzhba/.

The site is WordPress; its `page` post type has its own auto-generated sitemap, which
gives us a bounded, known list of URLs to scrape instead of an open-ended crawl:

    https://finki.ukim.mk/wp-sitemap-posts-page-1.xml
        <loc>...</loc>  -> absolute page URL

Each page uses the same `.page-content__title` / `.page-content__body` template as
announcement detail pages (see `announcements.py`), so body extraction is shared via
`extract_page_body_text`.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, extract_page_body_text, parse_html, parse_xml

logger = logging.getLogger(__name__)

SITEMAP_PATH = "/wp-sitemap-posts-page-1.xml"
MIN_CONTENT_LENGTH = 100


def parse_sitemap_xml(xml: bytes | str) -> list[str]:
    """Pure parsing step, unit-testable against a saved fixture. Returns absolute page URLs."""
    soup = parse_xml(xml)
    return [loc.get_text(strip=True) for loc in soup.select("loc")]


def parse_page_html(html: bytes | str) -> tuple[str, str]:
    """Pure parsing step. Returns (title, content_text)."""
    soup = parse_html(html)
    title_el = soup.select_one(".page-content__title")
    title = title_el.get_text(strip=True) if title_el else ""
    content = extract_page_body_text(soup)
    return title, content


def scrape_pages() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        sitemap_response = get(client, f"{BASE_URL}{SITEMAP_PATH}")
        urls = parse_sitemap_xml(sitemap_response.content)

        for url in urls:
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch official-site page: %s", url)
                continue

            # Stale sitemap entries redirect to a custom 404 page that itself responds
            # 200 OK, so `raise_for_status()` doesn't catch it — check where we landed.
            if response.url.path.rstrip("/") == "/not-found":
                continue

            title, content = parse_page_html(response.content)
            # Many sitemap entries are section-landing pages whose body is just nav
            # cards (e.g. "Студии" with content "Студии") — bare titles/near-empty text
            # embed as generic vectors that score deceptively high against unrelated
            # queries, crowding out genuinely relevant results. Skip them; the pages
            # they link to are already indexed on their own.
            if len(content) < MIN_CONTENT_LENGTH:
                continue

            yield NormalizedDocument(
                source="official",
                type="page",
                title=title or url,
                url=url,
                content=content or title,
            ).clean()
