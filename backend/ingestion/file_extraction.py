"""Shared, reusable extractors for turning a downloaded file's raw bytes into plain
text — used both by the exam-session scraper (persisted into the index) and by the
quiz feature (`backend/quiz/extraction.py`, ephemeral). Kept in `ingestion/` rather than
under `quiz/` or `scrapers/` since both of those depend on it, not the other way round.
"""

import datetime
import io
import re
from collections import Counter

from openpyxl import load_workbook
from pypdf import PdfReader


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _normalize_ws(value: str) -> str:
    """Some cells carry an embedded line break (e.g. a room label like "АМФ \nФИНКИ
    Г") — collapsed to one space so it can never split a "date time room: course"
    line across two physical lines."""
    return re.sub(r"\s+", " ", value).strip()


_SHEET_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _parse_sheet_date(title: str) -> datetime.datetime | None:
    """Sheet titles are the exam day, e.g. "08.06.2026", sometimes with a trailing
    "(Понеделник)" day-name annotation - not consistently zero-padded across all files
    (some sheets are titled e.g. "5.6.2023" instead of "05.06.2023", since these are
    hand-prepared per session/year), hence 1-or-2-digit day/month. Used to derive the
    session's `published_at` from its earliest sheet, so recency ranking can prefer
    this year's session over an older one with near-identical content (see `chat.py`'s
    `prefer_current_year`)."""
    match = _SHEET_DATE_RE.match(title.strip())
    if match is None:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return datetime.datetime(year, month, day)
    except ValueError:
        return None


def _slot_duration(times: list[datetime.time]) -> datetime.timedelta:
    """The grid's row-to-row step (typically 30 minutes) - the minimum positive gap
    between any two distinct time-of-day values actually seen in the sheet, so a
    course's real end time (one slot past its last occupied row) can be computed
    instead of reported as that row's own *start* label. Falls back to 30 minutes
    when the sheet has too few distinct times to measure a gap from (e.g. a single
    exam slot all day)."""
    distinct = sorted(set(times))
    if len(distinct) < 2:
        return datetime.timedelta(minutes=30)
    base = datetime.date(2000, 1, 1)
    gaps = (
        datetime.datetime.combine(base, b) - datetime.datetime.combine(base, a)
        for a, b in zip(distinct, distinct[1:])
    )
    return min(gaps)


def _group_contiguous_runs(
    entries: list[tuple[datetime.time, str]], slot_duration: datetime.timedelta
) -> list[tuple[datetime.time, datetime.time, set[str]]]:
    """Splits one course's (time, room) occurrences on a day into contiguous time
    runs, keyed on time alone: a gap larger than one slot means a genuinely separate
    offering (e.g. a morning shift and an afternoon shift of the same large course,
    or two different group-sections both scheduled under the same course text) that
    must not be bridged into one bogus wide range, while several rooms at the *same*
    time (a large enrollment split across overflow rooms) correctly stay one run.
    Returns (start, end, rooms) per run, with `end` computed as the run's last slot
    plus `slot_duration` - the actual end of that slot, not just its start label."""
    ordered = sorted(entries, key=lambda e: e[0])
    base = datetime.date(2000, 1, 1)
    runs: list[list[tuple[datetime.time, str]]] = []
    for time_value, room in ordered:
        if runs and (
            datetime.datetime.combine(base, time_value) - datetime.datetime.combine(base, runs[-1][-1][0])
        ) <= slot_duration:
            runs[-1].append((time_value, room))
        else:
            runs.append([(time_value, room)])

    result: list[tuple[datetime.time, datetime.time, set[str]]] = []
    for run in runs:
        start = run[0][0]
        end = (datetime.datetime.combine(base, run[-1][0]) + slot_duration).time()
        rooms = {room for _, room in run}
        result.append((start, end, rooms))
    return result


