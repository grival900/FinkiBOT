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
from backend.scrapers.official_site.schedule_links import scrape_schedule_links


@dataclass
class ScraperEntry:
    name: str
    source: str
    fn: Callable[[], Iterator[NormalizedDocument]]
    enabled: bool = True


SCRAPERS: list[ScraperEntry] = [
    ScraperEntry(name="official.announcements", source="official", fn=scrape_announcements),
    ScraperEntry(name="official.schedule_links", source="official", fn=scrape_schedule_links),
    ScraperEntry(name="finki_hub.courses", source="finki_hub", fn=scrape_courses),
    ScraperEntry(name="finki_hub.thesis_archive", source="finki_hub", fn=scrape_thesis_archive, enabled=False),
    ScraperEntry(name="finki_hub.recordings", source="finki_hub", fn=scrape_recordings, enabled=False),
    ScraperEntry(name="finki_hub.schedules", source="finki_hub", fn=scrape_schedules, enabled=False),
]
