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

from backend.core.auth import hash_password
from backend.db import SessionLocal
from backend.ingestion.pipeline import ingest_normalized_document
from backend.models import User
from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "seed" / "documents.json"

# Fixed dev-bootstrap admin credentials — unlike create_admin.py (which only promotes
# an already-registered account, precisely to avoid a script-supplied password), a
# fresh machine needs *some* way into /admin without a live SMTP setup to register
# through first. Idempotent: skipped if the account already exists.
SEED_ADMIN_EMAIL = "admin@email.com"
SEED_ADMIN_PASSWORD = "admin"


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


def seed_admin() -> bool:
    """Creates the default admin@email.com/admin account if it doesn't exist yet.
    Returns whether it was created."""
    with SessionLocal() as db:
        if db.query(User).filter_by(email=SEED_ADMIN_EMAIL).one_or_none() is not None:
            return False
        db.add(User(email=SEED_ADMIN_EMAIL, password_hash=hash_password(SEED_ADMIN_PASSWORD), is_admin=True))
        db.commit()
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = seed()
    print(f"Seeded {n} documents from {SEED_PATH}")
    if seed_admin():
        print(f"Created admin account {SEED_ADMIN_EMAIL} (password: {SEED_ADMIN_PASSWORD})")
    else:
        print(f"Admin account {SEED_ADMIN_EMAIL} already exists")
