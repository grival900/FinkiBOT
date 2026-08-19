from backend.api.routers.chat import build_context, citation_url
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
