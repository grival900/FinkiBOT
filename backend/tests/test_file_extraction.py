from datetime import datetime
from pathlib import Path

from backend.ingestion.file_extraction import extract_pdf_text, extract_xlsx_schedule_grid

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_pdf_text_returns_readable_text():
    data = (FIXTURES / "sample_exam_schedule.pdf").read_bytes()
    text = extract_pdf_text(data)

    # This older-format session file lists courses in a flat Предмет/Термин/Простории
    # table, unlike the xlsx grid format below.
    assert "Дискретна математика" in text
    assert "лаб" in text


def test_extract_xlsx_schedule_grid_collapses_merged_slots_into_one_line_per_course():
    data = (FIXTURES / "sample_exam_schedule.xlsx").read_bytes()
    text, published_at = extract_xlsx_schedule_grid(data)
    lines = text.splitlines()

    # published_at is the earliest sheet date (the fixture's two sheets are 08.06.2026
    # and 09.06.2026) — used so recency ranking can prefer this session over an older
    # one with near-identical content.
    assert published_at == datetime(2026, 6, 8)

    # The fixture is a 2-sheet (2-day) trim of a real session file. Each course should
    # appear exactly once per day, with its time range and every room it's scheduled in
    # on a single self-contained, bracket-wrapped record, not once per half-hour slot
    # / room it spans. Brackets (not just the newline the records are also joined
    # with) are the real boundary marker: `chunk_text` discards newlines when it
    # re-chunks, so brackets are what keeps a busy day's back-to-back records from
    # reading as one run-on blob a model could misattribute across.
    matching = [line for line in lines if "Дистрибуирани системи" in line]
    assert len(matching) == 1
    # The real merge spans the 08:00 and 08:30 grid rows (a one-hour block) - the end
    # time must be the last occupied slot's *end* (09:00), not that slot's own start
    # label (08:30), which is what the code used to (incorrectly) report.
    assert matching[0] == "[08.06.2026 08:00-09:00 117: Дистрибуирани системи]"

    # A course spanning several room-columns at the same time collapses into one line
    # listing all of them, rather than one line per room.
    interactive_lines = [line for line in lines if "Интерактивни апликации" in line]
    assert len(interactive_lines) == 1
    assert "лаб. 2" in interactive_lines[0]
    assert "лаб. 3" in interactive_lines[0]

    # Two distinct sheets (days) both contributed records.
    assert any(line.startswith("[08.06.2026") for line in lines)
    assert any(line.startswith("[09.06.2026") for line in lines)


def test_extract_xlsx_schedule_grid_splits_disjoint_same_course_occurrences():
    """The motivating bug: the same course text can legitimately occupy two disjoint
    time blocks the same day (e.g. a morning shift and an unrelated afternoon shift
    of a large course, or two different group-sections both scheduled under the same
    course name). Grouping purely by course name and taking min/max across all its
    occurrences bridged these into one bogus wide range implying one continuous
    block; grouping by contiguous time keeps genuinely separated occurrences as two
    accurate records instead - while still merging truly-adjacent merge blocks (see
    the fixture-based test above, where two adjacent merged ranges for the same
    course correctly stay one continuous run)."""
    import io
    from datetime import time as dtime

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "10.09.2026"
    ws["B2"] = "лаб. 1"
    ws["A3"] = dtime(8, 0)
    ws["B3"] = "Оперативни системи"
    # Establishes the grid's real 30-minute slot duration (via the 08:00->08:30 gap)
    # independently of the two far-apart "Оперативни системи" rows below - without
    # this, the only two distinct times in the sheet would be 6 hours apart and
    # `_slot_duration` would (wrongly, for this synthetic sheet) treat 6 hours as the
    # grid's own step size, making the two occurrences look "contiguous".
    ws["A4"] = dtime(8, 30)
    ws["B4"] = "Друг предмет"
    ws["A5"] = dtime(14, 0)
    ws["B5"] = "Оперативни системи"
    buf = io.BytesIO()
    wb.save(buf)

    text, _ = extract_xlsx_schedule_grid(buf.getvalue())
    lines = text.splitlines()

    matching = [line for line in lines if "Оперативни системи" in line]
    assert len(matching) == 2
    assert "[10.09.2026 08:00-08:30 лаб. 1: Оперативни системи]" in matching
    assert "[10.09.2026 14:00-14:30 лаб. 1: Оперативни системи]" in matching


