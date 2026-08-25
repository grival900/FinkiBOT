import logging
import threading

from sqlalchemy.orm import Session

from backend.core.site_settings import get_bool_setting
from backend.db import SessionLocal
from backend.ingestion.chunking import chunk_text
from backend.ingestion.embeddings import embed_texts
from backend.models import Chunk, Document
from backend.scrapers.normalize import NormalizedDocument
from backend.scrapers.registry import SCRAPERS

logger = logging.getLogger(__name__)

_ingestion_lock = threading.Lock()


def upsert_document(db: Session, ndoc: NormalizedDocument) -> tuple[Document, bool]:
    """Inserts or updates a Document by its unique `url`. Returns (document, changed) —
    `changed` is False when the URL was already indexed with identical content, so the
    caller can skip re-chunking/re-embedding unchanged pages."""
    existing = db.query(Document).filter_by(url=ndoc.url).one_or_none()

    if existing is not None and (existing.source != ndoc.source or existing.type != ndoc.type):
        # Two different scrapers producing the same URL is a bug, not a legitimate
        # update — silently "winning" here would overwrite one source's content under
        # the other's source/type label (this happened once: finki_hub.courses and
        # official.subjects both used the official subject URL as their Document.url).
        raise ValueError(
            f"URL collision on {ndoc.url!r}: already indexed as "
            f"{existing.source}/{existing.type}, but {ndoc.source}/{ndoc.type} scraper "
            f"produced the same URL"
        )

    if existing is None:
        # The source site can restructure its URLs wholesale — this happened once when
        # finki.ukim.mk's announcement board migrated off Drupal (see
        # scrapers/official_site/announcements.py's docstring), leaving old and new URLs
        # for the same announcements both indexed and both cited as separate sources for
        # the same answer. When a document with the exact same source/type/title/content
        # already exists under a different URL, treat this as that document moving
        # rather than a new one. Matching on title *and* content_hash (not content_hash
        # alone) matters: some announcements legitimately share boilerplate body text
        # across different real events (e.g. yearly exam-schedule notices whose only
        # distinguishing text lives in a linked spreadsheet we don't parse) — those must
        # stay separate documents, and they always differ by title.
        moved = (
            db.query(Document)
            .filter_by(source=ndoc.source, type=ndoc.type, title=ndoc.title, content_hash=ndoc.content_hash)
            .first()
        )
        if moved is not None:
            moved.url = ndoc.url
            moved.published_at = ndoc.published_at
            moved.doc_metadata = ndoc.metadata
            return moved, False

        doc = Document(
            source=ndoc.source,
            type=ndoc.type,
            title=ndoc.title,
            url=ndoc.url,
            published_at=ndoc.published_at,
            content=ndoc.content,
            content_hash=ndoc.content_hash,
            doc_metadata=ndoc.metadata,
        )
        db.add(doc)
        db.flush()
        return doc, True

    changed = existing.content_hash != ndoc.content_hash
    if changed:
        existing.title = ndoc.title
        existing.content = ndoc.content
        existing.content_hash = ndoc.content_hash
        existing.published_at = ndoc.published_at
        existing.doc_metadata = ndoc.metadata
    return existing, changed


def reindex_document(db: Session, doc: Document) -> None:
    db.query(Chunk).filter(Chunk.document_id == doc.id).delete()

    texts = chunk_text(doc.content)
    if not texts:
        return
    vectors = embed_texts(texts)
    for i, (text, vector) in enumerate(zip(texts, vectors)):
        db.add(Chunk(document_id=doc.id, chunk_index=i, text=text, embedding=vector))


def ingest_normalized_document(db: Session, ndoc: NormalizedDocument) -> tuple[Document, bool]:
    doc, changed = upsert_document(db, ndoc)
    if changed:
        reindex_document(db, doc)
    return doc, changed


def run_ingestion(cadence: str | None = None) -> dict[str, int]:
    """Runs every enabled scraper matching `cadence` ("frequent" or "slow"), or every
    enabled scraper if `cadence` is None. Returns a per-scraper count of documents seen
    (used by /admin/reindex and the scheduler for logging).

    Guarded by a lock so concurrent calls (e.g. scheduler + manual trigger) don't race —
    the frequent and slow scheduler jobs share this same lock, so one running long never
    causes the other to double up on the same source."""
    if not _ingestion_lock.acquire(blocking=False):
        logger.warning("Skipping ingestion — another ingestion is already running")
        return {}
    try:
        return _run_ingestion_locked(cadence)
    finally:
        _ingestion_lock.release()


def run_full_ingestion() -> dict[str, int]:
    """Runs every enabled scraper, regardless of cadence. Slow (see `registry.py`) —
    prefer `run_frequent_ingestion()`/`run_slow_ingestion()` for the scheduler; this is
    for a deliberate one-off full rebuild (`/admin/reindex` with no `cadence`, or
    `python -m backend.scripts.reindex`)."""
    return run_ingestion(cadence=None)


def run_frequent_ingestion() -> dict[str, int]:
    """Runs only frequent-cadence scrapers: cheap JSON feeds and the announcement
    board. Safe to run every scheduler tick."""
    return run_ingestion(cadence="frequent")


def run_slow_ingestion() -> dict[str, int]:
    """Runs only slow-cadence scrapers: sources with no bulk endpoint that require one
    HTTP request per item (official course syllabi, professor profiles, recordings
    pages) and rarely change. Meant for a much longer scheduler interval."""
    return run_ingestion(cadence="slow")


def _run_ingestion_locked(cadence: str | None) -> dict[str, int]:
    stats: dict[str, int] = {}
    with SessionLocal() as db:
        for entry in SCRAPERS:
            if not entry.enabled:
                continue
            # Admin-editable override on top of the hardcoded default — lets an admin
            # disable a misbehaving scraper (e.g. a site layout change breaking it)
            # without a redeploy. Can only turn an enabled scraper off, never turn a
            # hardcoded-disabled stub on (those raise NotImplementedError).
            if not get_bool_setting(db, f"scraper_enabled:{entry.name}", True):
                continue
            if cadence is not None and entry.cadence != cadence:
                continue
            count = 0
            try:
                for ndoc in entry.fn():
                    try:
                        with db.begin_nested():
                            ingest_normalized_document(db, ndoc)
                    except Exception:
                        logger.exception("Failed to ingest %s (%s)", ndoc.url, entry.name)
                        continue
                    count += 1
                    if count % 20 == 0:
                        db.commit()
                db.commit()
            except Exception:
                logger.exception("Scraper %s failed", entry.name)
                db.rollback()
            stats[entry.name] = count
    return stats
