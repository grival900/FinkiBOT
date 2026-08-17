"""Scrapes teaching-staff profile pages (finki.ukim.mk/kadar/<slug>) — name, email, and
resume/bio plus other tabs (books, papers, conferences, projects, membership) when
filled in. Sourced from the site's own WordPress sitemap for this custom post type,
same pattern as `pages.py`:

    https://finki.ukim.mk/wp-sitemap-posts-nastaven_kadar-1.xml

Confirmed live: all tabs (Резиме/Книги/Трудови/Конференции/Проекти/Член) are
server-rendered in the initial HTML regardless of which one is visually active, so a
plain GET captures everything — no client-side tab-click interaction needed. Many
profiles have no bio filled in ("Нема внесени податоци") and are skipped as
near-empty, same rationale as `pages.py`'s landing-page filter.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, element_to_text, parse_html, parse_xml

logger = logging.getLogger(__name__)

SITEMAP_PATH = "/wp-sitemap-posts-nastaven_kadar-1.xml"
MIN_CONTENT_LENGTH = 100


def parse_sitemap_xml(xml: bytes | str) -> list[str]:
    soup = parse_xml(xml)
    return [loc.get_text(strip=True) for loc in soup.select("loc")]


def parse_professor_html(html: bytes | str) -> tuple[str, str, str | None]:
    """Pure parsing step, unit-testable against a saved fixture. Returns (name, content_text, email)."""
    soup = parse_html(html)
    content_el = soup.select_one(".staff-single__content")
    if content_el is None:
        return "", "", None
    name_el = content_el.select_one(".staff-name") or soup.select_one("h1")
    name = name_el.get_text(strip=True) if name_el else ""
    email_el = soup.select_one(".staff-profile__email")
    email = email_el.get_text(strip=True) if email_el else None
    return name, element_to_text(content_el), email


def scrape_professors() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        sitemap_response = get(client, f"{BASE_URL}{SITEMAP_PATH}")
        urls = parse_sitemap_xml(sitemap_response.content)

        for url in urls:
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch professor page: %s", url)
                continue

            if response.url.path.rstrip("/") == "/not-found":
                continue

            name, content, email = parse_professor_html(response.content)
            if len(content) < MIN_CONTENT_LENGTH:
                continue

            yield NormalizedDocument(
                source="official",
                type="professor",
                title=name or url,
                url=url,
                content=content,
                metadata={"email": email} if email else {},
            ).clean()
