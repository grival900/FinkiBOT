"""Central list of scrapers the ingestion pipeline (and /admin/reindex) can run.

Each entry is a zero-arg callable returning an iterator of NormalizedDocument.
Scrapers that raise NotImplementedError are marked `enabled=False` so a full
reindex run skips them instead of failing outright.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from backend.scrapers.finki_hub.courses import scrape_courses
from backend.scrapers.finki_hub.recordings import scrape_recordings
from backend.scrapers.finki_hub.schedules import scrape_schedules
from backend.scrapers.finki_hub.thesis_archive import scrape_thesis_archive
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.official_site.announcements import scrape_announcements
from backend.scrapers.official_site.pages import scrape_pages
from backend.scrapers.official_site.professors import scrape_professors
from backend.scrapers.official_site.schedule_links import scrape_schedule_links
from backend.scrapers.official_site.subjects import scrape_subjects


@dataclass
class ScraperEntry:
    name: str
    source: str
    fn: Callable[[], Iterator[NormalizedDocument]]
    enabled: bool = True


SCRAPERS: list[ScraperEntry] = [
    ScraperEntry(name="official.announcements", source="official", fn=scrape_announcements),
    ScraperEntry(name="official.schedule_links", source="official", fn=scrape_schedule_links),
    ScraperEntry(name="official.pages", source="official", fn=scrape_pages),
    ScraperEntry(name="official.professors", source="official", fn=scrape_professors),
    # Must run after finki_hub.courses — it reads official subject-page URLs that
    # finki_hub.courses already captured from the finki-hub detail dialog, rather than
    # discovering them independently (there's no listing/sitemap of its own).
    ScraperEntry(name="finki_hub.courses", source="finki_hub", fn=scrape_courses),
    ScraperEntry(name="official.subjects", source="official", fn=scrape_subjects),
    ScraperEntry(name="finki_hub.recordings", source="finki_hub", fn=scrape_recordings),
    ScraperEntry(name="finki_hub.thesis_archive", source="finki_hub", fn=scrape_thesis_archive, enabled=False),
    ScraperEntry(name="finki_hub.schedules", source="finki_hub", fn=scrape_schedules, enabled=False),
]
