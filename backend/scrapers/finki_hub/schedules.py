"""TODO: rasporedi.finki-hub.com (class schedules) DOM not yet investigated. Wire this up
the same way as `courses.py` once selectors are captured. Note the official site also
links a live schedule tool at raspored.finki.ukim.mk and posts session-specific exam
schedules as file attachments on the announcement board (see official_site/announcements.py)
— those may be a more direct source for exam-date questions than this module ends up being.
"""

from collections.abc import Iterator

from backend.scrapers.normalize import NormalizedDocument


def scrape_schedules() -> Iterator[NormalizedDocument]:
    raise NotImplementedError("schedules scraper not yet implemented — see module docstring")
    yield  # pragma: no cover
