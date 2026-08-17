from backend.ingestion.chunking import chunk_text


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
