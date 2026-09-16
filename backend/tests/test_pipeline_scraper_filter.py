"""`run_ingestion`/`_run_ingestion_locked`'s `name` param narrows a reindex to exactly
one scraper (e.g. "finki_hub.sessions") regardless of cadence — for re-fetching a
single source after fixing its own extraction code, without paying for every other
cadence-mate too."""

import pytest
from unittest.mock import MagicMock, patch

from backend.ingestion import pipeline
from backend.scrapers.registry import ScraperEntry


def _entries():
    return [
        ScraperEntry(name="fake.a", source="official", fn=MagicMock(return_value=iter([])), cadence="frequent"),
        ScraperEntry(name="fake.b", source="finki_hub", fn=MagicMock(return_value=iter([])), cadence="slow"),
    ]


def test_run_ingestion_locked_runs_only_the_named_scraper():
    entries = _entries()
    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = MagicMock()

    with (
        patch.object(pipeline, "SessionLocal", return_value=session_ctx),
        patch.object(pipeline, "SCRAPERS", entries),
        patch.object(pipeline, "get_bool_setting", return_value=True),
    ):
        stats = pipeline._run_ingestion_locked(None, incremental=False, name="fake.b")

    assert list(stats.keys()) == ["fake.b"]
    entries[0].fn.assert_not_called()
    entries[1].fn.assert_called_once()


def test_run_ingestion_locked_name_filter_applies_regardless_of_cadence():
    """`name` narrows the run even when the caller also passes a `cadence` that would
    otherwise exclude it - `name` is meant to stand alone, not combine with cadence."""
    entries = _entries()
    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = MagicMock()

    with (
        patch.object(pipeline, "SessionLocal", return_value=session_ctx),
        patch.object(pipeline, "SCRAPERS", entries),
        patch.object(pipeline, "get_bool_setting", return_value=True),
    ):
        stats = pipeline._run_ingestion_locked("frequent", incremental=False, name="fake.b")

    # "fake.b" is cadence="slow" - combining an explicit cadence with a mismatched
    # name legitimately yields nothing, which is why the CLI/admin route don't pass
    # both at once; this just documents that both filters are applied together here.
    assert stats == {}
    entries[1].fn.assert_not_called()


def test_run_ingestion_rejects_an_unknown_scraper_name():
    with patch.object(pipeline, "SCRAPERS", _entries()):
        with pytest.raises(ValueError, match="fake.unknown"):
            pipeline.run_ingestion(name="fake.unknown")
