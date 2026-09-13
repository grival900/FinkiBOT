import re
from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from google.genai import types
from sqlalchemy.orm import Session

from backend.api.schemas import ChatRequest
from backend.core.config import get_settings
from backend.core.llm import get_client
from backend.core.retrieval import SearchResult, search
from backend.core.site_settings import get_float_setting
from backend.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()

# How many candidates to pull from vector search before recency-filtering down to
# CHAT_RESULT_K — needs to be wide enough that a query matching a yearly-recurring
# announcement (e.g. "студентска служба") has a real chance of surfacing a current-year
# hit alongside the older ones semantic search alone would rank just as high. Widened
# once type=exam documents were introduced: one exam-session spreadsheet now produces
# many small near-identical per-row documents (same course text repeated per room/time),
# which can otherwise crowd out an equally relevant document from a different year or
# source at these tighter limits.
CANDIDATE_POOL_K = 40
CHAT_RESULT_K = 10

# Citation list is deliberately tighter than the context the model gets. A retrieved
# chunk can be worth handing the model as background yet not worth naming as a source:
# the long tail of the pool is usually an incidental keyword overlap, and listing it
# under "Извори" just makes a correct answer look like it came from the wrong page.
MAX_CITED_SOURCES = 4
# A document whose best chunk scores more than this below the top hit is dropped from
# the citation list (not the context) — see `select_citation_sources`.
CITATION_SCORE_GAP = 0.15

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
    "Other context entries have type=exam: these ARE one real row extracted from an exam-"
    "session/consultation spreadsheet (course, date, time, room, professor — whatever "
    "columns that particular file has, labelled exactly as the file labels them), not just "
    "a link. When a type=exam entry answers the student's question, state the concrete "
    "facts from it directly (e.g. the actual date/time/room) instead of only pointing at "
    "the file — that's exactly what these entries are for. A grid-shaped schedule file "
    "(rooms as columns, half-hour time slots as rows) produces several type=exam entries "
    "for the exact same course+room that only differ by a slightly later start time — "
    "these are consecutive slots of one continuous exam block, not separate exam sittings. "
    "When you see several type=exam entries for the same course and room, report only the "
    "single earliest start time among them (when the exam block begins), not every slot — "
    "never list out multiple times for what is really one continuous block in one room. "
    "Only mention more than one time for the same course if the rooms are genuinely "
    "different, since that means separate groups of students sit the exam separately. Only fall back to 'проверете во "
    "документот' if no type=exam entry in the context actually covers what they asked.\n\n"
    "A single time slot in a grid-shaped schedule file can have different rooms running "
    "different courses side by side — including one whose column literally reads an English "
    "name (e.g. 'Databases') for the very course the student asked about in Macedonian ('Бази "
    "на податоци'); that's the same course, not a different one, so include it. But when a "
    "room's course text clearly names a genuinely different subject than what the student "
    "asked about, don't include that room just because it shares the same time slot — only "
    "report rooms whose course field actually matches (allowing for an equivalent English/"
    "Macedonian name) the specific course the student asked about.\n\n"
        "Course names at FINKI overlap heavily as substrings — 'Бази на податоци', "
    "'Неструктурирани бази на податоци', 'Дистрибуирани бази на податоци', 'Напредни бази на "
    "податоци' are four different courses that all contain the words 'бази на податоци'. "
    "When the student names a specific course, only use a type=exam/type=course/type=material "
    "row whose course field is an EXACT match to that course name (or an exact equivalent "
    "translation) — never one that merely contains the asked-about words as part of a longer, "
    "more specific course title, and never one that's missing a qualifier word the student's "
    "course name has. If nothing in the context is an exact match, say so rather than "
    "substituting the closest-sounding longer/shorter course name.\n\n"
    "This is a hard filtering rule, not a suggestion: when answering about one named course, "
    "silently discard every context entry whose own course field is a DIFFERENT course, even "
    "one that shares words, sits in the same file, or occupies the same exam time slot — treat "
    "a discarded entry exactly as if it were never in the context at all. Never mention it, "
    "never list its room 'for completeness', never add a parenthetical note about it. For "
    "example, if asked about 'Бази на податоци' and the context also contains rows for "
    "'Неструктурирани бази на податоци' and 'Веб базирани системи' at the very same date/time, "
    "the answer must describe ONLY the 'Бази на податоци' rows — say nothing whatsoever about "
    "the other two courses, not even a footnote. The answer should read exactly like an answer "
    "from a normal single-purpose lookup tool that was only ever given data for the one course "
    "asked about.\n\n"
    "The context can contain type=exam/type=schedule entries from two different sources for "
    "the same kind of exam-session data: 'official' (finki.ukim.mk's own schedule widget, "
    "which only ever shows the single most recently posted session — it has no history of "
    "past sessions) and 'finki_hub' (finki-hub.com's own archive, which keeps multiple past "
    "sessions). If the student asks about a session/year the official source has no entry "
    "for, don't just say the data isn't available — check whether a finki_hub entry in the "
    "context covers it instead, and if so answer from that one directly (still citing it "
    "normally), same as you would for any other source. Only say the information truly isn't "
    "available if neither source's context entries cover what was asked.\n\n"
    "type=consultation entries are a professor's actual upcoming consultation slot(s) — "
    "date, time, location, and any instructions — scraped directly from the live booking "
    "system, not just a link to it. When asked when a professor has consultations, state "
    "the real date/time/location from a type=consultation entry directly. A `staff` entry's "
    "own 'Консултации' line is only ever a link to that same booking system, never the slot "
    "data itself — prefer the type=consultation entry when both are present in the context.\n\n"
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
    "Exception: when the question is specifically and only about a professor's consultations "
    "(e.g. \"кога има консултации проф. X\") rather than about the professor generally, skip "
    "the header+full-profile treatment entirely — just answer in one or two short sentences "
    "like a normal chatbot would, e.g. \"Професорот <name> има консултации на <date> од <start> "
    "до <end> часот, <location>.\" Don't add their title, email, cabinet, bio, or publications "
    "unless the student actually asked about those too — a consultations question wants a "
    "quick fact, not a profile.\n\n"
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


