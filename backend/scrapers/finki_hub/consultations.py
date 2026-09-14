"""Scrapes each active staff member's live consultation schedule from
consultations.finki.ukim.mk — a separate FINKI web app, not a file. `staff.py` already
captures the per-professor URL to this page (from `staff.json`'s `consultations`
field) but only stores the bare link; this is where the actual scheduled slots
(date/time/room) get fetched and turned into searchable content.

Split out from `scrape_staff` rather than folded into it: `staff.json` is a single
cheap JSON fetch (cadence="frequent"), but fetching every professor's consultations
page individually is genuinely one request per person (~96 active staff carry a
consultations link, confirmed live) — by the registry's own cadence rule that's a
"slow" cost, so this gets its own entry alongside `official.professors`, which made
the same call for the same reason.

Confirmed live: a plain GET returns fully server-rendered HTML (no JS/API call
needed) — either a "Нема закажани консултации..." message, or one `.consultation-card`
per scheduled slot with Датум/Време/Локација fields.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.scrapers.finki_hub.base import STAFF_JSON_URL, parse_html
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

NO_SLOTS_SELECTOR = "h5.text-muted"
_RELEVANT_FIELDS = {"Датум", "Време", "Локација"}


def parse_consultations_html(html: bytes | str) -> str:
    """Pure parsing step, unit-testable against a saved fixture. Returns either the
    "no consultations scheduled" message, or one self-contained line per scheduled
    slot (so a later chunk-boundary split can never strand a date away from its own
    time/room)."""
    soup = parse_html(html)

    empty_el = soup.select_one(NO_SLOTS_SELECTOR)
    if empty_el is not None:
        return empty_el.get_text(strip=True)

    lines: list[str] = []
    for card in soup.select(".consultation-card"):
        fields: dict[str, str] = {}
        for item in card.select(".info-item"):
            label_el = item.find("strong")
            if label_el is None:
                continue
            label = label_el.get_text(strip=True)
            if label not in _RELEVANT_FIELDS:
                continue
            value_el = label_el.find_next_sibling("span")
            fields[label] = value_el.get_text(strip=True) if value_el else ""

        if fields:
            lines.append(", ".join(f"{label}: {value}" for label, value in fields.items()))

    return "\n".join(lines)


def scrape_consultations(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = client.get(STAFF_JSON_URL)
        response.raise_for_status()
        entries = response.json()

        for entry in entries:
            if entry.get("active") != "1":
                continue
            name = entry.get("name", "")
            url = entry.get("consultations", "")
            if not name or not url:
                continue
            if skip_urls is not None and url in skip_urls:
                continue

            try:
                page = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch consultations page: %s", url)
                continue

            content = parse_consultations_html(page.content)
            if not content:
                continue

            yield NormalizedDocument(
                source="finki_hub",
                type="consultation",
                title=name,
                url=url,
                content=f"{name}\n{content}",
            ).clean()
