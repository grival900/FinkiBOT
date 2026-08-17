from sqlalchemy.orm import Session

from backend.models import Document, SentNotification, Subscription


def matches_filters(doc: Document, filters: dict) -> bool:
    """Announcements aren't currently tagged with structured course codes (the official
    scraper doesn't extract that), so course_codes are matched the same way as free-text
    keywords: as a case-insensitive substring of the title+content. An empty filter set
    means "notify on every new announcement"."""
    terms = [t.lower() for t in [*filters.get("keywords", []), *filters.get("course_codes", [])]]
    if not terms:
        return True
    haystack = f"{doc.title}\n{doc.content}".lower()
    return any(term in haystack for term in terms)


def find_unsent_matches(db: Session, subscription: Subscription) -> list[Document]:
    already_sent_ids = {
        row.document_id
        for row in db.query(SentNotification.document_id).filter_by(subscription_id=subscription.id)
    }
    announcements = db.query(Document).filter_by(source="official", type="announcement").all()
    return [
        doc
        for doc in announcements
        if doc.id not in already_sent_ids and matches_filters(doc, subscription.filters)
    ]
