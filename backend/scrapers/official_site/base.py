import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

BASE_URL = "https://finki.ukim.mk"

_DATE_RE = re.compile(r"(\d{2})[./](\d{2})[./](\d{4})")


def parse_drupal_date(text: str) -> datetime | None:
    """Parses both listing-page dates ('20.07.2026') and detail-page dates
    ('20/07/2026') — both are DD-MM-YYYY, just with a different separator."""
    match = _DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    return datetime(int(year), int(month), int(day))


def element_to_text(el: Tag) -> str:
    text = el.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_html(content: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(content, "lxml")
