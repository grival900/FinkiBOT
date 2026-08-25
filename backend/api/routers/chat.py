from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from google.genai import types
from sqlalchemy.orm import Session

from backend.api.schemas import ChatRequest
from backend.core.config import get_settings
from backend.core.llm import get_client
from backend.core.retrieval import SearchResult, search
from backend.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()

# How many candidates to pull from vector search before recency-filtering down to
# CHAT_RESULT_K — needs to be wide enough that a query matching a yearly-recurring
# announcement (e.g. "студентска служба") has a real chance of surfacing a current-year
# hit alongside the older ones semantic search alone would rank just as high.
CANDIDATE_POOL_K = 24
CHAT_RESULT_K = 6

SYSTEM_PROMPT = (
    "You are FinkiBOT, an assistant for students at FINKI (Faculty of Computer Science "
    "and Engineering, Skopje). You receive context snippets retrieved from finki.ukim.mk "
    "and finki-hub.com alongside each question.\n\n"
    "When the context is relevant to the student's question, base your answer on it. When "
    "the context is not relevant — for example, general knowledge questions about "
    "programming concepts, mathematics, science, or other non-FINKI-specific topics — "
    "answer from your own general knowledge without claiming the information is "
    "unavailable.\n\n"
    "Never fabricate FINKI-specific information (course details, professor names, exam "
    "schedules, deadlines, enrollment rules) from general knowledge — only state FINKI "
    "facts that appear in the provided context. If a FINKI-specific question has no "
    "matching context, say so plainly.\n\n"
    "Context entries include a date. For announcements specifically, the retrieval "
    "layer already prefers this year's matches over older ones when both exist for the "
    "same query — so if every announcement in your context is from a past year, that "
    "means nothing more recent was found, not an oversight. In that case, say plainly "
    "that you don't have anything from this year and name the year(s) the information "
    "you do have is actually from, rather than presenting old announcements as current.\n\n"
    "Some context entries have type=schedule: these are reference links (e.g. to an exam "
    "session schedule spreadsheet), not documents with the actual dates in their text — "
    "we don't have the file contents, only the link. When a schedule entry's title matches "
    "what the student is asking about (e.g. they ask about the June exam session and a "
    "schedule entry is titled 'јунска испитна сесија'), say you don't have the exact dates "
    "but mention that specific entry — don't substitute a less relevant schedule entry just "
    "because it's also present in the context.\n\n"
    "Don't write a source list or any URLs/links yourself — the app appends an accurate "
    "source list automatically after your answer, from the same context you were given. "
    "Referring to a source by name in prose (e.g. \"according to the official course "
    "page...\") is fine, but never write out a URL or a markdown link.\n\n"
    "Format every answer as markdown: use **bold** for labels and key terms, bullet lists "
    "for multiple facts, and blank lines between paragraphs — never a single wall of text.\n\n"
    "When the question is clearly about one specific course, structure the answer as:\n"
    "### <course name>\n"
    "then a bullet list of the key facts actually present in the context (code, "
    "level/semester, ECTS credits, prerequisites, professors/assistants, accreditation "
    "programs — skip whatever you don't have, don't pad with 'N/A'), followed by a short "
    "paragraph for anything else worth saying (e.g. syllabus content, learning "
    "objectives).\n\n"
    "When the question is clearly about one specific professor, structure the answer as:\n"
    "### <professor name>\n"
    "then a bullet list of the key facts actually present (title/position, email, cabinet, "
    "consultations), followed by a short paragraph summarizing their bio/publications if "
    "present in the context.\n\n"
    "For anything else (announcements, general questions, multi-course comparisons), just "
    "use clear markdown prose/lists — the header+bullet template above is specifically for "
    "single-course and single-professor questions.\n\n"
    "Keep answers concise and scannable: lead with the direct answer, don't restate the "
    "question, and don't pad with filler or repeat the same point across sources. It's fine "
    "to be longer when the question genuinely calls for it (e.g. summarizing a professor's "
    "full bio or a course syllabus) — just don't stretch length unnecessarily. "
    "Respond in the same language the student asked in (usually Macedonian)."
)


