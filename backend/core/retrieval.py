"""Shared vector-search layer. Both the FastAPI `/search`+`/chat` routes and the MCP
servers call into this module so retrieval logic lives in exactly one place."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.transliteration import is_latin_only, transliterate_latin_to_cyrillic
from backend.ingestion.embeddings import embed_query
from backend.models import Chunk, Document

# The two sources currently indexed (see registry.py) — hardcoded here rather than
# queried from the DB since `search()` needs this list even when nothing of one source
# happens to be indexed yet, and it's exactly the pair the frontend's source filter
# and the two MCP servers already hardcode.
ALL_SOURCES = ["official", "finki_hub"]


@dataclass
class SearchResult:
    document_id: str
    title: str
    url: str
    source: str
    type: str
    published_at: datetime | None
    chunk_text: str
    score: float  # cosine similarity in [-1, 1], higher is more relevant
    metadata: dict[str, Any] = field(default_factory=dict)


def _query_vectors(query: str) -> list[list[float]]:
    """Embeds `query` and, for a Latin-only query, also a best-effort Cyrillic
    transliteration — computed once per variant regardless of how many sources end
    up being searched against them (embedding is the expensive step here, not the
    indexed vector search itself). The indexed content is essentially all Cyrillic:
    a query typed in Macedonian "latinica" (no Cyrillic keyboard handy, e.g. "bazi na
    podatoci") would otherwise never semantically match — searching the transliterated
    variant *alongside* the original (not replacing it) keeps genuine Latin-script
    terms like "SQL"/"Java" matching too."""
    queries = [query]
    if is_latin_only(query):
        translit = transliterate_latin_to_cyrillic(query)
        if translit != query:
            queries.append(translit)
    return [embed_query(q) for q in queries]


def _search_by_vector(
    db: Session,
    query_vector: list[float],
    k: int,
    source: str | None,
    type: str | None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[SearchResult]:
    distance = Chunk.embedding.cosine_distance(query_vector)

    stmt = select(Chunk, Document, distance.label("distance")).join(Document, Chunk.document_id == Document.id)
    if source is not None:
        stmt = stmt.where(Document.source == source)
    if type is not None:
        stmt = stmt.where(Document.type == type)
    # Only announcements carry published_at today (see chat.py's prefer_current_year
    # docstring) — a date range naturally excludes every undated document type rather
    # than needing a separate announcement-only code path, which is fine since setting
    # a date range is an explicit, opt-in choice.
    if date_from is not None:
        stmt = stmt.where(Document.published_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Document.published_at < date_to + timedelta(days=1))
    stmt = stmt.order_by(distance).limit(k)

    return [
        SearchResult(
            document_id=str(doc.id),
            title=doc.title,
            url=doc.url,
            source=doc.source,
            type=doc.type,
            published_at=doc.published_at,
            chunk_text=chunk.text,
            score=1 - dist,
            metadata=doc.doc_metadata or {},
        )
        for chunk, doc, dist in db.execute(stmt).all()
    ]


def _merge(results_by_chunk: dict[str, SearchResult], results: list[SearchResult]) -> None:
    for result in results:
        key = f"{result.document_id}:{result.chunk_text[:80]}"
        existing = results_by_chunk.get(key)
        if existing is None or result.score > existing.score:
            results_by_chunk[key] = result


def search(
    db: Session,
    query: str,
    k: int = 5,
    source: str | None = None,
    type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[SearchResult]:
    """Searches a specific source when `source` is given (top `k`, best score first).

    Otherwise searches *each* indexed source independently and returns the union —
    not one global cross-source ranking. A single ranking would let whichever
    source's content tends to score higher (e.g. official's verbose syllabus prose
    vs finki_hub's short metadata cards) crowd the other out of the results
    entirely, rather than just outranking it — confirmed live: "bazi" with no source
    filter returned 8 official results and only 2 finki_hub ones in the top 10,
    silently dropping finki_hub courses ("Вовед во бази на податоци и SQL" among
    them) that rank clearly on-topic when finki_hub is searched alone. Union-of-
    per-source search guarantees every source contributes up to `k` results, same as
    searching each source separately, at the cost of returning up to
    `len(ALL_SOURCES) * k` results instead of a strict `k` when `source` is unset.
    """
    vectors = _query_vectors(query)
    sources = [source] if source is not None else ALL_SOURCES

    results_by_chunk: dict[str, SearchResult] = {}
    for src in sources:
        per_source: dict[str, SearchResult] = {}
        for vector in vectors:
            _merge(per_source, _search_by_vector(db, vector, k, src, type, date_from, date_to))
        # Trimmed per source *before* merging into the overall result set — otherwise
        # a source with more transliteration-variant matches could still end up
        # contributing more than k results and re-introduce the crowding-out this
        # function exists to avoid.
        top_k = sorted(per_source.values(), key=lambda r: r.score, reverse=True)[:k]
        _merge(results_by_chunk, top_k)

    return sorted(results_by_chunk.values(), key=lambda r: r.score, reverse=True)
