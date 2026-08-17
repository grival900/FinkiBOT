"""TODO: snimki.finki-hub.com (recorded lectures) DOM not yet investigated. Wire this up
the same way as `courses.py` once selectors are captured.
"""

from collections.abc import Iterator

from backend.scrapers.normalize import NormalizedDocument


def scrape_recordings() -> Iterator[NormalizedDocument]:
    raise NotImplementedError("recordings scraper not yet implemented — see module docstring")
    yield  # pragma: no cover