def _resolve_merged_cells(ws) -> dict[tuple[int, int], object]:
    """Merged ranges (common in these sheets — a course commonly spans several
    time-rows and/or room-columns at once) only carry their value on the top-left
    cell; `iter_rows(values_only=True)` returns None for every other cell in the
    range. Returns a {(row, col): value} override map for every cell in every range."""
    overrides: dict[tuple[int, int], object] = {}
    for merged_range in ws.merged_cells.ranges:
        top_left = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
        if top_left is None:
            continue
        for row in range(merged_range.min_row, merged_range.max_row + 1):
            for col in range(merged_range.min_col, merged_range.max_col + 1):
                overrides[(row, col)] = top_left
    return overrides


def _fill_key(cell) -> tuple | None:
    """A comparable identity for a cell's solid background fill, or None for no/non-
    solid fill. openpyxl represents a fill color as either a direct RGB string or a
    theme index + tint, never both, so the key has to branch on which one is set -
    two cells "look the same color" only when both the kind of color reference and its
    value match."""
    fill = cell.fill
    if fill is None or fill.patternType != "solid":
        return None
    fg = fill.fgColor
    if fg.type == "rgb":
        return ("rgb", fg.rgb)
    if fg.type == "theme":
        return ("theme", fg.theme, fg.tint)
    return None


def _resolve_color_blocks(ws, cell_value, header_row_index: int) -> dict[tuple[int, int], object]:
    """Some session sheets mark a course's whole room/time block purely with matching
    solid cell-fill color instead of an actual Excel merge - confirmed live: a real
    September session's "Структурно програмирање" renders as a solid red rectangle
    spanning 08:00-14:00 across 9 rooms, but only its top-left cell (08:00, лаб. 2)
    actually has the course name; every other cell in that rectangle is blank, telling
    it apart from a genuinely empty slot only by sharing that same fill color.
    `_resolve_merged_cells` sees nothing there at all (there is no merge), so without
    this the extractor could only ever report that single top-left cell - exactly the
    "08:00-08:30, лаб. 2 only" bug this fixes.

    Flood-fills every 4-connected run of same-colored *empty* cells outward from its
    anchor (the one cell in the run with real text) and returns a {(row, col): value}
    override map for the rest of the run, same shape as `_resolve_merged_cells`'s
    result so both can feed the same `cell_value` lookup. A plain bounding-rectangle
    assumption isn't enough on its own: the real example above has another booking
    ("Гости Израел", its own genuine merge with a different fill) carved out of the
    middle of one column, making the true shape notched rather than a clean
    rectangle - flood fill naturally stops at that boundary since the colors differ,
    where a rectangle-expansion approach would either swallow the unrelated booking or
    stop too early and under-report the real block's other columns.

    Bounded to the sheet's own body rows/columns (below the header row, from column B
    on) so it can never run away into a banner row or a differently-colored legend
    column that also happens to use solid fills for unrelated styling reasons."""
    rows = range(header_row_index + 1, ws.max_row + 1)
    cols = range(2, ws.max_column + 1)

    def fill_key(row: int, col: int) -> tuple | None:
        return _fill_key(ws.cell(row=row, column=col))

    visited: set[tuple[int, int]] = set()
    overrides: dict[tuple[int, int], object] = {}

    for row in rows:
        for col in cols:
            if (row, col) in visited:
                continue
            value = cell_value(row, col)
            if value in (None, ""):
                continue
            anchor_key = fill_key(row, col)
            if anchor_key is None:
                continue
            visited.add((row, col))
            stack = [(row, col)]
            while stack:
                r, c = stack.pop()
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if nr not in rows or nc not in cols or (nr, nc) in visited:
                        continue
                    if cell_value(nr, nc) not in (None, ""):
                        continue
                    if fill_key(nr, nc) != anchor_key:
                        continue
                    visited.add((nr, nc))
                    overrides[(nr, nc)] = value
                    stack.append((nr, nc))
    return overrides


