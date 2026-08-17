"""Word-based chunking. Word count is a rough proxy for token count, which is fine here
since chunks only need to be small enough for retrieval + prompt context, not exact."""


def chunk_text(text: str, max_words: int = 220, overlap_words: int = 40) -> list[str]:
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
