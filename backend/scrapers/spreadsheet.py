"""Turns a downloaded .xlsx file into indexable per-row documents.

Before this module, exam-session/consultation spreadsheets (see
`official_site/schedule_links.py` and `finki_hub/sessions.py`) were indexed as a bare
title + download link — the assistant could point a student at the right file but
could never state a date, room, or time itself, since none of that text was ever
actually indexed. This module is what closes that gap: it reads every sheet, finds the
header row, and renders each data row as `header: value` lines, one small document per
row, so retrieval can match "кога имам испит по <предмет>" directly against a row that
says so.

Deliberately layout-agnostic. These files are maintained by different professors/admin
staff with no shared template — column order, language, and even which facts are
present (course vs. student name, date vs. term, room vs. online link) vary file to
file. Rather than hardcode a schema, this just pairs up whatever the header row
actually says with whatever's in ecah data row underneath it, and skips a sheet
entirely if it can't even find a plausible header. That means it can't be certain a
given column *means* "exam date" rather than something else — it hands the raw
labelled facts to retrieval/the LLM and lets them make sense of it, same as any other
scraped page in this project.
"""

import io
import logging
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook

from backend.scrapers.normalize import NormalizedDocument

logger = logging.getLogger(__name__)

# A row with fewer non-empty cells than this can't plausibly be a header (a single
# stray value in column A is almost always a merged title/banner cell above the real
# table, not the table itself).
_MIN_HEADER_CELLS = 2

# Hard cap on how many rows a single workbook can contribute, across all its sheets.
# Real exam-session files can legitimately be large — one sheet per exam date, each
# listing every student registered for that slot — so this is a safety ceiling against
# a truly pathological file (a "dirty" used-range far bigger than any real table,
# where someone once selected/formatted thousands of otherwise-empty rows), not a
# expected-size limit. Every non-empty row becomes its own indexed document with its
# own embedding computed on CPU, so raising this trades reindex time for coverage —
# if a real file still hits this cap, consider running that reindex pass off-hours
# rather than lowering it further.
_MAX_ROWS_PER_WORKBOOK = 500


@dataclass
class SpreadsheetRow:
    sheet: str
    row_number: int  # 1-based, matching what a person looking at the file would count
    values: dict[str, str] = field(default_factory=dict)  # header -> cell text, non-empty only

    def as_text(self) -> str:
        return "\n".join(f"{header}: {value}" for header, value in self.values.items())

    @property
    def label(self) -> str:
        """Best short name for this row (used as a document title) — the first
        non-empty cell, which across every schedule/consultation file inspected so far
        is the course or person the row is actually about."""
        for value in self.values.values():
            if value:
                return value
        return f"ред {self.row_number}"


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _find_header_row(rows: list[tuple]) -> int | None:
    for i, row in enumerate(rows):
        if sum(1 for c in row if _cell_text(c)) >= _MIN_HEADER_CELLS:
            return i
    return None


def _fill_merged_cells(source_rows: list[list], target_rows: list[list], merged_ranges) -> None:
    """Propagates each merged range's top-left value to every cell it covers.

    openpyxl only ever returns a value for the top-left cell of a merged range — every
    other cell in it comes back as `None`, even though visually (and in the source
    file's intent) the whole range shares that one value. A grid-shaped exam schedule
    (rooms as columns, time slots as rows, one merged cell spanning every room+time the
    course actually occupies) relies entirely on that shared meaning: without filling
    the merge, only the single top-left room/time combination is ever seen, silently
    dropping every other room the same exam uses.

    Every top-left value is read from `source_rows` — a pristine, never-mutated copy —
    while all propagation writes go to `target_rows`. This matters when a sheet has
    several separate merges close together (e.g. one wide merge for a shared exam next
    to several independent single-column merges for unrelated courses): reading top-left
    values from a list that earlier merges had already written into risked one merge's
    fill silently overwriting the very cell another merge needed to read its own,
    different, course name from — corrupting that room's course into the wrong one.
    Reading exclusively from the untouched source avoids that entirely."""
    for merged_range in merged_ranges:
        min_row, min_col = merged_range.min_row, merged_range.min_col
        max_row, max_col = merged_range.max_row, merged_range.max_col
        if min_row - 1 >= len(source_rows):
            continue
        top_left_row = source_rows[min_row - 1]
        if min_col - 1 >= len(top_left_row):
            continue
        value = top_left_row[min_col - 1]
        if value is None:
            continue
        for r in range(min_row, max_row + 1):
            if r - 1 >= len(target_rows):
                continue
            row = target_rows[r - 1]
            while len(row) <= max_col - 1:
                row.append(None)
            for c in range(min_col, max_col + 1):
                if row[c - 1] is None:
                    row[c - 1] = value


