"""Scrapes predmeti.finki-hub.com — a client-rendered (Vite) app with no discoverable
public JSON API: all ~178 course rows are already present in the DOM on load (not
paginated/virtualized), confirmed by inspecting the live page. Listing structure:

    table tbody tr[role=button]
        td[0]  course name
        td[1]  accreditation years, e.g. "2023, 2018"
        td[3]  div > div  tag chips

Clicking a row opens a `[role=dialog]` with the actual course detail — professors,
assistants, and one card per accreditation year (course code, level, semester,
Discord channel, prerequisite, and a link to the official finki.ukim.mk subject page).
Confirmed live structure:

    [role=dialog]
        h4 (text "Професори") + .flex.flex-wrap.gap-1 > div  -> professor names
        h4 (text "Асистенти") + .flex.flex-wrap.gap-1 > div  -> assistant names
        .grid.gap-4 > div (one card per accreditation year)
            h3            -> "Акредитација <year>"
            a[href]       -> official subject page link
            dl > dt + dd  -> Код / Ниво / Семестар / Канал / Име / Предуслов pairs

This is a per-row interaction (~178 dialog opens across the whole listing, at the
polite scrape delay), so it's slower than a plain listing scrape — but it's what
actually has course content (level, semester, prerequisites, professors) rather than
just name/years/tags, which is what a course detail page on our own site needs
instead of sending students to finki-hub.
"""

import logging
import time
from collections.abc import Iterator
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from backend.core.config import get_settings
from backend.scrapers.finki_hub.base import PREDMETI_URL, parse_html
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)
settings = get_settings()


def _names_after_heading(soup, heading_text: str) -> list[str]:
    heading = next((h for h in soup.select("h4") if h.get_text(strip=True) == heading_text), None)
    if heading is None:
        return []
    chip_container = heading.find_next_sibling("div")
    if chip_container is None:
        return []
    return [chip.get_text(strip=True) for chip in chip_container.select("div") if chip.get_text(strip=True)]


def parse_dialog_html(html: str) -> dict:
    """Pure parsing step, unit-testable against a saved fixture."""
    soup = parse_html(html)

    accreditations = []
    for card in soup.select(".grid.gap-4 > div"):
        h3 = card.select_one("h3")
        if h3 is None:
            continue
        link_el = card.select_one("a[href]")
        fields: dict[str, str] = {}
        dl = card.select_one("dl")
        if dl is not None:
            for dt, dd in zip(dl.select("dt"), dl.select("dd"), strict=False):
                fields[dt.get_text(strip=True)] = dd.get_text(strip=True)
        accreditations.append(
            {
                "year": h3.get_text(strip=True).removeprefix("Акредитација ").strip(),
                "official_url": link_el["href"] if link_el else None,
                **fields,
            }
        )

    return {
        "professors": _names_after_heading(soup, "Професори"),
        "assistants": _names_after_heading(soup, "Асистенти"),
        "accreditations": accreditations,
    }


def _format_content(name: str, tags: list[str], details: dict) -> str:
    lines = [name]
    accreditations = details["accreditations"]
    latest = accreditations[0] if accreditations else {}

    if latest.get("Ниво") or latest.get("Семестар"):
        lines.append(f"Ниво: {latest.get('Ниво', '?')}, Семестар: {latest.get('Семестар', '?')}")
    if latest.get("Предуслов"):
        lines.append(f"Предуслов: {latest['Предуслов']}")
    if details["professors"]:
        lines.append(f"Професори: {', '.join(details['professors'])}")
    if details["assistants"]:
        lines.append(f"Асистенти: {', '.join(details['assistants'])}")
    if tags:
        lines.append(f"Тагови: {', '.join(tags)}")
    years = ", ".join(a["year"] for a in accreditations if a["year"])
    if years:
        lines.append(f"Акредитации: {years}")

    return "\n".join(lines)


def scrape_courses() -> Iterator[NormalizedDocument]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=settings.scrape_user_agent)
        page.goto(PREDMETI_URL, wait_until="networkidle")
        page.wait_for_selector("table tbody tr")

        row_count = page.locator("table tbody tr").count()
        for i in range(row_count):
            row = page.locator("table tbody tr").nth(i)
            cells = row.locator("td")
            name = cells.nth(0).inner_text().strip()
            tags = [t.strip() for t in cells.nth(3).locator("div > div").all_inner_texts() if t.strip()]

            details: dict = {"professors": [], "assistants": [], "accreditations": []}
            try:
                row.click()
                dialog = page.locator("[role=dialog]")
                dialog.wait_for(timeout=5000)
                details = parse_dialog_html(dialog.inner_html())
                page.keyboard.press("Escape")
            except Exception:
                logger.exception("Failed to open course detail dialog for %s", name)
            time.sleep(settings.scrape_request_delay_seconds)

            accreditations = details["accreditations"]
            official_url = next((a["official_url"] for a in accreditations if a["official_url"]), None)

            metadata = {
                "accreditation_years": [a["year"] for a in accreditations if a["year"]],
                "tags": tags,
                "professors": details["professors"],
                "assistants": details["assistants"],
                "accreditations": accreditations,
            }
            if official_url:
                metadata["official_subject_url"] = official_url

            # predmeti.finki-hub.com has no stable per-course route in list mode, so we
            # synthesize one from the course name to keep Document.url unique/stable
            # across runs. Deliberately never the official subject URL — that belongs to
            # a *different* document (see official_site/subjects.py's own scrape of it);
            # reusing it here would collide on the DB's URL-based upsert key and let one
            # scraper silently overwrite the other's content under the wrong source.
            url = f"{PREDMETI_URL}/?course={quote(name)}"

            yield NormalizedDocument(
                source="finki_hub",
                type="course",
                title=name,
                url=url,
                content=_format_content(name, tags, details),
                metadata=metadata,
            ).clean()

        browser.close()