# Appended to each citation's title so entries for the same subject from different
# sites are visibly distinct — before this, the finki-hub and official pages for one
# course both rendered as the bare title "Неструктурирани бази на податоци", looking
# like one link repeated.
_TYPE_LABEL = {
    "course": "предмет",
    "professor": "професор",
    "staff": "наставник",
    "announcement": "објава",
    "material": "материјали",
    "schedule": "распоред",
    "exam": "испитен термин",
    "consultation": "консултации",
    "page": "страница",
}
_FRONTEND_HOST = urlparse(settings.frontend_origin).netloc.removeprefix("www.")


def _display_host(url: str) -> str:
    """Human-facing site name for a citation link — normalised so every finki-hub
    subdomain (predmeti./snimki./assets.) reads as one site, and our own internal
    document page (only used for finki_hub courses) is attributed to finki-hub too."""
    host = urlparse(url).netloc.removeprefix("www.")
    if host == _FRONTEND_HOST or host.endswith("finki-hub.com"):
        return "finki-hub.com"
    if host.endswith("finki.ukim.mk"):
        return "finki.ukim.mk"
    return host or "врска"


def source_label(result: SearchResult) -> str:
    """Citation display text: title + what it is + which site the link opens."""
    kind = _TYPE_LABEL.get(result.type, result.type)
    return f"{result.title} ({kind}, {_display_host(citation_url(result))})"


def build_context(results: list[SearchResult]) -> str:
    if not results:
        return "(no matching context found)"
    blocks = []
    for r in results:
        date = r.published_at.date().isoformat() if r.published_at else "n/a"
        blocks.append(f"[{r.title}] (type: {r.type}, url: {citation_url(r)}, date: {date})\n{r.chunk_text}")
    return "\n\n---\n\n".join(blocks)


def select_citation_sources(
    results: list[SearchResult],
    max_sources: int = MAX_CITED_SOURCES,
    score_gap: float = CITATION_SCORE_GAP,
) -> list[SearchResult]:
    """Which retrieved documents to actually list under "Извори". `results` is already
    sorted best-first. Keeps one entry per document (and per resolved link — the
    finki-hub and official copies of a course can point at the same syllabus URL),
    stops at the first document whose score falls more than `score_gap` below the top
    hit (the point where matches stop being what the answer is built on and start
    being passing keyword mentions), and caps the count. Returns `[]` for an empty
    input — the caller then omits the block entirely rather than printing an empty
    heading."""
    if not results:
        return []
    top_score = results[0].score
    seen_docs: set[str] = set()
    seen_urls: set[str] = set()
    picked: list[SearchResult] = []
    for r in results:
        if top_score - r.score > score_gap:
            break
        url = citation_url(r)
        if r.document_id in seen_docs or url in seen_urls:
            continue
        seen_docs.add(r.document_id)
        seen_urls.add(url)
        picked.append(r)
        if len(picked) >= max_sources:
            break
    return picked


