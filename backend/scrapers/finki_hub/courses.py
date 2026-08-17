"""Scrapes predmeti.finki-hub.com — a client-rendered (Vite) app with no discoverable
public JSON API: all ~178 course rows are already present in the DOM on load (not
paginated/virtualized), confirmed by inspecting the live page. Structure:

    table tbody tr
        td[0]  course name
        td[1]  accreditation years, e.g. "2023, 2018"
        td[2]  (discord channel indicator, not scraped)
        td[3]  div > div  tag chips

Clicking a row opens a `[role=dialog]` with professors/assistants and a link to the
official finki.ukim.mk subject page (`.../mk/subject/<CODE>`) — that's `deep=True` mode
below. It's ~178 extra page interactions, so keep it off by default and reserve it for
periodic (e.g. nightly) deep passes rather than every scrape run.
"""

import logging
import time
from collections.abc import Iterator
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from backend.core.config import get_settings
from backend.scrapers.finki_hub.base import PREDMETI_URL
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)
settings = get_settings()


def scrape_courses(deep: bool = False) -> Iterator[NormalizedDocument]:
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
            years_text = cells.nth(1).inner_text().strip()
            tags = [t.strip() for t in cells.nth(3).locator("div > div").all_inner_texts() if t.strip()]

            metadata: dict = {
                "accreditation_years": [y.strip() for y in years_text.split(",") if y.strip()],
                "tags": tags,
            }
            official_url: str | None = None

            if deep:
                try:
                    row.click()
                    dialog = page.locator("[role=dialog]")
                    dialog.wait_for(timeout=5000)
                    link = dialog.locator("a[href*='finki.ukim.mk/mk/subject/']")
                    if link.count() > 0:
                        official_url = link.first.get_attribute("href")
                        metadata["official_subject_url"] = official_url
                    page.keyboard.press("Escape")
                    time.sleep(settings.scrape_request_delay_seconds)
                except Exception:
                    logger.exception("Failed to open course detail dialog for %s", name)

            # predmeti.finki-hub.com has no stable per-course route in list mode, so we
            # synthesize one from the course name to keep Document.url unique/stable
            # across runs; deep mode gets the real official subject URL instead.
            url = official_url or f"{PREDMETI_URL}/?course={quote(name)}"
            content = f"{name}\nАкредитации: {years_text}\nТагови: {', '.join(tags)}"

            yield NormalizedDocument(
                source="finki_hub",
                type="course",
                title=name,
                url=url,
                content=content,
                metadata=metadata,
            ).clean()

        browser.close()
