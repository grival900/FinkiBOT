"""Scrapes the "Распоред на часови и консултации" widget on the announcement board
page (`/announcements/`) — a small set of reference links (exam-session schedule
spreadsheets, the live campus map, etc.), not part of the announcement rows
themselves (see `announcements.py`). This is where exam-session schedules actually
live: confirmed live, it currently links to a SharePoint spreadsheet like "Распоред за
септемвриска испитна сесија ... 2025/2026" alongside the FINKI Live Мапа.

Without this, the announcement board's own rows carry no exam dates at all, so RAG
chat/quiz has nothing to say about "кога е испитната сесија" — this scraper exists
specifically to fix that gap.

Structure confirmed by inspecting the live DOM on 2026-08-17:
    section.schedule-section
        a.schedule-card[href]
            span.schedule-card__heading   -> title
            span.schedule-card__subtitle  -> optional extra context (e.g. study cycle)

We only index the link text + URL, not any file contents (the actual dates are inside a
SharePoint spreadsheet we don't parse) — so the assistant can at least point a student to
the right document instead of claiming it has no information. The site itself curates
which cards are shown (e.g. it swaps to the next exam session once the current one
passes), so we don't hardcode which sessions to expect — we just scrape whatever's live.
"""

from collections.abc import Iterator

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.announcements import LISTING_PATH
from backend.scrapers.official_site.base import BASE_URL, parse_html


def parse_schedule_links_html(html: bytes | str) -> list[tuple[str, str]]:
    """Pure parsing step, unit-testable against a saved fixture. Returns (title, url) pairs."""
    soup = parse_html(html)
    section = soup.select_one(".schedule-section")
    if section is None:
        return []

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for card in section.select("a.schedule-card[href]"):
        href = card["href"].strip()
        heading_el = card.select_one(".schedule-card__heading")
        subtitle_el = card.select_one(".schedule-card__subtitle")
        heading = heading_el.get_text(strip=True) if heading_el else ""
        subtitle = subtitle_el.get_text(strip=True) if subtitle_el else ""
        text = f"{heading} {subtitle}".strip()
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
