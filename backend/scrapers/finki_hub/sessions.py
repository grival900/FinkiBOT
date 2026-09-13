import logging
import re
from collections.abc import Iterator

import httpx

from backend.scrapers.finki_hub.base import SESSIONS_BASE_URL, SESSIONS_JSON_URL
from backend.scrapers.http import make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.spreadsheet import extract_rows, rows_to_documents

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"^(\d{4}/\d{4})")

# Only the this-many most recent academic years get their spreadsheet actually
# downloaded and parsed into per-row `exam` documents. `sessions.json` accumulates
# every session ever posted (going back years), and each one is now a real .xlsx
# fetch + full-table parse (see `spreadsheet.py`) — nobody asks "when is my exam" for
# a session from 2021, so spending that time there just delays the sessions someone
# actually will ask about. Older sessions still get their plain link-only `schedule`
# document (see below) — they're just not fully parsed.
_RECENT_YEARS_TO_PARSE = 2


def _recent_academic_years(session_names: list[str], keep: int = _RECENT_YEARS_TO_PARSE) -> set[str]:
    years = {m.group(1) for name in session_names if (m := _YEAR_RE.match(name))}
    ranked = sorted(years, key=lambda y: int(y.split("/")[0]), reverse=True)
    return set(ranked[:keep])


def parse_session_entry(session_name: str, filename: str) -> tuple[str, str, dict]:
    """Pure parsing step, unit-testable. Returns (title, content, metadata)."""
    download_url = f"{SESSIONS_BASE_URL}/{filename}"

    year_match = _YEAR_RE.match(session_name)
    academic_year = year_match.group(1) if year_match else ""
    session_type = session_name.removeprefix(academic_year).strip() if academic_year else session_name

    content = f"{session_name}\nЛинк за преземање: {download_url}"

    metadata: dict[str, str] = {"filename": filename}
    if academic_year:
        metadata["academic_year"] = academic_year
    if session_type:
        metadata["session_type"] = session_type

    return session_name, content, metadata


def _fetch_and_parse_session_file(client: httpx.Client, download_url: str) -> list:
    """Best-effort: downloads the actual exam-session .xlsx and parses it into rows
    (see `scrapers/spreadsheet.py`) so chat/quiz can answer with real dates/rooms
    instead of only pointing at the file. Never raises — a download or parse failure
    (network hiccup, a file that isn't really .xlsx, an unreadable layout) just means
    this session's rows aren't queryable individually; the plain schedule-link
    document from `parse_session_entry` above still gets indexed either way."""
    try:
        response = client.get(download_url)
        response.raise_for_status()
        return extract_rows(response.content)
    except Exception:
        logger.warning("Could not download/parse session file %s", download_url, exc_info=True)
        return []


def scrape_sessions(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = client.get(SESSIONS_JSON_URL)
        response.raise_for_status()
        data = response.json()

        recent_years = _recent_academic_years(list(data.keys()))

        for session_name, filename in data.items():
            url = f"{SESSIONS_BASE_URL}/{filename}"
            if skip_urls is not None and url in skip_urls:
                continue
            title, content, metadata = parse_session_entry(session_name, filename)

            yield NormalizedDocument(
                source="finki_hub",
                type="schedule",
                title=title,
                url=url,
                content=content,
                metadata=metadata,
            ).clean()

            # Skip the (slow — full download + parse) row extraction for older
            # sessions entirely; only recent-year files pay that cost.
            if metadata.get("academic_year") not in recent_years:
                continue

            rows = _fetch_and_parse_session_file(client, url)
            if rows:
                yield from rows_to_documents(
                    rows,
                    source="finki_hub",
                    file_title=session_name,
                    file_url=url,
                    extra_metadata=metadata,
                )