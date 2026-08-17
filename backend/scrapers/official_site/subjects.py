"""Scrapes official course syllabus pages (finki.ukim.mk/mk/subject/<code>) — title,
code, study programs, ECTS credits, teacher list, prerequisites, learning objectives,
and content outline. Confirmed live: this legacy Drupal template (served from
oldsite.finki.ukim.mk, same redirect `announcements.py` used to go through) has NOT
been replaced by anything on the redesigned site — unlike announcements, there is no
newer equivalent, so this genuinely is the live, canonical source for this content,
not a stale mirror.

Unlike other scrapers, this one has no independent listing or sitemap of its own:
subject page URLs only exist as `official_url` entries on already-indexed
`finki_hub.courses` documents (captured from the finki-hub course detail dialog). So
this reads those URLs from the DB instead of crawling for them — it depends on
`finki_hub.courses` having already run at least once.
"""

import logging
from collections.abc import Iterator

import httpx

from backend.db import SessionLocal
from backend.models import Document
from backend.scrapers.http import get, make_client
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.base import element_to_text, parse_html

logger = logging.getLogger(__name__)


def _subject_urls_from_courses() -> list[str]:
    with SessionLocal() as db:
        rows = db.query(Document.doc_metadata).filter(Document.source == "finki_hub", Document.type == "course")
        urls: set[str] = set()
        for (metadata,) in rows:
            for acc in metadata.get("accreditations", []):
                url = acc.get("official_url")
                if url:
                    urls.add(url)
    return sorted(urls)


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
