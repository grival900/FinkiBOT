"""Turns a course's plain-text prerequisite field into resolved links to the
prerequisite course's own indexed document, so a student can click through a
course's requirement chain instead of just reading inert text.

Prerequisite text (`accreditations[].Предуслов` on finki_hub course documents,
captured from the finki-hub detail dialog) lists one or more course names, joined
with " или " (or) when there are alternatives, e.g. "Алгоритми и податочни
структури или Примена на алгоритми и податочни структури" — or isn't a course at
all, e.g. "100 кредити" (a credit threshold). We only ever link segments that
exactly match an indexed course title (case-insensitive); anything else is left as
plain text rather than risk pointing at the wrong course.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import Document


def split_prerequisite_text(text: str | None) -> list[str]:
    """Pure parsing step, unit-testable without a DB. Splits comma-separated
    requirements and "или" (or) alternatives into candidate course-name segments."""
    if not text:
        return []
    segments = []
    for part in text.split(","):
        segments.extend(part.split(" или "))
    return [s.strip() for s in segments if s.strip()]


def resolve_prerequisites(db: Session, text: str) -> list[dict]:
    """Returns one entry per candidate segment: {"text": segment, "document_id": id-or-None}
    — `document_id` is None for segments that don't exactly match an indexed course
    title (e.g. "100 кредити"), which the frontend renders as plain, unlinked text.

    Deliberately matches only `source="finki_hub"` course documents, even though
    `official/course` (syllabus) documents can share the same title: finki_hub course
    pages are the ones with their own `prerequisite_links` already resolved, so
    linking there lets a student keep clicking through the whole requirement chain —
    landing on a syllabus page instead would dead-end it after one hop."""
    results = []
    for segment in split_prerequisite_text(text):
        doc = (
            db.query(Document)
            .filter(
                Document.type == "course",
                Document.source == "finki_hub",
                func.lower(Document.title) == segment.lower(),
            )
            .first()
        )
        results.append({"text": segment, "document_id": str(doc.id) if doc else None})
    return results
