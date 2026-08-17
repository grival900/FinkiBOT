"""Shared vector-search layer. Both the FastAPI `/search`+`/chat` routes and the MCP
servers call into this module so retrieval logic lives in exactly one place."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def search(
    db: Session,
    query: str,
    k: int = 5,
    source: str | None = None,
    type: str | None = None,
) -> list[SearchResult]:
    query_vector = embed_query(query)
    distance = Chunk.embedding.cosine_distance(query_vector)

    stmt = select(Chunk, Document, distance.label("distance")).join(Document, Chunk.document_id == Document.id)
    if source is not None:
        stmt = stmt.where(Document.source == source)
    if type is not None:
        stmt = stmt.where(Document.type == type)
    stmt = stmt.order_by(distance).limit(k)

    results: list[SearchResult] = []
    for chunk, doc, dist in db.execute(stmt).all():
        results.append(
            SearchResult(
                document_id=str(doc.id),
                title=doc.title,
                url=doc.url,
                source=doc.source,
                type=doc.type,
                published_at=doc.published_at,
                chunk_text=chunk.text,
                score=1 - dist,
            )
        )
    return results
