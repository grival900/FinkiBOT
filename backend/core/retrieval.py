"""Shared vector-search layer. Both the FastAPI `/search`+`/chat` routes and the MCP
servers call into this module so retrieval logic lives in exactly one place."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.transliteration import is_latin_only, transliterate_latin_to_cyrillic
from backend.ingestion.embeddings import embed_query
from backend.models import Chunk, Document


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


def _search_one(
    db: Session,
    query: str,
    k: int,
    source: str | None,
    type: str | None,
) -> list[SearchResult]:
    query_vector = embed_query(query)
    distance = Chunk.embedding.cosine_distance(query_vector)

    stmt = select(Chunk, Document, distance.label("distance")).join(Document, Chunk.document_id == Document.id)
    if source is not None:
        stmt = stmt.where(Document.source == source)
    if type is not None:
        stmt = stmt.where(Document.type == type)
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


def search(
    db: Session,
    query: str,
    k: int = 5,
    source: str | None = None,
    type: str | None = None,
) -> list[SearchResult]:
    # The indexed content here is essentially all Cyrillic. A query typed in Macedonian
    # "latinica" (no Cyrillic keyboard handy, e.g. "bazi na podatoci") would otherwise
    # never semantically match — so for a Latin-only query, also search a best-effort
    # transliterated variant and merge results, rather than replacing the original
    # (which would break matching for genuine Latin-script terms like "SQL", "Java").
    queries = [query]
    if is_latin_only(query):
        translit = transliterate_latin_to_cyrillic(query)
        if translit != query:
            queries.append(translit)

    if len(queries) == 1:
        return _search_one(db, query, k, source, type)

    results_by_chunk: dict[str, SearchResult] = {}
    for variant in queries:
        for result in _search_one(db, variant, k, source, type):
            key = f"{result.document_id}:{result.chunk_text[:80]}"
            existing = results_by_chunk.get(key)
            if existing is None or result.score > existing.score:
                results_by_chunk[key] = result

    return sorted(results_by_chunk.values(), key=lambda r: r.score, reverse=True)[:k]
