"""Scrapes the "Распоред на часови и консултации" reference-links widget that sits in
the *header* of `/mk/student-announcement` — NOT part of the announcement rows
themselves (see `announcements.py`). This is where exam-session schedules actually live:
confirmed live, it links out to files like "Распоред за јунска испитна сесија ...
2025/2026" (a SharePoint spreadsheet) alongside a couple of other reference tools.

Without this, the announcement board's own rows carry no exam dates at all, so RAG
chat/quiz has nothing to say about "кога е испитната сесија" — this scraper exists
specifically to fix that gap.

Structure confirmed by inspecting the live DOM:
    div.view-header .view-raspored-list .ibox
        .ibox-title a[href]                  -> "Распоред на часови и консултации" -> raspored.finki.ukim.mk
        .ibox-content .row .col-sm-11 a[href] -> per-item title + URL (exam sessions, room map, etc.)

We only index the link text + URL, not any file contents (the actual dates are inside a
SharePoint spreadsheet we don't parse) — so the assistant can at least point a student to
the right document instead of claiming it has no information.
"""

from collections.abc import Iterator

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.announcements import LISTING_PATH
from backend.scrapers.official_site.base import BASE_URL, parse_html


def parse_schedule_links_html(html: bytes | str) -> list[tuple[str, str]]:
    """Pure parsing step, unit-testable against a saved fixture. Returns (title, url) pairs."""
    soup = parse_html(html)
    ibox = soup.select_one(".view-header .view-raspored-list .ibox")
    if ibox is None:
        return []

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    title_link = ibox.select_one(".ibox-title a[href]")
    if title_link is not None:
        href = title_link["href"].strip()
        text = title_link.get_text(strip=True) or "Распоред на часови и консултации"
        seen.add(href)
        results.append((text, href))

    for link in ibox.select(".ibox-content .row .col-sm-11 a[href]"):
        href = link["href"].strip()
        text = link.get_text(strip=True)
        if not href or not text or href in seen:
            continue
        seen.add(href)
        results.append((text, href))

    return results


def scrape_schedule_links() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = get(client, f"{BASE_URL}{LISTING_PATH}")

    for title, url in parse_schedule_links_html(response.content):
        yield NormalizedDocument(
            source="official",
            type="schedule",
            title=title,
            url=url,
            content=title,
        ).clean()
