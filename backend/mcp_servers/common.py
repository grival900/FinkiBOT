"""Shared helpers for the MCP servers. Each server is a thin tool layer over
`backend.core.retrieval.search` — filtered to its own `source`, so results are always
whatever the scrapers for that source have actually indexed (empty list, not an error,
for document types not scraped yet)."""

from backend.core.retrieval import SearchResult, search
from backend.db import SessionLocal


def result_to_dict(r: SearchResult) -> dict:
    return {
        "title": r.title,
        "url": r.url,
        "type": r.type,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "excerpt": r.chunk_text,
        "score": round(r.score, 4),
    }


def run_search(query: str, k: int, source: str, type: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        results = search(db, query, k=k, source=source, type=type)
    return [result_to_dict(r) for r in results]
