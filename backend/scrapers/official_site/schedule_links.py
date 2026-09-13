"""Scrapes the "Распоред на часови и консултации" widget on the announcement board
page (`/announcements/`) — a small set of reference links (exam-session schedule
spreadsheets, the live campus map, etc.), not part of the announcement rows
themselves (see `announcements.py`). This is where exam-session schedules actually
live: confirmed live, it currently links to a SharePoint spreadsheet like "Распоред за
септемвриска испитна сесија ... 2025/2026" alongside the FINKI Live Мапа.

We always index the link text + URL (a student can at least be pointed to the right
document). On top of that we *try* to also download and parse the file's actual
content (see `scrapers/spreadsheet.py`), so RAG chat/quiz can answer specific
questions ("кога е испитот по <предмет>") with the real row instead of only a link.
This is best-effort and silently falls back to link-only: SharePoint "personal"
sharing links are usually an interactive Office-Online viewer page rather than a
direct file, and some require a sign-in this scraper doesn't have. We try a
direct-download variant of the URL and give up quietly if what comes back isn't a
readable spreadsheet — never a hard failure for this scraper.

Structure confirmed by inspecting the live DOM on 2026-08-17:
    section.schedule-section
        a.schedule-card[href]
            span.schedule-card__heading   -> title
            span.schedule-card__subtitle  -> optional extra context (e.g. study cycle)
"""

import logging
from collections.abc import Iterator

import httpx

from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.announcements import LISTING_PATH
from backend.scrapers.official_site.base import BASE_URL, parse_html
from backend.scrapers.spreadsheet import extract_rows, rows_to_documents

logger = logging.getLogger(__name__)

# .xlsx (and .docx/.pptx) files are zip containers, whose bytes always start with this
# signature — a cheap way to tell "we got the actual file" apart from "we got an HTML
# sign-in/viewer page instead" before handing it to openpyxl.
_ZIP_SIGNATURE = b"PK"


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


def _direct_download_url(url: str) -> str:
    """OneDrive/SharePoint "personal" sharing links (the `...-my.sharepoint.com/:x:/g/
    personal/...` links this widget produces) open an interactive viewer by default;
    appending `download=1` is the documented way to get the raw file back instead. A
    no-op-looking transform for any link that isn't actually SharePoint — harmless
    since we only trust the response by its content, not by this URL shape."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}download=1"


def _fetch_and_parse_schedule_file(client: httpx.Client, url: str) -> list:
    """Best-effort, see module docstring. Never raises."""
    try:
        response = client.get(_direct_download_url(url))
        response.raise_for_status()
        if not response.content.startswith(_ZIP_SIGNATURE):
            logger.info("Schedule link %s did not resolve to a downloadable file, skipping parse", url)
            return []
        return extract_rows(response.content)
    except Exception:
        logger.warning("Could not download/parse schedule file %s", url, exc_info=True)
        return []


def scrape_schedule_links(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = get(client, f"{BASE_URL}{LISTING_PATH}")

        for title, url in parse_schedule_links_html(response.content):
            if skip_urls is not None and url in skip_urls:
                continue
            yield NormalizedDocument(
                source="official",
                type="schedule",
                title=title,
                url=url,
                content=title,
            ).clean()

            rows = _fetch_and_parse_schedule_file(client, url)
            if rows:
                yield from rows_to_documents(
                    rows,
                    source="official",
                    file_title=title,
                    file_url=url,
                    extra_metadata={},
                )