def _representative_date(dates: list[datetime.datetime]) -> datetime.datetime:
    """The median of the *majority year's* dates, not the plain median or minimum -
    specifically because both are sensitive to a single bad outlier, and FINKI's own
    spreadsheets do contain them: confirmed live, one real session file has a sheet
    titled "16.06.2025" sitting between "15.06.2026" and "17.06.2026" - a one-off
    typo, not a code bug. Taking `min()` there drags `published_at` a full year off,
    which `prefer_current_year` (chat.py) treats as "wrong year entirely" and drops
    the whole document from the model's context even though it's the most relevant
    result - confirmed live, this silently excluded the correct June exam-session
    document from a query that should have surfaced it.

    A plain median is *also* not enough on its own: for a file with only two dated
    sheets, the lower-median is mathematically identical to `min()` (a 1-1 split has
    no "majority" for the median to land on), so a single mistyped sheet in a short
    2-day colloquium round would reproduce the exact same bug. Filtering to whichever
    calendar year has more sheets first (breaking a true tie by keeping every
    candidate, since there's genuinely no way to tell which of two equally-sized
    year-clusters is the typo without external information) makes this robust for
    any file with 3+ sheets and a minority of typos, which covers every real case
    seen so far; a file with exactly two sheets split 1-1 between two different years
    remains a genuine, rare, irreducible ambiguity."""
    year_counts = Counter(d.year for d in dates)
    majority_year, majority_count = year_counts.most_common(1)[0]
    runner_up_count = year_counts.most_common(2)[1][1] if len(year_counts) > 1 else 0
    candidates = [d for d in dates if d.year == majority_year] if majority_count > runner_up_count else dates

    ordered = sorted(candidates)
    return ordered[(len(ordered) - 1) // 2]


def extract_xlsx_schedule_grid(data: bytes) -> tuple[str, datetime.datetime | None]:
    """FINKI's exam-session spreadsheets are not flat tables: one sheet per exam day
    (sheet title = the date), a header row of room/lab labels across columns, and a
    time-of-day down column A with the course occupying whichever room-column it is
    scheduled in for that row. A course commonly spans a merged range covering several
    consecutive time-rows (its duration) and/or several room-columns (overflow rooms
    for a large enrollment) at once - read naively that produces the same course
    repeated once per half-hour increment it spans, which is what this function
    collapses: all (time, room) slots for the same course on the same day are grouped
    by contiguous time (see `_group_contiguous_runs`) into one self-contained
    "[<date> <start>-<end> <rooms>: <course>]" record per run, with `end` computed as
    that run's last occupied slot plus the sheet's own row-to-row step (see
    `_slot_duration`) - not just that slot's own start label, which would report every
    multi-row exam as ending one slot early. Grouping by contiguous time rather than
    by course name alone also means two genuinely separate offerings of the same
    course on the same day (e.g. a morning shift and an afternoon shift of a large
    first-year course) become two separate records instead of one bogus block
    spanning the gap between them. So word-based chunking downstream can never split
    a course away from its own date/time/room, and no chunk is wasted on near-
    duplicate lines. Bracket-wrapped,
    not just newline-separated: `chunk_text` splits on any whitespace and rejoins with
    a single space, so a plain newline between records doesn't survive into the actual
    chunk text a busy day packs several adjacent records with nothing to tell them
    apart, and a model reading the run-on result can misattribute one record's time to
    an unrelated neighbouring course.

    A worksheet whose title doesn't parse as a plain date at all (e.g. "b-25.06.2026")
    is skipped entirely - see the loop below for why.

    Returns (text, representative_date) - a representative parsed sheet date (see
    `_representative_date`), for the caller to use as the document's `published_at`
    (None if no sheet title parsed as a date, e.g. an unexpected layout)."""
    wb = load_workbook(io.BytesIO(data), data_only=True)
    lines: list[str] = []
    sheet_dates: list[datetime.datetime] = []

    for ws in wb.worksheets:
        date = ws.title.strip()
        parsed_date = _parse_sheet_date(date)
        if parsed_date is None:
            # Confirmed live: some session files carry extra sheets whose title isn't a
            # plain date at all (e.g. "b-25.06.2026") but whose *content* is otherwise a
            # normal day of exam records — and the exact same "b-" block, byte for byte,
            # turned up in two different session files (2025/2026 June and 2025/2026
            # September), which only makes sense as leftover sheets carried over between
            # files rather than a second real exam group. Since there's no reliable way
            # to tell a genuine non-date sheet apart from this kind of stale carryover,
            # and either way `_representative_date` couldn't use it, skip the sheet
            # entirely rather than indexing content that isn't reliably this session's.
            continue
        sheet_dates.append(parsed_date)
        overrides = _resolve_merged_cells(ws)

        def cell_value(row: int, col: int):
            # Not `overrides.get((row, col), ws.cell(...).value)` - dict.get evaluates
            # its default argument eagerly regardless of whether the key hits, so that
            # form would pay for a real openpyxl Cell lookup on every call, defeating
            # the whole point of precomputing `overrides`.
            if (row, col) in overrides:
                return overrides[(row, col)]
            return ws.cell(row=row, column=col).value

        # Row 1 is a full-width merged day banner (not a header), row 2 holds the
        # room/lab labels, row 3+ are data rows with a time-of-day in column A - so the
        # header row is whichever one directly precedes the first data row, not just
        # "the first row that looks header-shaped" (the banner row, once its merge is
        # resolved, would otherwise look like one too).
        first_data_row = None
        for row in range(1, ws.max_row + 1):
            if isinstance(cell_value(row, 1), (datetime.time, datetime.datetime)):
                first_data_row = row
                break

        if first_data_row is None or first_data_row == 1:
            continue
        header_row_index = first_data_row - 1
        header = {
            col: _normalize_ws(str(v))
            for col in range(2, ws.max_column + 1)
            if (v := cell_value(header_row_index, col)) not in (None, "")
        }
        if not header:
            continue

        # A course whose block is drawn with matching cell-fill color rather than an
        # actual merge (see `_resolve_color_blocks`) - falls back to `cell_value`
        # itself wherever no such block was found, so this is a strict superset of it.
        color_overrides = _resolve_color_blocks(ws, cell_value, header_row_index)

        def cell_value_with_color(row: int, col: int):
            value = cell_value(row, col)
            if value not in (None, ""):
                return value
            return color_overrides.get((row, col))

        # course -> (time, room) occurrences, in row order
        occurrences: dict[str, list[tuple[datetime.time, str]]] = {}
        all_row_times: list[datetime.time] = []
        for row in range(header_row_index + 1, ws.max_row + 1):
            time_value = cell_value(row, 1)
            if not isinstance(time_value, (datetime.time, datetime.datetime)):
                continue
            if isinstance(time_value, datetime.datetime):
                time_value = time_value.time()
            all_row_times.append(time_value)

            for col, room in header.items():
                course = cell_value_with_color(row, col)
                if course in (None, "", ".") or not str(course).strip():
                    continue
                course = _normalize_ws(str(course))
                occurrences.setdefault(course, []).append((time_value, room))

        slot_duration = _slot_duration(all_row_times)
        for course, entries in occurrences.items():
            for start, end, rooms in _group_contiguous_runs(entries, slot_duration):
                time_range = f"{start:%H:%M}-{end:%H:%M}"
                rooms_str = ", ".join(sorted(rooms))
                # Bracket-wrapped rather than just newline-separated: `chunk_text` splits on
                # *any* whitespace (`text.split()`) and rejoins with a single space, so a
                # plain newline between records never survives into the actual chunk text a
                # dense day produces several adjacent records back to back with nothing to
                # tell them apart, and a model reading that run-on text can misattribute one
                # record's time/room to its unrelated neighbour (confirmed live: a course's
                # start time got paired with the *next*, different course's end time this
                # way). The brackets are a boundary marker robust to that rejoin.
                lines.append(f"[{date} {time_range} {rooms_str}: {course}]")

    return "\n".join(lines), (_representative_date(sheet_dates) if sheet_dates else None)
