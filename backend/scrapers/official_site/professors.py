"""Scrapes teaching-staff profile pages (finki.ukim.mk/kadar/<slug>) — name, email, and
resume/bio plus other tabs (books, papers, conferences, projects, membership) when
filled in.

Discovered via the staff directory listing page, not a sitemap: every `/wp-sitemap*`
path on finki.ukim.mk now 307-redirects to a decommissioned `oldsite.finki.ukim.mk`
domain that itself bounces back to `/not-found` — a leftover redirect rule from the
site's redesign. That lands as a 200 OK (the soft-404 page), so `get()`'s
`raise_for_status()` never catches it; the old sitemap-based discovery just silently
parsed zero `<loc>` tags out of the HTML and yielded nothing, forever.

`/kadar/` itself isn't affected by that redirect and lists every profile directly:
confirmed live, one page, no pagination, ~107 `a.kadar-item__link` entries.

Confirmed live: all tabs (Резиме/Книги/Трудови/Конференции/Проекти/Член) are
server-rendered in the initial HTML regardless of which one is visually active, so a
plain GET captures everything — no client-side tab-click interaction needed. Many
profiles have no bio filled in ("Нема внесени податоци") — skipped as near-empty
*unless* they carry an email, since administrative staff (secretaries, department
contacts) commonly have no bio at all but a real contact address that's exactly what
a student would want out of a staff lookup.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import BASE_URL, element_to_text, parse_html

logger = logging.getLogger(__name__)

LISTING_PATH = "/kadar/"
MIN_CONTENT_LENGTH = 100


def parse_listing_html(html: bytes | str) -> list[str]:
    """Pure parsing step, unit-testable. Returns absolute profile URLs from the staff directory."""
    soup = parse_html(html)
    urls: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a.kadar-item__link[href]"):
        url = a["href"]
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


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
        listing_response = get(client, f"{BASE_URL}{LISTING_PATH}")
        urls = parse_listing_html(listing_response.content)

        for url in urls:
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch professor page: %s", url)
                continue

            if response.url.path.rstrip("/") == "/not-found":
                continue

            name, content, email = parse_professor_html(response.content)
            # A short/empty bio ("Нема внесени податоци") is common for administrative
            # staff, who often have no bio at all but a real, useful contact email — skip
            # only when there's neither a substantial bio nor an email, since that's the
            # only case with nothing worth indexing.
            if len(content) < MIN_CONTENT_LENGTH and not email:
                continue

            yield NormalizedDocument(
                source="official",
                type="professor",
                title=name or url,
                url=url,
                content=content,
                metadata={"email": email} if email else {},
            ).clean()
