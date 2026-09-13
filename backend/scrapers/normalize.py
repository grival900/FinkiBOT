"""Common schema scrapers normalize into, decoupled from the DB layer.

Each source-specific scraper (official_site, finki_hub) yields `NormalizedDocument`
instances; the ingestion pipeline is the only place that touches SQLAlchemy models.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Source = Literal["official", "finki_hub"]
# "exam" documents are the per-row product of ingestion/spreadsheet.py: one exam-session
# spreadsheet, one document per parsed row (course/date/time/room, whatever columns that
# particular file actually has) — see that module's docstring. Distinct from "schedule",
# which stays link-only (title + URL, no file contents) for whatever couldn't be
# downloaded/parsed, so chat.py's system prompt can tell the two apart.
DocumentType = Literal[
    "announcement", "course", "professor", "staff", "thesis", "schedule", "material", "exam", "consultation"
]


@dataclass
class NormalizedDocument:
    source: Source
    type: DocumentType
    title: str
    url: str
    content: str
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def clean(self) -> "NormalizedDocument":
        """Collapse whitespace in title/content. Scrapers should call this before yielding."""
        self.title = " ".join(self.title.split())
        self.content = "\n".join(line.strip() for line in self.content.splitlines() if line.strip())
        return self
    