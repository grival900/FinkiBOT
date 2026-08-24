import logging
import re
from collections.abc import Iterator

from backend.scrapers.finki_hub.base import SESSIONS_BASE_URL, SESSIONS_JSON_URL
from backend.scrapers.http import make_client
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


def scrape_sessions() -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = client.get(SESSIONS_JSON_URL)
        response.raise_for_status()
        data = response.json()

    for session_name, filename in data.items():
        title, content, metadata = parse_session_entry(session_name, filename)

        yield NormalizedDocument(
            source="finki_hub",
            type="schedule",
            title=title,
            url=f"{SESSIONS_BASE_URL}/{filename}",
            content=content,
            metadata=metadata,
        ).clean()
