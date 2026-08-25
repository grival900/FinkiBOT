"""Central list of scrapers the ingestion pipeline (and /admin/reindex) can run.

Each entry is a zero-arg callable returning an iterator of NormalizedDocument.
Scrapers that raise NotImplementedError are marked `enabled=False` so a full
reindex run skips them instead of failing outright.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal

from backend.scrapers.finki_hub.courses import scrape_courses
from backend.scrapers.finki_hub.recordings import scrape_recordings
from backend.scrapers.finki_hub.schedules import scrape_schedules
from backend.scrapers.finki_hub.sessions import scrape_sessions
from backend.scrapers.finki_hub.staff import scrape_staff
from backend.scrapers.finki_hub.thesis_archive import scrape_thesis_archive
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.announcements import scrape_announcements
from backend.scrapers.official_site.info_pages import scrape_info_pages
from backend.scrapers.official_site.professors import scrape_professors
from backend.scrapers.official_site.schedule_links import scrape_schedule_links
from backend.scrapers.official_site.subjects import scrape_subjects


Cadence = Literal["frequent", "slow"]


@dataclass
class ScraperEntry:
    name: str
    source: str
    fn: Callable[[], Iterator[NormalizedDocument]]
    enabled: bool = True
    # "frequent": cheap (a handful of requests, mostly single JSON fetches) and/or
    #   time-sensitive (announcements, exam sessions) — safe to run every scheduler tick.
    # "slow": one HTTP request per item with no bulk/listing endpoint (official course
    #   syllabi, professor profiles, community recordings pages) — each full pass costs
    #   dozens to 100+ requests at the deliberate 1 req/sec rate limit, but the content
    #   itself rarely changes day to day, so it doesn't need to be re-crawled often.
    # See `scheduler.py` — frequent and slow cadences run on separate intervals.
    cadence: Cadence = "frequent"


SCRAPERS: list[ScraperEntry] = [
    ScraperEntry(name="official.announcements", source="official", fn=scrape_announcements, cadence="frequent"),
    ScraperEntry(name="official.schedule_links", source="official", fn=scrape_schedule_links, cadence="frequent"),
    ScraperEntry(name="official.professors", source="official", fn=scrape_professors, cadence="slow"),
    # Static content (About Us/Studies/Admissions/International Students/Contact) —
    # changes rarely, hence "slow" even though it's a short, hand-curated URL list
    # rather than the usual one-request-per-discovered-item pattern that cadence
    # otherwise implies. See info_pages.py's docstring for scope/exclusions.
    ScraperEntry(name="official.info_pages", source="official", fn=scrape_info_pages, cadence="slow"),
    # Must run after finki_hub.courses — it reads official subject-page URLs that
    # finki_hub.courses already captured from the finki-hub detail dialog, rather than
    # discovering them independently (there's no listing/sitemap of its own).
    ScraperEntry(name="finki_hub.courses", source="finki_hub", fn=scrape_courses, cadence="frequent"),
    ScraperEntry(name="official.subjects", source="official", fn=scrape_subjects, cadence="slow"),
    ScraperEntry(name="finki_hub.recordings", source="finki_hub", fn=scrape_recordings, cadence="slow"),
    ScraperEntry(name="finki_hub.staff", source="finki_hub", fn=scrape_staff, cadence="frequent"),
    ScraperEntry(name="finki_hub.sessions", source="finki_hub", fn=scrape_sessions, cadence="frequent"),
    ScraperEntry(
        name="finki_hub.thesis_archive", source="finki_hub", fn=scrape_thesis_archive, enabled=False, cadence="slow"
    ),
    ScraperEntry(
        name="finki_hub.schedules", source="finki_hub", fn=scrape_schedules, enabled=False, cadence="frequent"
    ),
]
