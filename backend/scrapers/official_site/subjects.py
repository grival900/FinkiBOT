"""Scrapes official course syllabus pages (finki.ukim.mk/mk/subject/<code>) for the one
thing `finki_hub.courses` doesn't have: full syllabus prose — learning objectives,
content outline, literature. Everything else about a course (code, level, semester,
credits, prerequisites, professors/assistants, accreditation programs) is already
covered by `finki_hub.courses` from a single `courses.json` fetch, so this scraper is
deliberately scoped to just the syllabus gap rather than re-scraping course identity —
see `SCRAPE_SUBJECTS_LIMIT` below for why, and `registry.py` for why this runs weekly
instead of hourly.

Confirmed live: this legacy Drupal template (served from oldsite.finki.ukim.mk, same
redirect `announcements.py` used to go through) has NOT been replaced by anything on
the redesigned site — unlike announcements, there is no newer equivalent, so this
genuinely is the live, canonical source for this content, not a stale mirror.

Unlike other scrapers, this one has no independent listing or sitemap of its own:
subject page URLs only exist as the `official_subject_url` field on already-indexed
`finki_hub.courses` documents (the latest accreditation year's URL — older curriculum
revisions aren't worth a separate page fetch). So this reads those URLs from the DB
instead of crawling for them — it depends on `finki_hub.courses` having already run at
least once.

Even scoped to one URL per course, that's ~180 individual page fetches with no bulk
endpoint — at the deliberate 1 req/sec rate limit, a full pass costs several minutes
on its own. `SCRAPE_SUBJECTS_LIMIT` caps how many get fetched in one run so this stays
bounded; unset it for full coverage on the (weekly, off-hours) slow cadence.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.core.config import get_settings
from backend.core.site_settings import get_setting_cached, parse_int_or_none
from backend.db import SessionLocal
from backend.models import Document
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import element_to_text, parse_html

logger = logging.getLogger(__name__)


def _subject_urls_from_courses() -> list[str]:
    with SessionLocal() as db:
        rows = db.query(Document.doc_metadata).filter(Document.source == "finki_hub", Document.type == "course")
        urls = sorted({url for (metadata,) in rows if (url := metadata.get("official_subject_url"))})

    limit = get_setting_cached("scrape_subjects_limit", get_settings().scrape_subjects_limit, parse_int_or_none)
    return urls[:limit] if limit is not None else urls


def parse_subject_html(html: bytes | str) -> tuple[str, str]:
    """Pure parsing step, unit-testable against a saved fixture. Returns (title, content_text)."""
    soup = parse_html(html)
    body_el = soup.select_one(".region-content")
    if body_el is None:
        return "", ""
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else ""
    return title, element_to_text(body_el)


def scrape_subjects() -> Iterator[NormalizedDocument]:
    urls = _subject_urls_from_courses()

    with make_client() as client:
        for url in urls:
            try:
                response = get(client, url)
            except httpx.HTTPError:
                logger.exception("Failed to fetch subject page: %s", url)
                continue

            title, content = parse_subject_html(response.content)
            if not content:
                continue

            yield NormalizedDocument(
                source="official",
                type="course",
                title=title or url,
                url=url,
                content=content,
            ).clean()
