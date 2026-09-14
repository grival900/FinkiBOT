import logging
import re
from collections.abc import Iterator
from datetime import datetime

from backend.ingestion.file_extraction import extract_pdf_text, extract_xlsx_schedule_grid
from backend.scrapers.finki_hub.base import SESSIONS_BASE_URL, SESSIONS_JSON_URL
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"^(\d{4}/\d{4})")


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


def extract_session_file_content(filename: str, data: bytes) -> tuple[str, datetime | None]:
    """Dispatches by extension, same shape as `backend/quiz/extraction.py`'s
    `extract_text`. `.xlsx` sessions (2022+) get the merged-cell-aware grid extractor,
    which also surfaces the session's earliest calendar date (for `published_at`, so
    recency ranking can prefer this year's session over an older one with near-
    identical content); older `.pdf` sessions get plain text only (no table structure
    or date column to exploit - just subject/year/time-slot/room - so no date signal,
    lower fidelity, acceptable for rarely-queried historical sessions). Any other
    extension is left unextracted (returns "") rather than raising, since a scrape
    loop over many files shouldn't abort on one unexpected filename."""
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        return extract_xlsx_schedule_grid(data)
    if lower.endswith(".pdf"):
        return extract_pdf_text(data), None
    logger.warning("Unrecognized exam-session file type, skipping content extraction: %s", filename)
    return "", None


def scrape_sessions(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = client.get(SESSIONS_JSON_URL)
        response.raise_for_status()
        data = response.json()

        for session_name, filename in data.items():
            url = f"{SESSIONS_BASE_URL}/{filename}"
            if skip_urls is not None and url in skip_urls:
                continue
            title, content, metadata = parse_session_entry(session_name, filename)

            # Fetch and parse are both a single, un-retried attempt at genuinely
            # external, sometimes-malformed input (a network blip, or one corrupt
            # .xlsx among ~40 files - openpyxl/pypdf do raise on that, unlike
            # BeautifulSoup's lenient HTML parsing elsewhere in these scrapers).
            # Skipping the yield entirely on either kind of failure - rather than
            # falling back to the plain link-only content - matters because
            # `upsert_document` can't tell "genuinely new content" apart from
            # "degraded fallback that happens to hash differently": yielding a
            # worse version of a document that was already successfully extracted
            # would silently overwrite the good one and wipe its `published_at`.
            # Not yielding at all leaves whatever's already indexed untouched, to
            # be retried next run.
            try:
                file_response = get(client, url)
                extracted, published_at = extract_session_file_content(filename, file_response.content)
            except Exception:
                logger.exception("Failed to fetch or parse exam-session file: %s", url)
                continue

            if extracted:
                content = f"{content}\n{extracted}"

            yield NormalizedDocument(
                source="finki_hub",
                type="schedule",
                title=title,
                url=url,
                content=content,
                published_at=published_at,
                metadata=metadata,
            ).clean()