def test_extract_xlsx_schedule_grid_skips_sheets_whose_title_is_not_a_plain_date():
    """The motivating bug: some session files carry extra sheets titled e.g.
    "b-25.06.2026" instead of a plain date, and the exact same "b-" block turned up
    byte-for-byte in two different session files (2025/2026 June and September) —
    leftover/stale content carried over between files, not a genuine second exam
    group. Since it can't reliably be told apart from a real sheet, and it never
    contributes to `published_at` anyway (`_parse_sheet_date` already rejects it), the
    whole sheet is skipped rather than indexed as if it were this session's own."""
    import io
    from datetime import time as dtime

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "10.09.2026"
    ws["B2"] = "лаб. 1"
    ws["A3"] = dtime(8, 0)
    ws["B3"] = "Структурно програмирање"

    stray = wb.create_sheet("b-25.06.2026")
    stray["B2"] = "лаб. 13"
    stray["A3"] = dtime(15, 0)
    stray["B3"] = "Маркетинг"

    buf = io.BytesIO()
    wb.save(buf)

    text, published_at = extract_xlsx_schedule_grid(buf.getvalue())

    assert "Структурно програмирање" in text
    assert "Маркетинг" not in text
    assert published_at == datetime(2026, 9, 10)


def test_extract_xlsx_schedule_grid_empty_workbook_returns_empty_string_and_no_date():
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)

    assert extract_xlsx_schedule_grid(buf.getvalue()) == ("", None)


def test_extract_xlsx_schedule_grid_published_at_is_robust_to_one_mistyped_sheet():
    """The motivating real bug: a real session file has a sheet titled "16.06.2025"
    (should be 2026) sitting between two correctly-dated 2026 sheets - a one-off typo
    in FINKI's own spreadsheet. Taking the plain minimum date would drag published_at
    a full year off, which chat.py's prefer_current_year treats as "wrong year
    entirely" and drops the whole document even though it's the most relevant result
    - confirmed live, this silently hid the correct June exam session from a query
    about it. The median must land in the correct year despite the outlier."""
    import io
    from datetime import time as dtime

    import openpyxl

    wb = openpyxl.Workbook()
    del wb["Sheet"]
    day_titles = ["08.06.2026", "09.06.2026", "10.06.2026", "16.06.2025", "17.06.2026", "18.06.2026"]
    for title in day_titles:
        ws = wb.create_sheet(title=title)
        ws["B2"] = "лаб. 3"
        ws["A3"] = dtime(8, 0)
        ws["B3"] = "Тест предмет"
    buf = io.BytesIO()
    wb.save(buf)

    _, published_at = extract_xlsx_schedule_grid(buf.getvalue())

    assert published_at is not None
    assert published_at.year == 2026


def test_extract_xlsx_schedule_grid_parses_single_digit_day_month_sheet_title():
    """Sheet titles aren't consistently zero-padded across all of FINKI's session
    files (confirmed live: some real sheets are titled "5.6.2023", not "05.06.2023")
    — a date parser expecting exactly 2 digits would silently miss these."""
    import io
    from datetime import time as dtime

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "5.6.2023"
    ws["B2"] = "лаб. 3"
    ws["A3"] = dtime(8, 0)
    ws["B3"] = "Тест предмет"
    buf = io.BytesIO()
    wb.save(buf)

    text, published_at = extract_xlsx_schedule_grid(buf.getvalue())

    assert published_at == datetime(2023, 6, 5)
    assert "5.6.2023" in text
