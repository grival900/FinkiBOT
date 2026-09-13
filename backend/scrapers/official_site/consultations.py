"""Scrapes each professor's live consultation-slot listing at
consultations.finki.ukim.mk — a separate booking system, not covered by anything else
this project indexes. `finki_hub.staff`'s own `consultations` field (see
`finki_hub/staff.py`) only ever captures the URL to this page, never the actual slot
data. This closes that gap: parses the upcoming date/time/location/instructions for
each professor directly, so chat can answer "кога има консултации проф. X" with a real
slot instead of only a link.

Professor discovery: reuses finki_hub's own staff.json feed (the same one
`finki_hub/staff.py` scrapes) purely to get the list of consultations.finki.ukim.mk
URLs to visit — one HTTP request per professor who has one, same shape as
`official_site/professors.py`.

Structure confirmed by inspecting a live page's HTML on 2026-09-13:
    div.row
        div.col-lg-5.col-md-6
            div.info-item
                i (icon, not content)
                div
                    strong                      -> label (e.g. "Датум", "Време")
                    span (one or more)           -> value(s); a date row carries an
                                                     extra badge span ("Утре"/"Денес")
                                                     alongside the actual date
            ... (Време, Локација, Пријавени студенти, Инструкции — same shape)
        div.col-lg-7.col-md-6   (empty)
One `.row` per upcoming slot. Only the first results page is scraped (no pagination
follow-up) — this is meant to surface the next handful of upcoming slots a student
would actually ask about, not build a full historical/future archive.
"""

import logging
from collections.abc import Iterator

from backend.scrapers.finki_hub.base import STAFF_JSON_URL
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import parse_html

logger = logging.getLogger(__name__)

CONSULTATIONS_HOST = "consultations.finki.ukim.mk"


def consultation_urls(staff_entries: list[dict]) -> list[tuple[str, str]]:
    """Pure step, unit-testable: (professor_name, consultations_url) pairs from
    finki_hub's staff feed — only entries whose `consultations` field actually points
    at the live booking system (some professors have none, or a different link)."""
    results: list[tuple[str, str]] = []
    for entry in staff_entries:
        name = (entry.get("name") or "").strip()
        url = (entry.get("consultations") or "").strip()
        if name and CONSULTATIONS_HOST in url:
            results.append((name, url))
    return results


def parse_consultation_slots(html: bytes | str) -> list[dict[str, str]]:
    """Pure parsing step, unit-testable against a saved fixture. Returns one dict per
    upcoming slot: {label -> value}, e.g. {"Датум": "14.9.2026 (понеделник), Утре",
    "Време": "14:00 - 16:00", ...}. Skips a `.row` with no `.info-item` inside it
    (the page's second, empty column renders as its own bare `.row` in some layouts)."""
    soup = parse_html(html)
    slots: list[dict[str, str]] = []
    for row in soup.select("div.row"):
        items = row.select(".info-item")
        if not items:
            continue
        slot: dict[str, str] = {}
        for item in items:
            label_el = item.select_one("strong")
            if label_el is None:
                continue
            label = label_el.get_text(strip=True)
            if not label:
                continue
            value = ", ".join(
                text for span in item.select("span") if (text := span.get_text(strip=True))
            )
            if value:
                slot[label] = value
        if slot:
            slots.append(slot)
    return slots


def _slot_text(slot: dict[str, str]) -> str:
    return "\n".join(f"{label}: {value}" for label, value in slot.items())


def scrape_consultations(skip_urls: set[str] | None = None) -> Iterator[NormalizedDocument]:
    with make_client() as client:
        response = client.get(STAFF_JSON_URL)
        response.raise_for_status()
        staff_entries = response.json()

        for name, url in consultation_urls(staff_entries):
            if skip_urls is not None and url in skip_urls:
                continue
            try:
                page = get(client, url)
                slots = parse_consultation_slots(page.content)
            except Exception:
                logger.warning("Could not fetch/parse consultations page %s", url, exc_info=True)
                continue
            if not slots:
                # No upcoming slots currently listed — not an error, just nothing to
                # index yet for this professor (mirrors professors.py skipping anyone
                # with no bio entered).
                continue

            content = f"Консултации — {name}\n\n" + "\n\n".join(_slot_text(s) for s in slots)
            metadata: dict[str, str] = {"professor": name, "slot_count": str(len(slots))}
            metadata.update(slots[0])  # nearest slot's own fields, for quick lookup

            yield NormalizedDocument(
                source="official",
                type="consultation",
                title=f"Консултации — {name}",
                url=url,
                content=content,
                metadata=metadata,
            ).clean()