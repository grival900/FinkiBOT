import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.schemas import DocumentOut
from backend.core.prerequisites import resolve_prerequisites
from backend.db import get_db
from backend.models import Document

router = APIRouter(prefix="/documents", tags=["documents"])


def _with_resolved_prerequisites(doc: Document, db: Session) -> dict:
    """Course documents' `accreditations[].Предуслов` is plain text — this resolves it
    into `prerequisite_links` (course name + document_id when it matches an indexed
    course) without touching the stored metadata, computed fresh on every read since
    which courses are indexed can change between reindexes."""
    metadata = dict(doc.doc_metadata)
    if doc.type != "course" or not metadata.get("accreditations"):
        return metadata

    accreditations = []
    for acc in metadata["accreditations"]:
        acc = dict(acc)
        prereq_text = acc.get("Предуслов")
        if prereq_text:
            acc["prerequisite_links"] = resolve_prerequisites(db, prereq_text)
        accreditations.append(acc)
    metadata["accreditations"] = accreditations
    return metadata


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentOut:
    """Serves a single indexed document in full — backs the internal course/page detail
    view so search results don't have to send students to an external site to read
    what we already scraped and stored ourselves."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found") from None

    doc = db.get(Document, doc_uuid)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentOut(
        id=str(doc.id),
        source=doc.source,
        type=doc.type,
        title=doc.title,
        url=doc.url,
        published_at=doc.published_at,
        content=doc.content,
        doc_metadata=_with_resolved_prerequisites(doc, db),
    )
