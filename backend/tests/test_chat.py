from datetime import datetime, timezone

from backend.api.routers.chat import (
    CITATION_SCORE_GAP,
    MAX_CITED_SOURCES,
    _sources_cut_index,
    build_context,
    build_sources_block,
    citation_url,
    prefer_current_year,
    select_citation_sources,
    source_label,
)
from backend.core.config import get_settings
from backend.core.retrieval import SearchResult

_FRONTEND_ORIGIN = get_settings().frontend_origin


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
    assert citation_url(r) == f"{_FRONTEND_ORIGIN}/documents/abc-123"


def test_citation_url_leaves_other_sources_and_types_untouched():
    r = _result(source="official", type="announcement", url="https://finki.ukim.mk/announcements/x/")
    assert citation_url(r) == "https://finki.ukim.mk/announcements/x/"

    r = _result(source="finki_hub", type="material", url="https://snimki.finki-hub.com/courses/x")
    assert citation_url(r) == "https://snimki.finki-hub.com/courses/x"


def test_build_context_embeds_internal_link_for_finki_hub_course():
    results = [_result(source="finki_hub", type="course", document_id="abc-123", title="Бази на податоци")]
    context = build_context(results)
    assert f"{_FRONTEND_ORIGIN}/documents/abc-123" in context
    assert "predmeti.finki-hub.com" not in context


def test_select_citation_sources_drops_the_low_scoring_tail():
    """The motivating bug: a name query returned the right professor page at 0.7 plus
    three unrelated pages at ~0.35 that only mention the name in passing — all four got
    listed as sources, making a correct answer look like it cited the wrong people."""
    results = [
        _result(document_id="right", score=0.72),
        _result(document_id="tail-1", score=0.72 - CITATION_SCORE_GAP - 0.01),
        _result(document_id="tail-2", score=0.30),
    ]

    picked = select_citation_sources(results)

    assert [r.document_id for r in picked] == ["right"]


def test_select_citation_sources_keeps_documents_within_the_gap():
    results = [
        _result(document_id="a", url="https://example.com/a", score=0.70),
        _result(document_id="b", url="https://example.com/b", score=0.70 - CITATION_SCORE_GAP + 0.02),
    ]

    picked = select_citation_sources(results)

    assert [r.document_id for r in picked] == ["a", "b"]


def test_select_citation_sources_dedupes_by_document_and_caps_count():
    results = [_result(document_id="dup", url="https://example.com/dup", chunk_text="chunk a", score=0.80)]
    results += [_result(document_id="dup", url="https://example.com/dup", chunk_text="chunk b", score=0.79)]
    results += [
        _result(document_id=f"d{i}", url=f"https://example.com/d{i}", score=0.80)
        for i in range(MAX_CITED_SOURCES + 3)
    ]

    picked = select_citation_sources(results)

    assert len(picked) == MAX_CITED_SOURCES
    assert picked[0].document_id == "dup"
    assert [r.document_id for r in picked].count("dup") == 1


def test_select_citation_sources_empty_input():
    assert select_citation_sources([]) == []


def test_select_citation_sources_dedupes_documents_that_resolve_to_one_url():
    """A finki_hub course with no stable page of its own is cited at its official
    syllabus URL — the same URL the official course document already uses. Two
    near-tied results, one link: list it once."""
    shared = "https://www.finki.ukim.mk/mk/subject/F23L3S141"
    results = [
        _result(document_id="official-doc", source="official", type="course", url=shared, score=0.80),
        _result(
            document_id="finki-hub-doc",
            source="finki_hub",
            type="course",
            metadata={"official_subject_url": shared},
            score=0.79,
        ),
    ]

    picked = select_citation_sources(results)

    assert [r.document_id for r in picked] == ["official-doc"]


def test_source_label_distinguishes_same_title_across_sites():
    official = _result(
        title="Неструктурирани бази на податоци",
        source="official",
        type="course",
        url="https://www.finki.ukim.mk/mk/subject/F23L3S141",
    )
    # finki_hub course with no official syllabus URL -> cited at our own /documents page,
    # which _display_host still attributes to finki-hub.
    finki_hub = _result(
        title="Неструктурирани бази на податоци", source="finki_hub", type="course", metadata={}
    )

    assert source_label(official) == "Неструктурирани бази на податоци (предмет, finki.ukim.mk)"
    assert source_label(finki_hub) == "Неструктурирани бази на податоци (предмет, finki-hub.com)"


def test_source_label_uses_the_link_host_not_the_source_field():
    """A finki_hub staff card stores a finki.ukim.mk profile URL — the label should say
    where the link actually goes."""
    staff = _result(
        title="Слободан Калајџиски",
        source="finki_hub",
        type="staff",
        url="https://www.finki.ukim.mk/mk/staff/slobodan-kalajdziski",
    )
    assert source_label(staff) == "Слободан Калајџиски (наставник, finki.ukim.mk)"


def test_build_sources_block_labels_each_entry_with_its_site():
    block = build_sources_block(
        [_result(title="Т", source="official", type="professor", url="https://finki.ukim.mk/kadar/t/")]
    )
    assert "**Извори:**" in block
    assert "- [Т (професор, finki.ukim.mk)]" in block


def test_build_sources_block_is_empty_when_nothing_qualifies():
    assert build_sources_block([]) == ""


def test_sources_cut_index_finds_a_model_written_list_after_a_rule():
    body = "Answer text here.\n\n---\n\n**Извори:**\n- [X](https://e.com)"
    idx = _sources_cut_index(body)
    assert idx is not None
    assert body[:idx].rstrip() == "Answer text here."


def test_sources_cut_index_finds_a_bare_heading():
    body = "Одговор.\nSources:\n- x"
    assert body[: _sources_cut_index(body)].rstrip() == "Одговор."


def test_sources_cut_index_ignores_the_word_mid_sentence():
    assert _sources_cut_index("Постојат два извори за оваа информација и двата се важни.") is None
    assert _sources_cut_index("Plain answer with no list at all.") is None
