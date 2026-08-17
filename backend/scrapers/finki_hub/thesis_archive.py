"""TODO: diplomski.finki-hub.com uses a different (non-<table>) data-grid component than
predmeti.finki-hub.com (mentor list -> click a mentor -> per-mentor thesis list), so it
needs its own DOM investigation before a scraper can be written here. Confirmed live:
68 mentors, 4059 theses, with search/status/year filters. Not implemented yet — wire
this up the same way as `courses.py` once the grid's real selectors are captured.
"""

from collections.abc import Iterator

from backend.scrapers.normalize import NormalizedDocument


def scrape_thesis_archive() -> Iterator[NormalizedDocument]:
    raise NotImplementedError("thesis_archive scraper not yet implemented — see module docstring")
    yield  # pragma: no cover
