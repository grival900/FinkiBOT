"""Exports the `documents` table to a JSON seed file for fast, fully offline
first-time setup on a new machine: `python -m backend.scripts.export_seed`.

See `seed.py` (the loader) and the root README's "First time on a new machine"
section. Intentionally excludes chunk embeddings — they're cheap and fast to
regenerate locally (a couple of minutes for everything currently indexed) and
re-deriving them avoids shipping vectors tied to a specific embedding model version.

This is a manual snapshot, not something that runs automatically: re-run it after a
full reindex whenever you want to refresh the committed seed with current content,
otherwise it just drifts stale (fine for its purpose — it's a fast bootstrap, not a
freshness guarantee; the scheduler/live reindex is what keeps things current after
setup).
"""

import json
from pathlib import Path

from backend.db import SessionLocal
from backend.models import Document

SEED_PATH = Path(__file__).resolve().parent.parent / "seed" / "documents.json"


def export_seed() -> int:
    with SessionLocal() as db:
        docs = db.query(Document).order_by(Document.source, Document.type, Document.url).all()
        rows = [
            {
                "source": d.source,
                "type": d.type,
                "title": d.title,
                "url": d.url,
                "content": d.content,
                "published_at": d.published_at.isoformat() if d.published_at else None,
                "metadata": d.doc_metadata or {},
            }
            for d in docs
        ]

    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    count = export_seed()
    print(f"Exported {count} documents to {SEED_PATH}")