def build_sources_block(results: list[SearchResult]) -> str:
    """Built here instead of left to the LLM: guarantees every link is well-formed and
    points at the right place (see `citation_url`), that each entry says which site it
    came from (see `source_label`), and that identical questions get an identically
    formatted list. `results` is expected to be pre-filtered by
    `select_citation_sources`."""
    if not results:
        return ""
    lines = [f"- [{source_label(r)}]({citation_url(r)})" for r in results]
    return "\n\n---\n\n**Извори:**\n" + "\n".join(lines)


# The model is told (system prompt) not to write its own source list, but sometimes
# does anyway — always at the very end, as a near-bare heading like "Извори:" or
# "**Sources**", optionally after a --- rule. We cut from there on and append our own
# canonical block instead, so the answer never shows two overlapping lists.
_SOURCES_HEADING_RE = re.compile(
    r"\n\s*(?:[-*_]{3,}\s*)?"  # optional horizontal rule (and any blank lines around it)
    r"(?:\*{1,2}|__|#{1,6}[ \t]*)?"  # optional bold / ATX-heading markup
    r"(?:извори|sources|референци|references)"
    r"[ \t]*:?[ \t]*(?:\*{1,2}|__)?[ \t]*\n",  # optional colon / closing markup, then EOL
    re.IGNORECASE,
)
# How many trailing characters to hold back while streaming, so a source heading that
# has only partly arrived isn't emitted before we can recognise and cut it.
_HEADING_LOOKBACK = 64


def _sources_cut_index(text: str) -> int | None:
    m = _SOURCES_HEADING_RE.search(text)
    return m.start() if m else None


def _gemini_role(role: str) -> str:
    """Gemini uses "model" where Anthropic/OpenAI-style APIs use "assistant"."""
    return "model" if role == "assistant" else "user"


@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    min_score = get_float_setting(db, "chat_min_score", settings.chat_min_score)
    candidates = search(db, payload.message, k=CANDIDATE_POOL_K, min_score=min_score)
    current_year = datetime.now(timezone.utc).year
    results = prefer_current_year(candidates, k=CHAT_RESULT_K, current_year=current_year)
    context = build_context(results)
    cited = select_citation_sources(results)

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

    def _thinking_config() -> types.ThinkingConfig:
        """Gemini 2.5 controls thinking via a token `thinking_budget` (0 disables it);
        Gemini 3 models use the newer `thinking_level` instead — `thinking_budget` is
        documented as backward-compatible there too, but has been observed to trigger a
        hard 400 INVALID_ARGUMENT against gemini-3.6-flash in practice, so this switches
        on the model name rather than relying on that compatibility claim. "low" is the
        closest match to the old thinking_budget=0 intent (minimize the latency/cost this
        was originally added to cut — see below), since "minimal" isn't available on
        every Gemini 3 variant."""
        if settings.llm_model.startswith("gemini-3"):
            return types.ThinkingConfig(thinking_level="low")
        return types.ThinkingConfig(thinking_budget=0)

    def event_stream() -> Iterator[str]:
        stream = client.models.generate_content_stream(
            model=settings.llm_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=4096,
                temperature=0.2,
                # A full "high" thinking pass measured ~3s added to time-to-first-token
                # for zero benefit on this task (grounded RAG lookup + rephrasing, not
                # multi-step reasoning) — cut first-token latency from ~4.4s to ~1s.
                thinking_config=_thinking_config(),
            ),
        )
        acc = ""
        sent = 0
        for chunk in stream:
            if not chunk.text:
                continue
            acc += chunk.text
            cut = _sources_cut_index(acc)
            if cut is not None:
                if cut > sent:
                    yield acc[sent:cut]
                sent = len(acc)
                for _ in stream:  # drain the rest, discard the model's own list
                    pass
                break
            safe = len(acc) - _HEADING_LOOKBACK
            if safe > sent:
                yield acc[sent:safe]
                sent = safe
        if sent < len(acc):
            cut = _sources_cut_index(acc)
            yield acc[sent : cut if cut is not None else len(acc)].rstrip()
        yield build_sources_block(cited)

    return StreamingResponse(event_stream(), media_type="text/plain")
