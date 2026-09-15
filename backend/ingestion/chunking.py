"""Word-based chunking. Word count is a rough proxy for token count, which is fine here
since chunks only need to be small enough for retrieval + prompt context, not exact."""

import re

DEFAULT_MAX_WORDS = 220
DEFAULT_OVERLAP_WORDS = 40

# Fallback sizing for schedule content with no bracketed per-course records to group by
# (PDF-derived older sessions - see `extract_pdf_text`, which has no per-record
# structure at all, just plain page text). Exam-schedule documents are one whole
# session's worth of grid content (~150-190 courses per file) - at the default chunk
# size, a single chunk would bundle ~15-20 unrelated courses together, diluting the
# embedding for any one course's query into near-noise. A much smaller chunk keeps
# each one closer to a handful of courses, which is what actually lets a course-
# specific query score distinctly instead of matching everything to a similar degree.
SCHEDULE_MAX_WORDS = 50
SCHEDULE_OVERLAP_WORDS = 10

_BRACKETED_RECORD_RE = re.compile(r"\[[^\[\]]*\]")
_RECORD_LEADING_TOKEN_RE = re.compile(r"\[(\S+)")


def chunk_text(text: str, max_words: int = DEFAULT_MAX_WORDS, overlap_words: int = DEFAULT_OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def _pack_records_to_budget(records: list[str], max_words: int) -> list[str]:
    """Packs whole records into chunks of at most `max_words` each. A record is never
    split mid-way (it's already an atomic, self-contained bracketed unit) - but once a
    day's accumulated records would exceed the budget, a new chunk starts, so an
    unusually busy exam day can't reintroduce the same "too many unrelated courses
    sharing one embedding" dilution problem `SCHEDULE_MAX_WORDS` exists to prevent
    (confirmed live: a single ordinary day's records already reached 83 words in real
    data, past the 50-word budget - an actually-busy day would be considerably more)."""
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for record in records:
        record_words = len(record.split())
        if current and current_words + record_words > max_words:
            chunks.append(" ".join(current))
            current = []
            current_words = 0
        current.append(record)
        current_words += record_words
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_schedule_by_date(text: str) -> list[str]:
    """Groups `extract_xlsx_schedule_grid`'s bracket-wrapped "[date time room: course]"
    records by the leading token inside each bracket (the sheet-title date, verbatim -
    e.g. "08.06.2026" or "b-19.06.2026" for a parallel exam group), so every course
    scheduled on the same day ends up in the *same* chunk together (split into more
    than one chunk only if that day's records alone exceed `SCHEDULE_MAX_WORDS` - see
    `_pack_records_to_budget`).

    Plain word-count chunking (what this replaces for schedule content) has no notion
    of a "day" as a unit - a day with several distinct exam entries could get split
    across two chunks by sheer word-count bad luck, and a query matching one of that
    day's courses would then only surface whichever chunk happened to also rank in the
    final top-k, silently leaving the day's other, equally relevant entries out of the
    model's context (confirmed live: a query correctly found one course's exam slot for
    a given day but never surfaced a second, unrelated course also scheduled that same
    day, because it landed in a different chunk that didn't make the cut). Grouping by
    day instead means a query landing on any one of that day's records pulls in the
    whole day (or as much of it as fits the word budget) at once.

    Falls back to plain small-chunk word-based chunking when there are no bracketed
    records at all - PDF-derived older sessions (see `extract_pdf_text`) are just plain
    page text with no per-record structure to group by."""
    records = _BRACKETED_RECORD_RE.findall(text)
    if not records:
        return chunk_text(text, max_words=SCHEDULE_MAX_WORDS, overlap_words=SCHEDULE_OVERLAP_WORDS)

    preamble_end = text.find("[")
    preamble = text[:preamble_end].strip()
    # Just the session name (e.g. "2025/2026 Јуни"), not the download-link line under
    # it - carried into every day's own chunk below. The motivating bug: a bracketed
    # record like "[26.06.2026 ... Маркетинг]" has no lexical connection at all to the
    # session it belongs to, so a query naming a specific session/period ("во јунската
    # сесија") had nothing session-level to match against and could just as easily
    # surface the same course's date from a *different* session's chunk instead
    # (confirmed live). The session name used to only survive as its own standalone
    # preamble chunk, disconnected from every day's actual course records.
    session_label = preamble.splitlines()[0] if preamble else ""

    # dict preserves insertion order, so no separate order-tracking list is needed.
    grouped: dict[str, list[str]] = {}
    for record in records:
        match = _RECORD_LEADING_TOKEN_RE.match(record)
        key = match.group(1) if match else "?"
        grouped.setdefault(key, []).append(record)

    chunks: list[str] = []
    for day_records in grouped.values():
        for day_chunk in _pack_records_to_budget(day_records, SCHEDULE_MAX_WORDS):
            chunks.append(f"{session_label}\n{day_chunk}" if session_label else day_chunk)
    if preamble:
        chunks.insert(0, preamble)
    return chunks


def get_chunks(doc_type: str, text: str) -> list[str]:
    """Chunks `text` using whichever strategy fits `Document.type` - date-grouped for
    schedules, plain word-based chunking (the shared default) for everything else."""
    if doc_type == "schedule":
        return chunk_schedule_by_date(text)
    return chunk_text(text)