def extract_rows(data: bytes) -> list[SpreadsheetRow]:
    """Parses every sheet of an .xlsx workbook into `SpreadsheetRow`s. Never raises for
    a file it can't make sense of (unexpected layout, empty sheet) — worst case it
    returns fewer rows, or none, and the caller falls back to the plain link-only
    document it already had. Raises only if `data` isn't a readable .xlsx at all
    (wrong file type entirely), which callers are expected to catch."""
    # Not read_only: merged-cell ranges (needed to fill grid-shaped schedules — see
    # `_fill_merged_cells`) aren't exposed by openpyxl's read-only worksheet at all
    # (`ReadOnlyWorksheet` has no `merged_cells` attribute). The row cap above already
    # bounds how much a pathological file can cost us, so the extra memory of a normal
    # load is an acceptable trade for actually seeing merges.
    workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    results: list[SpreadsheetRow] = []

    for sheet in workbook.worksheets:
        if len(results) >= _MAX_ROWS_PER_WORKBOOK:
            logger.warning(
                "Workbook hit the %d-row cap before sheet %r — remaining sheets skipped",
                _MAX_ROWS_PER_WORKBOOK,
                sheet.title,
            )
            break
        try:
            raw_rows = list(sheet.iter_rows(values_only=True))
        except Exception:
            logger.warning("Could not read sheet %r", sheet.title, exc_info=True)
            continue

        # Header detection runs on the *unfilled* rows: a full-width merged banner
        # (e.g. a date title spanning the whole sheet) has only one real value, so it
        # correctly looks like "1 non-empty cell" and gets skipped in favour of the
        # real header row underneath it. Filling merges first would make that banner
        # look like a wide header instead, which is exactly backwards.
        header_idx = _find_header_row(raw_rows)
        if header_idx is None:
            continue

        filled_rows = [list(row) for row in raw_rows]
        try:
            merged_ranges = list(sheet.merged_cells.ranges)
        except Exception:
            merged_ranges = []
        if merged_ranges:
            _fill_merged_cells(raw_rows, filled_rows, merged_ranges)

        headers = [_cell_text(c) or f"колона {i + 1}" for i, c in enumerate(filled_rows[header_idx])]

        for offset, row in enumerate(filled_rows[header_idx + 1 :]):
            if len(results) >= _MAX_ROWS_PER_WORKBOOK:
                logger.warning(
                    "Sheet %r hit the %d-row cap — remaining rows in this sheet skipped",
                    sheet.title,
                    _MAX_ROWS_PER_WORKBOOK,
                )
                break
            values = {h: t for h, c in zip(headers, row) if (t := _cell_text(c))}
            if not values:
                continue
            results.append(SpreadsheetRow(sheet=sheet.title, row_number=header_idx + offset + 2, values=values))

    return results


def rows_to_documents(
    rows: list[SpreadsheetRow],
    *,
    source: str,
    file_title: str,
    file_url: str,
    extra_metadata: dict[str, Any] | None = None,
) -> list[NormalizedDocument]:
    """One `type=exam` NormalizedDocument per row. `file_url` stays the real
    downloadable file for every row (so "open the original" always works) — each row
    gets a `#sheet-rownumber` fragment appended to make its own URL unique, since
    `Document.url` is the ingestion pipeline's dedupe key (see
    `ingestion/pipeline.py::upsert_document`) and every row from the same file would
    otherwise collide on one URL."""
    base_metadata = extra_metadata or {}
    documents = []
    for row in rows:
        content = f"{file_title} ({row.sheet})\n{row.as_text()}\n\nЛинк за преземање: {file_url}"
        metadata = {**base_metadata, "sheet": row.sheet, "row": row.row_number, **row.values}
        documents.append(
            NormalizedDocument(
                source=source,
                type="exam",
                title=f"{file_title} — {row.label}",
                url=f"{file_url}#{row.sheet}-{row.row_number}",
                content=content,
                metadata=metadata,
            ).clean()
        )
    return documents