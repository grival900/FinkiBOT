"""Scrapes snimki.finki-hub.com — a community-maintained (unofficial) collection of
recorded-lecture links, playlists, and notes, one static page per course. Confirmed
live: server-rendered (VitePress), course pages are linked from the `/introduction.html`
sidebar (68 confirmed live) — no separate sitemap exists.

Each course page lists recording links grouped by professor/year/lecture, plus
"Дополнителна содржина" (additional content) and "Белешки" (notes) sections when
filled in. This is what finki-hub actually has under the "materials" umbrella — there
is no separate slides/notes repository distinct from this recordings+notes collection,
confirmed by checking finki-hub.com's own platform list live.
"""

import logging
from collections.abc import Iterator
from urllib.parse import urljoin

import httpx

from backend.scrapers.finki_hub.base import SNIMKI_URL, element_to_text, parse_html
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

INTRODUCTION_PATH = "/introduction.html"


def parse_course_links(html: bytes | str) -> list[str]:
    """Pure parsing step, unit-testable against a saved fixture. Returns absolute course-page URLs."""
    soup = parse_html(html)
    urls = {urljoin(SNIMKI_URL, a["href"]) for a in soup.select('a[href*="/courses/"]')}
    return sorted(urls)


def parse_course_page_html(html: bytes | str) -> tuple[str, str]:
    """Pure parsing step. Returns (title, content_text)."""
    soup = parse_html(html)
    main_el = soup.select_one(".vp-doc")
    if main_el is None:
        return "", ""
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True).replace("​", "") if title_el else ""
    return title, element_to_text(main_el)


def scrape_recordings() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        intro_response = get(client, f"{SNIMKI_URL}{INTRODUCTION_PATH}")
        urls = parse_course_links(intro_response.content)

        for url in urls:
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch recordings page: %s", url)
                continue

            title, content = parse_course_page_html(response.content)
            if not content:
                continue

            yield NormalizedDocument(
                source="finki_hub",
                type="material",
                title=title or url,
                url=url,
                content=content,
            ).clean()
