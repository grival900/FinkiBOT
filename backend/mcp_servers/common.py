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
    # recency_boost: a caller reaching for these tools ("what's the latest on X")
    # almost always wants the current posting of a recurring announcement, not
    # whichever year's copy happens to score highest on vector similarity.
    with SessionLocal() as db:
        results = search(db, query, k=k, source=source, type=type, recency_boost=True)
    return [result_to_dict(r) for r in results]


def run_search_types(query: str, k: int, source: str, types: list[str]) -> list[dict]:
    """Like `run_search`, but merges results across several `Document.type` values —
    for exam-session lookups, where the same query should surface both `type=exam`
    (an actual parsed row, if we managed to download/parse that file) and `type=schedule`
    (the link-only fallback for whatever we couldn't parse) ranked together by score,
    rather than the caller having to know which type any given file ended up as."""
    with SessionLocal() as db:
        merged = [
            r for t in types for r in search(db, query, k=k, source=source, type=t, recency_boost=True)
        ]
    merged.sort(key=lambda r: r.score, reverse=True)
    return [result_to_dict(r) for r in merged[:k]]