def prefer_current_year(results: list[SearchResult], k: int, current_year: int) -> list[SearchResult]:
    """Recency bias for chat context — a query like "студентска служба" semantically
    matches near-identical announcement text posted every year, and cosine similarity
    alone has no way to prefer this year's copy over 2014's. Undated results (courses,
    professors, etc. — only `announcement` documents carry `published_at`, see
    `scrapers/official_site/announcements.py`) are always kept since recency doesn't
    apply to them. Among dated results, older years are dropped whenever at least one
    current-year match exists for the same query; otherwise every dated result is kept
    as a fallback, oldest included, since that's genuinely the best we have.
    """
    dated = [r for r in results if r.published_at is not None]
    undated = [r for r in results if r.published_at is None]
    current_year_matches = [r for r in dated if r.published_at.year == current_year]  # type: ignore[union-attr]
    kept_dated = current_year_matches if current_year_matches else dated
    merged = sorted(kept_dated + undated, key=lambda r: r.score, reverse=True)
    return merged[:k]


def citation_url(result: SearchResult) -> str:
    """Prefer a real external URL when we have one. finki_hub course pages have no
    stable per-course route to cite directly — clicking a row on predmeti.finki-hub.com
    never changes the URL (it's a client-side modal, not a real route) — but the
    document's metadata often already carries the actual official syllabus URL
    (captured from the accreditation data), which is worth citing over our own page
    when it exists; only fall back to our internal page when it doesn't."""
    if result.source == "finki_hub" and result.type == "course":
        official_url = result.metadata.get("official_subject_url")
        if official_url:
            return official_url
        return f"{settings.frontend_origin}/documents/{result.document_id}"
    return result.url


def build_context(results: list[SearchResult]) -> str:
    if not results:
        return "(no matching context found)"
    blocks = []
    for r in results:
        date = r.published_at.date().isoformat() if r.published_at else "n/a"
        blocks.append(f"[{r.title}] (type: {r.type}, url: {citation_url(r)}, date: {date})\n{r.chunk_text}")
    return "\n\n---\n\n".join(blocks)


def build_sources_block(results: list[SearchResult]) -> str:
    """Built here instead of left to the LLM: guarantees every link is well-formed and
    points at the right place (see `citation_url`), and keeps identical questions from
    getting a differently-formatted source list each time."""
    seen: set[str] = set()
    lines: list[str] = []
    for r in results:
        if r.document_id in seen:
            continue
        seen.add(r.document_id)
        lines.append(f"- [{r.title}]({citation_url(r)})")
    if not lines:
        return ""
    return "\n\n---\n\n**Извори:**\n" + "\n".join(lines)


def _gemini_role(role: str) -> str:
    """Gemini uses "model" where Anthropic/OpenAI-style APIs use "assistant"."""
    return "model" if role == "assistant" else "user"


@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    candidates = search(db, payload.message, k=CANDIDATE_POOL_K)
    current_year = datetime.now(timezone.utc).year
    results = prefer_current_year(candidates, k=CHAT_RESULT_K, current_year=current_year)
    context = build_context(results)

    contents = [
        types.Content(role=_gemini_role(m.role), parts=[types.Part.from_text(text=m.content)])
        for m in payload.history
    ]
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Context:\n{context}\n\nQuestion: {payload.message}")],
        )
    )

    client = get_client()

    def event_stream() -> Iterator[str]:
        stream = client.models.generate_content_stream(
            model=settings.llm_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=4096,
                temperature=0.2,
                # gemini-2.5-flash runs an extended "thinking" pass by default — measured
                # ~3s added to time-to-first-token for zero benefit on this task (grounded
                # RAG lookup + rephrasing, not multi-step reasoning). Disabling it cut
                # first-token latency from ~4.4s to ~1s in testing.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
        yield build_sources_block(results)

    return StreamingResponse(event_stream(), media_type="text/plain")
