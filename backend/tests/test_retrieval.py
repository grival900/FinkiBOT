from unittest.mock import patch

from backend.core import retrieval
from backend.core.retrieval import SearchResult, _merge, search


def _result(**overrides) -> SearchResult:
    defaults = dict(
        document_id="doc-1",
        title="Title",
        url="https://example.com",
        source="official",
        type="course",
        published_at=None,
        chunk_text="chunk text",
        score=0.5,
    )
    return SearchResult(**{**defaults, **overrides})


def test_merge_keeps_highest_score_per_chunk():
    low = _result(document_id="a", chunk_text="same chunk", score=0.3)
    high = _result(document_id="a", chunk_text="same chunk", score=0.9)

    merged: dict[str, SearchResult] = {}
    _merge(merged, [low])
    _merge(merged, [high])

    assert list(merged.values()) == [high]


def test_search_with_source_filter_only_queries_that_source():
    with (
        patch.object(retrieval, "_query_vectors", return_value=[[0.1, 0.2]]),
        patch.object(retrieval, "_search_by_vector") as mock_search,
    ):
        mock_search.return_value = [_result(document_id="a", source="official", score=0.7)]
        results = search(db=None, query="бази", k=5, source="official")

    mock_search.assert_called_once_with(None, [0.1, 0.2], 5, "official", None, None, None)
    assert [r.document_id for r in results] == ["a"]


def test_search_without_source_filter_unions_instead_of_competing():
    """The motivating bug: searching "bazi" with no source filter returned 8 official
    results and only 2 finki_hub ones in the top 10 — a single global ranking let
    official's generally-higher-scoring content crowd finki_hub out almost entirely,
    even though several finki_hub courses were clearly on-topic. Union-of-per-source
    search must return every one of finki_hub's top-k matches regardless of how they'd
    rank against official's, same as searching finki_hub alone would."""
    official_results = [_result(document_id=f"official-{i}", source="official", score=0.9 - i * 0.01) for i in range(5)]
    finki_hub_results = [_result(document_id=f"finki_hub-{i}", source="finki_hub", score=0.4 - i * 0.01) for i in range(5)]

    def fake_search_by_vector(db, vector, k, source, type, date_from=None, date_to=None):
        return official_results if source == "official" else finki_hub_results

    with (
        patch.object(retrieval, "_query_vectors", return_value=[[0.1, 0.2]]),
        patch.object(retrieval, "_search_by_vector", side_effect=fake_search_by_vector),
    ):
        results = search(db=None, query="bazi", k=5)

    document_ids = {r.document_id for r in results}
    assert document_ids == {f"official-{i}" for i in range(5)} | {f"finki_hub-{i}" for i in range(5)}
    # Sorted by score overall, so official's higher-scoring results still lead — but
    # every finki_hub result is present, just not first.
    assert results[0].source == "official"
    assert "finki_hub-0" in document_ids


def test_search_caps_each_source_at_k_before_merging():
    many_official = [_result(document_id=f"official-{i}", source="official", score=1.0 - i * 0.01) for i in range(10)]

    def fake_search_by_vector(db, vector, k, source, type, date_from=None, date_to=None):
        return many_official[:k] if source == "official" else []

    with (
        patch.object(retrieval, "_query_vectors", return_value=[[0.1, 0.2]]),
        patch.object(retrieval, "_search_by_vector", side_effect=fake_search_by_vector),
    ):
        results = search(db=None, query="bazi", k=3)

    assert len(results) == 3
