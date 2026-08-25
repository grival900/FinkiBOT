from datetime import datetime, timezone

from backend.api.routers.chat import build_context, citation_url, prefer_current_year
from backend.core.retrieval import SearchResult


def _result(**overrides) -> SearchResult:
    defaults = dict(
        document_id="doc-1",
        title="Title",
        url="https://example.com/original",
        source="official",
        type="announcement",
        published_at=None,
        chunk_text="chunk text",
        score=0.5,
    )
    return SearchResult(**{**defaults, **overrides})


def _dated(year: int, **overrides) -> SearchResult:
    return _result(published_at=datetime(year, 6, 1, tzinfo=timezone.utc), **overrides)


def test_prefer_current_year_drops_older_years_when_current_year_matches_exist():
    """The motivating case: a query like "студентска служба" matches near-identical
    announcement text posted every year — once a current-year match exists, older
    years shouldn't dilute the answer."""
    results = [
        _dated(2026, document_id="new", score=0.7),
        _dated(2014, document_id="old-1", score=0.9),
        _dated(2019, document_id="old-2", score=0.8),
    ]

    kept = prefer_current_year(results, k=6, current_year=2026)

    assert [r.document_id for r in kept] == ["new"]


def test_prefer_current_year_falls_back_to_older_years_when_none_match():
    """No current-year data at all — older years are genuinely the best available, so
    they're kept (highest score first) rather than leaving the answer empty."""
    results = [
        _dated(2014, document_id="old-1", score=0.6),
        _dated(2019, document_id="old-2", score=0.9),
    ]

    kept = prefer_current_year(results, k=6, current_year=2026)

    assert [r.document_id for r in kept] == ["old-2", "old-1"]


def test_prefer_current_year_always_keeps_undated_results():
    """Only announcements carry published_at — course/professor/etc. results have none
    and recency filtering doesn't apply to them at all."""
    results = [
        _dated(2014, document_id="old-announcement", score=0.95),
        _result(document_id="course", type="course", published_at=None, score=0.5),
    ]

    kept = prefer_current_year(results, k=6, current_year=2026)

    assert {r.document_id for r in kept} == {"old-announcement", "course"}


def test_prefer_current_year_respects_k():
    results = [_dated(2026, document_id=f"new-{i}", score=1.0 - i * 0.01) for i in range(10)]

    kept = prefer_current_year(results, k=3, current_year=2026)

    assert len(kept) == 3
    assert [r.document_id for r in kept] == ["new-0", "new-1", "new-2"]


def test_citation_url_uses_internal_link_for_finki_hub_courses():
    """predmeti.finki-hub.com has no per-course route to cite — a link to it only
    ever lands on the generic listing page, never the specific course."""
    r = _result(source="finki_hub", type="course", document_id="abc-123")
    assert citation_url(r) == "http://localhost:5173/documents/abc-123"


def test_citation_url_leaves_other_sources_and_types_untouched():
    r = _result(source="official", type="announcement", url="https://finki.ukim.mk/announcements/x/")
    assert citation_url(r) == "https://finki.ukim.mk/announcements/x/"

    r = _result(source="finki_hub", type="material", url="https://snimki.finki-hub.com/courses/x")
    assert citation_url(r) == "https://snimki.finki-hub.com/courses/x"


def test_build_context_embeds_internal_link_for_finki_hub_course():
    results = [_result(source="finki_hub", type="course", document_id="abc-123", title="Бази на податоци")]
    context = build_context(results)
    assert "http://localhost:5173/documents/abc-123" in context
    assert "predmeti.finki-hub.com" not in context
