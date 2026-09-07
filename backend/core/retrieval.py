"""Shared vector-search layer. Both the FastAPI `/search`+`/chat` routes and the MCP
servers call into this module so retrieval logic lives in exactly one place."""

import difflib
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

# Score added to a result whose document *title* contains every token of a short,
# specific query. Pure dense retrieval ranks a chunk that merely mentions a name or
# course code (a co-author line on a different professor's publications page, a
# prerequisite reference on another course) about as high as the page actually about
# it; this nudge lets the on-topic page win without a full keyword index. Deliberately
# small — it reorders near-ties, it doesn't drag an off-topic chunk to the top.
TITLE_MATCH_BOOST = 0.12
# Only queries with at most this many whitespace tokens get the boost — a long topical
# query ("што покрива предметот бази на податоци и sql") would match half the course
# catalogue's titles and the boost would be noise rather than signal.
_MAX_BOOST_QUERY_TOKENS = 5
# Fuzzy per-token match threshold, to absorb the transliteration slack the Latin->
# Cyrillic map openly makes ("kalajdziski" lands as "калајѕиски"; the real surname is
# "калајџиски" — SequenceMatcher ratio ~0.9, a substring check alone would miss it).
_TITLE_TOKEN_SIM = 0.82
# The title boost can only reorder results the vector search already returned. A small
# caller `k` (the MCP tools ask for 3-5) would hand it a list the on-topic page never
# made it into — so each per-source vector search pulls at least this many candidates
# to rerank before trimming back to `k`. Cheap: an HNSW top-30 costs no more than a
# top-5 in practice.
_RERANK_POOL = 30


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


def _title_query_variants(query: str) -> list[list[str]]:
    """Tokenised query forms to test against result titles: the query as typed, plus a
    Cyrillic transliteration when it's Latin-only (indexed titles are Cyrillic). Only
    variants short enough to be a name/code lookup rather than a topical sentence."""
    variants = [query.lower().split()]
    if is_latin_only(query):
        variants.append(transliterate_latin_to_cyrillic(query).split())
    return [v for v in variants if 1 <= len(v) <= _MAX_BOOST_QUERY_TOKENS]


def _token_in_title(token: str, title_tokens: list[str]) -> bool:
    return any(
        token in tt or difflib.SequenceMatcher(None, token, tt).ratio() >= _TITLE_TOKEN_SIM
        for tt in title_tokens
    )


def _apply_title_boost(query: str, results: list[SearchResult]) -> None:
    """Bumps the score of every result whose title contains all tokens of a short
    query variant (see `_title_query_variants`). Mutates `results` in place; a no-op
    for long/topical queries and for results with no title-level match."""
    variants = _title_query_variants(query)
    if not variants:
        return
    for r in results:
        title_tokens = r.title.lower().split()
        if any(all(_token_in_title(t, title_tokens) for t in variant) for variant in variants):
            r.score = min(1.0, r.score + TITLE_MATCH_BOOST)


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
    min_score: float | None = None,
) -> list[SearchResult]:
    """Searches a specific source when `source` is given (top `k`, best score first).

    `min_score`, when set, drops every result below that cosine similarity from the
    return value — the caller's relevance floor. Left `None` (the `/search` box, the
    MCP tools) every top-`k` result comes back regardless of how weak; `/chat` passes
    a floor so the assistant never builds context or a citation list out of chunks
    that merely share a keyword with the question.

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

    pool = max(k, _RERANK_POOL)
    results_by_chunk: dict[str, SearchResult] = {}
    for src in sources:
        per_source: dict[str, SearchResult] = {}
        for vector in vectors:
            _merge(per_source, _search_by_vector(db, vector, pool, src, type, date_from, date_to))
        # Title-relevance nudge applied *before* the per-source top-k trim, so a page
        # actually about the query can climb into the k results even if a mere mention
        # of it on another page scored a hair higher on vector similarity alone.
        ranked = list(per_source.values())
        _apply_title_boost(query, ranked)
        # Trimmed per source *before* merging into the overall result set — otherwise
        # a source with more transliteration-variant matches could still end up
        # contributing more than k results and re-introduce the crowding-out this
        # function exists to avoid.
        top_k = sorted(ranked, key=lambda r: r.score, reverse=True)[:k]
        _merge(results_by_chunk, top_k)

    ordered = sorted(results_by_chunk.values(), key=lambda r: r.score, reverse=True)
    if min_score is not None:
        ordered = [r for r in ordered if r.score >= min_score]
    return ordered
