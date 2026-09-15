from backend.ingestion.chunking import chunk_schedule_by_date, chunk_text, get_chunks


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []


def test_short_text_is_a_single_chunk():
    text = "збор " * 10
    assert len(chunk_text(text, max_words=220, overlap_words=40)) == 1


def test_long_text_is_split_with_full_coverage():
    words = [f"w{i}" for i in range(500)]
    text = " ".join(words)
    chunks = chunk_text(text, max_words=220, overlap_words=40)

    assert len(chunks) == 3
    covered = set(" ".join(chunks).split())
    assert covered == set(words)


def test_chunks_overlap():
    words = [f"w{i}" for i in range(500)]
    text = " ".join(words)
    chunks = chunk_text(text, max_words=220, overlap_words=40)

    first_words = chunks[0].split()
    second_words = chunks[1].split()
    assert first_words[-40:] == second_words[:40]


def test_chunk_schedule_by_date_groups_same_day_records_into_one_chunk():
    """The motivating bug: two distinct courses scheduled the same day landed in
    different word-count chunks, so a query matching one of them never surfaced the
    other. Grouping by the bracket's leading date token keeps a whole day together
    regardless of how many records or words it has."""
    text = (
        "2025/2026 Септември\nЛинк за преземање: https://example.com/f.xlsx\n"
        "[10.09.2026 08:00-11:00 117: Дискретна математика/ Математика 2] "
        "[10.09.2026 11:30-13:30 лаб. 3: Дискретна математика (КИ)] "
        "[11.09.2026 09:00-10:00 200ц: Друг предмет]"
    )

    chunks = chunk_schedule_by_date(text)

    same_day_chunk = next(c for c in chunks if "10.09.2026" in c)
    assert "Математика 2" in same_day_chunk
    assert "(КИ)" in same_day_chunk
    assert "Друг предмет" not in same_day_chunk
    # The non-bracketed session-name/download-link preamble survives as its own chunk.
    assert any("Линк за преземање" in c for c in chunks)
    # ...and its first line (just the session name, not the download link) is also
    # carried into every day's own chunk, so a query naming the session/period has
    # something to actually match against.
    assert all(c.startswith("2025/2026 Септември\n") for c in chunks if "10.09.2026" in c or "11.09.2026" in c)


def test_chunk_schedule_by_date_splits_a_busy_day_once_it_exceeds_the_budget():
    """The motivating bug: grouping by day alone had no upper size bound at all, so a
    genuinely busy exam day (many courses spread across many rooms) could reintroduce
    the exact "too many unrelated courses diluting one embedding" problem
    SCHEDULE_MAX_WORDS was introduced to prevent - just rescoped from "whole document"
    to "one busy day". A day whose combined records exceed the word budget must split
    into more than one chunk, each still date-grouped, none of them mid-record."""
    from backend.ingestion.chunking import SCHEDULE_MAX_WORDS

    # Each record is ~6 words; comfortably more than SCHEDULE_MAX_WORDS worth of
    # records for one single day.
    record_count = (SCHEDULE_MAX_WORDS // 6) + 5
    records = " ".join(f"[10.09.2026 08:00-08:30 лаб.{i}: Курс{i} Предмет]" for i in range(record_count))

    chunks = chunk_schedule_by_date(records)

    same_day_chunks = [c for c in chunks if "10.09.2026" in c]
    assert len(same_day_chunks) > 1
    assert all(len(c.split()) <= SCHEDULE_MAX_WORDS for c in same_day_chunks)
    # No record was split or lost across the split.
    for i in range(record_count):
        assert any(f"Курс{i} Предмет" in c for c in same_day_chunks)


def test_chunk_schedule_by_date_groups_parallel_group_sheets_separately():
    """A "b-" prefixed sheet title (a parallel/alternate exam group) is a different
    leading token from its plain counterpart, so it forms its own chunk rather than
    silently merging into an unrelated bucket."""
    text = "[19.06.2026 08:00-10:00 117: Курс А] [b-19.06.2026 08:00-10:00 118: Курс Б]"

    chunks = chunk_schedule_by_date(text)

    assert len(chunks) == 2
    assert any("Курс А" in c and "Курс Б" not in c for c in chunks)
    assert any("Курс Б" in c and "Курс А" not in c for c in chunks)


def test_chunk_schedule_by_date_falls_back_to_word_chunking_with_no_brackets():
    """PDF-derived older sessions have no bracketed per-course records at all (see
    extract_pdf_text) - nothing to group by, so this falls back to plain word-based
    chunking instead of treating the whole document as one giant chunk."""
    words = [f"w{i}" for i in range(500)]
    text = " ".join(words)

    chunks = chunk_schedule_by_date(text)

    assert len(chunks) > 1
    assert all(len(c.split()) <= 50 for c in chunks)


def test_get_chunks_dispatches_schedule_to_date_grouping():
    text = "[10.09.2026 08:00-11:00 117: Курс] [10.09.2026 11:30-13:30 лаб. 3: Друг курс]"
    assert get_chunks("schedule", text) == chunk_schedule_by_date(text)


def test_get_chunks_uses_plain_word_chunking_for_other_types():
    text = "збор " * 10
    assert get_chunks("announcement", text) == chunk_text(text)
