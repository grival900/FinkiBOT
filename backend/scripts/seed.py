"""Loads `backend/seed/documents.json` into the database: `python -m backend.scripts.seed`.

A fast, fully offline first-time setup that skips live scraping entirely — no
requests to finki.ukim.mk or finki-hub.com at all, just local chunking + embedding.
See the root README's "First time on a new machine" section.

Goes through the same upsert/chunk/embed pipeline a live scrape would
(`ingest_normalized_document`), so re-running this is safe and idempotent, and
mixing it with a later live reindex works exactly like it would for any other
source — matched by URL, unchanged content skipped.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from backend.db import SessionLocal
from backend.ingestion.pipeline import ingest_normalized_document
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "seed" / "documents.json"


def row_to_ndoc(row: dict) -> NormalizedDocument:
    """Pure parsing step, unit-testable against an inline dict."""
    return NormalizedDocument(
        source=row["source"],
        type=row["type"],
        title=row["title"],
        url=row["url"],
        content=row["content"],
        published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
        metadata=row["metadata"],
    ).clean()


def seed() -> int:
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    count = 0
    with SessionLocal() as db:
        for row in rows:
            ndoc = row_to_ndoc(row)
            try:
                with db.begin_nested():
                    ingest_normalized_document(db, ndoc)
            except Exception:
                logger.exception("Failed to seed %s", ndoc.url)
                continue
            count += 1
            if count % 50 == 0:
                db.commit()
        db.commit()
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = seed()
    print(f"Seeded {n} documents from {SEED_PATH}")
