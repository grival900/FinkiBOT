"""One-off cleanup for documents indexed twice under different URLs before the
upsert-time fix in `ingestion/pipeline.py::upsert_document` existed: `python -m
backend.scripts.dedupe_documents [--dry-run]`.

Finds groups of documents sharing the same (source, type, title, content_hash) —
genuine duplicates of the same real-world item under a different URL (this happened
once when finki.ukim.mk's announcement board migrated off Drupal, leaving both the
old and new URLs indexed for the same announcements and both cited as separate
sources for the same answer). Deliberately requires an exact title match, not just
content_hash: some announcements legitimately share boilerplate body text across
different real events, and those always differ by title, so they're left alone.

Idempotent — safe to re-run; a clean database finds nothing to merge. For each
group, keeps one document (preferring a URL under /announcements/, the site's
current path, over a legacy one — see announcements.py's docstring — and otherwise
the earliest-scraped row) and deletes the rest, which cascades to their chunks.
"""

import sys

from sqlalchemy import func, select

from backend.db import SessionLocal
from backend.models import Document

CURRENT_PATH_MARKER = "/announcements/"


def _pick_canonical(docs: list[Document]) -> Document:
    for doc in docs:
        if CURRENT_PATH_MARKER in doc.url:
            return doc
    return min(docs, key=lambda d: d.scraped_at)


def find_duplicate_groups(db) -> list[list[Document]]:
    dupe_keys = (
        db.query(Document.source, Document.type, Document.title, Document.content_hash)
        .group_by(Document.source, Document.type, Document.title, Document.content_hash)
        .having(func.count(Document.id) > 1)
        .all()
    )
    groups = []
    for source, type_, title, content_hash in dupe_keys:
        stmt = select(Document).filter_by(source=source, type=type_, title=title, content_hash=content_hash)
        groups.append(list(db.execute(stmt).scalars().all()))
    return groups


def dedupe(dry_run: bool = False) -> int:
    removed = 0
    with SessionLocal() as db:
        for group in find_duplicate_groups(db):
            canonical = _pick_canonical(group)
            for doc in group:
                if doc.id == canonical.id:
                    continue
                print(f"  duplicate of {canonical.url!r}: removing {doc.url!r} ({doc.title!r})")
                if not dry_run:
                    db.delete(doc)
                removed += 1
        if not dry_run:
            db.commit()
    return removed


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    n = dedupe(dry_run=dry_run)
    verb = "Would remove" if dry_run else "Removed"
    print(f"{verb} {n} duplicate document(s).")
