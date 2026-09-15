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
from backend.core.retrieval import RECENCY_MATCH_BOOST, SearchResult, search
from backend.core.site_settings import get_float_setting
from backend.db import get_db
from backend.mcp_servers.official_live_mcp.server import search_official_site_live

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()

# How many candidates to pull from vector search before recency-filtering down to
# CHAT_RESULT_K — needs to be wide enough that a query matching a yearly-recurring
# announcement (e.g. "студентска служба") has a real chance of surfacing a current-year
# hit alongside the older ones semantic search alone would rank just as high.
CANDIDATE_POOL_K = 24
CHAT_RESULT_K = 6

# Only ever fires when the local index has nothing at all for the query (every
# candidate fell below `chat_min_score`, or there were none) — a genuinely new
# announcement/page finki.ukim.mk already has but the next reindex hasn't reached yet.
# Deliberately not fired alongside a normal (non-empty) local result set: a real, if
# imperfect, indexed match is still a better-grounded answer than an unindexed page we
# only know the title and URL of.
LIVE_FALLBACK_LIMIT = 3

# Citation list is deliberately tighter than the context the model gets. A retrieved
# chunk can be worth handing the model as background yet not worth naming as a source:
# the long tail of the pool is usually an incidental keyword overlap, and listing it
# under "Извори" just makes a correct answer look like it came from the wrong page.
# Capped at 1: in practice the single top hit is the actual source the answer is built
# on, and anything past that is rarely more than a passing keyword match dressed up as
# a citation. `select_citation_sources`'s score-gap cutoff already does the real work
# of dropping unrelated tail matches — this cap is a hard backstop on top of it.
MAX_CITED_SOURCES = 1
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
    "Some context entries are marked as a live search result instead of indexed "
    "content: they carry only a title/type and no page text at all (our local index "
    "had nothing for this query, so this is a same-topic page fetched live from "
    "finki.ukim.mk as a fallback). Never invent what such a page says — tell the "
    "student you found a page that's likely relevant but don't have its contents "
    "indexed yet, and point them to it (the source list below your answer already "
    "links it).\n\n"
    "Context entries include a date. For announcements specifically, the retrieval "
    "layer already prefers this year's matches over older ones when both exist for the "
    "same query — so if every announcement in your context is from a past year, that "
    "means nothing more recent was found, not an oversight. In that case, say plainly "
    "that you don't have anything from this year and name the year(s) the information "
    "you do have is actually from, rather than presenting old announcements as current.\n\n"
    "Some context entries have type=schedule: for finki-hub.com sources these now include "
    "the actual per-course exam date/time/room extracted from the schedule spreadsheet "
    "(XLSX sessions have this in full; older PDF sessions may only have time/room, not an "
    "exact date) — read the entry's text itself for the specific date/time/room rather than "
    "assuming it's link-only. Official (finki.ukim.mk) schedule entries are still link-only "
    "reference links with no parsed content — for those, say you don't have the exact dates "
    "but mention the specific entry whose title matches what the student is asking about, "
    "rather than substituting a less relevant one just because it's also present in the "
    "context.\n\n"
    "Don't write a source list or any URLs/links yourself — the app appends an accurate "
    "source list automatically after your answer, from the same context you were given. "
    "Referring to a source by name in prose (e.g. \"according to the official course "
    "page...\") is fine, but never write out a URL or a markdown link.\n\n"
    "Format every answer as markdown: use **bold** for labels and key terms, bullet lists "
    "for multiple facts, and blank lines between paragraphs — never a single wall of text.\n\n"
    "Match the scope of the question, not just its topic. A question about one specific "
    "fact (an exam date, a consultation slot, an email, a room) gets *only* that fact — "
    "don't pad it with unrelated detail the context happens to also contain (e.g. a full "
    "course syllabus when only the exam date was asked, or a professor's bio when only "
    "their consultations were asked). Use the fuller course/professor templates below "
    "*only* when the question is genuinely general — \"кажи ми за...\", \"што е...\", or "
    "just the course/professor's name with no further specifics. For anything narrower, "
    "answer the specific thing asked, with at most one short sentence of context if it "
    "helps confirm which course/professor is meant.\n\n"
    "When the question is genuinely general and clearly about one specific course, "
    "structure the answer as:\n"
    "### <course name>\n"
    "then a bullet list of the key facts actually present in the context (code, "
    "level/semester, ECTS credits, prerequisites, professors/assistants, accreditation "
    "programs — skip whatever you don't have, don't pad with 'N/A'), followed by a short "
    "paragraph for anything else worth saying (e.g. syllabus content, learning "
    "objectives).\n\n"
    "When the question is genuinely general and clearly about one specific professor, "
    "structure the answer as:\n"
    "### <professor name>\n"
    "then a bullet list of the key facts actually present (title/position, email, cabinet, "
    "consultations), followed by a short paragraph summarizing their bio/publications if "
    "present in the context.\n\n"
    "When the question is specifically about a professor's consultations, structure the "
    "answer as:\n"
    "### <professor name> — консултации\n"
    "then a bullet list with title/position and the courses they teach (if present in the "
    "context) plus the scheduled slot(s) (date/time/location), or say plainly that no "
    "slots are currently scheduled if that's what the context says. Leave out bio and "
    "publications entirely — that belongs to the general professor template above, not "
    "here. If a type=consultation context entry (Датум/Време/Локација) and a type=staff "
    "entry (Кабинет) disagree on where the professor can be found, trust the consultation "
    "entry's own Локација — it's the live, per-slot source, while the staff profile's "
    "cabinet field can be stale.\n\n"
    "When the question is specifically about an exam date/session for a course, answer "
    "with just the date/time/room(s). Report only the year the student asked about; if "
    "they didn't name one, use the message's stated date to judge which session is "
    "current or next upcoming and report that one. If the context genuinely contains "
    "several different sessions for the same course (e.g. a January and a June date), "
    "name which session you're reporting (e.g. \"Јунска сесија: ...\") and only list the "
    "others if the student asked for a specific session by name or for all of them — "
    "don't recite every session found back to back by default.\n\n"
    "For anything else (announcements, general questions, multi-course comparisons), just "
    "use clear markdown prose/lists — the templates above are specifically for the "
    "narrower question types they each name.\n\n"
    "Keep answers concise and scannable: lead with the direct answer, don't restate the "
    "question, and don't pad with filler or repeat the same point across sources. It's fine "
    "to be longer when the question genuinely calls for it (e.g. summarizing a professor's "
    "full bio or a course syllabus) — just don't stretch length unnecessarily. "
    "Respond in the same language the student asked in (usually Macedonian)."
)


_ACADEMIC_YEAR_RE = re.compile(r"^(\d{4})/(\d{4})")

# A schedule chunk's own date, read straight out of its leading "[dd.mm.yyyy ...]"
# record (see `chunk_schedule_by_date`, which groups every record for one calendar day
# into the same chunk) — unlike `published_at`, which is one representative date for
# the *entire* session file (see `_representative_date`), this is the actual day the
# chunk's own content is about.
_SCHEDULE_CHUNK_DATE_RE = re.compile(r"\[(\d{1,2})\.(\d{1,2})\.(\d{4})")
_SCHEDULE_CHUNK_RECENCY_HORIZON_DAYS = 180
# Deliberately smaller than RECENCY_MATCH_BOOST: this only needs to break ties *among*
# same-year schedule chunks (see `_apply_schedule_chunk_recency_boost`), not compete
# with the year-level boost that already separates current-year from stale-year
# matches.
SCHEDULE_CHUNK_RECENCY_BOOST = 0.08


def _schedule_chunk_date(chunk_text: str) -> datetime | None:
    m = _SCHEDULE_CHUNK_DATE_RE.search(chunk_text)
    if m is None:
        return None
    day, month, year = (int(g) for g in m.groups())
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _apply_schedule_chunk_recency_boost(results: list[SearchResult], now: datetime) -> dict[int, float]:
    """The motivating bug: a course's exam date exists in more than one same-year
    session file at once (a colloquium, then January, then June, then September all
    exist "this year") — `prefer_current_year`'s current-year boost treats every one of
    them identically, so with only `CHAT_RESULT_K` slots to go around, whichever
    session happened to score marginally higher on raw cosine similarity won the last
    slot even when it was months stale and a genuinely later session's chunk for the
    same course existed too (confirmed live: "кога се полага структурно
    програмирање" surfaced a winter colloquium, January, and June session, but never
    the current September one). Boosts each schedule chunk by how close its own date
    is to `now` (in either direction — a session currently underway is exactly as
    relevant as one about to start), so competing same-year schedule chunks for the
    same course are actually ranked by which session is live/upcoming instead of by
    embedding noise. Returns a `{id(result): boost}` map rather than mutating scores,
    same reasoning as `prefer_current_year`'s own boost."""
    now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    boosts: dict[int, float] = {}
    for r in results:
        if r.type != "schedule":
            continue
        chunk_date = _schedule_chunk_date(r.chunk_text)
        if chunk_date is None:
            continue
        distance_days = abs((now_naive - chunk_date).days)
        remaining = 1 - distance_days / _SCHEDULE_CHUNK_RECENCY_HORIZON_DAYS
        if remaining <= 0:
            continue
        boosts[id(r)] = SCHEDULE_CHUNK_RECENCY_BOOST * remaining
    return boosts


def _effective_year(r: SearchResult) -> int | None:
    """The year to filter/boost `r` by. Directly `published_at.year` when we have a
    real date. Pre-2022 finki_hub exam-session ("schedule") documents only got a PDF
    extraction, which never parses a per-sheet date at all (see
    `extract_session_file_content`) — `published_at` is `None` for them, which used to
    make `prefer_current_year` treat them as "undated" and always keep, so an old
    2021/2022 exam session rode alongside a current one in the same answer instead of
    being filtered out (confirmed live: "кога е испит по маркетинг" returned both a
    2026 and a 2021/2022 date). These documents do carry an `academic_year` string
    ("2021/2022", see `parse_session_entry`) in their metadata even without a parsed
    date, and every FINKI exam period (January/June/September) falls in the second
    half of that academic year, so its second component is a good enough proxy year to
    filter on."""
    if r.published_at is not None:
        return r.published_at.year
    if r.type == "schedule":
        m = _ACADEMIC_YEAR_RE.match(r.metadata.get("academic_year", ""))
        if m:
            return int(m.group(2))
    return None


def prefer_current_year(
    results: list[SearchResult], k: int, current_year: int, now: datetime | None = None
) -> list[SearchResult]:
    """Recency bias for chat context — a query like "студентска служба" semantically
    matches near-identical announcement text posted every year, and cosine similarity
    alone has no way to prefer this year's copy over 2014's. Results with no
    `_effective_year` at all (professor bios, course syllabi, etc.) are always kept
    since recency doesn't apply to them. Among the rest, older years are dropped
    whenever at least one current-year match exists for the same query; otherwise
    every dated result is kept as a fallback, oldest included, since that's genuinely
    the best we have.

    Narrowing to current-year matches isn't enough on its own: a current-year schedule
    chunk still has to out-score whatever undated results the query also pulled in, and
    a broad official course-syllabus page (long, topically on-target prose) routinely
    scores *higher* than a short, specific schedule chunk on pure cosine similarity —
    confirmed live: for "кога се полага дискретна математика" the one genuinely current
    schedule chunk (0.557) lost to five undated syllabus pages (0.57-0.64) and was
    dropped from the final top-k entirely. So a current-year match gets the same small
    reordering bump `_apply_recency_boost` gives a freshly-published announcement
    elsewhere in retrieval.py — enough to win close ties, not enough to drag an
    off-topic dated result above a clearly-better undated one.

    The boost affects ordering only, never `r.score` itself: `select_citation_sources`
    (called on this same list right after) drops anything more than a fixed gap below
    the top score, so permanently inflating a current-year match's score would inflate
    that reference point too and could silently drop an unrelated, unboosted, still-
    relevant source from the citation list purely because some other result got
    boosted — confirmed live. Sorting on a computed key instead keeps every result's
    `score` an honest, comparable cosine similarity for anything downstream.
    """
    years = {id(r): _effective_year(r) for r in results}
    dated = [r for r in results if years[id(r)] is not None]
    undated = [r for r in results if years[id(r)] is None]
    current_year_matches = [r for r in dated if years[id(r)] == current_year]
    kept_dated = current_year_matches if current_year_matches else dated

    boosted_ids = {id(r) for r in current_year_matches}
    schedule_boosts = _apply_schedule_chunk_recency_boost(results, now or datetime.now(timezone.utc))

    def sort_key(r: SearchResult) -> float:
        boost = RECENCY_MATCH_BOOST if id(r) in boosted_ids else 0.0
        boost += schedule_boosts.get(id(r), 0.0)
        return min(1.0, r.score + boost)

    merged = sorted(kept_dated + undated, key=sort_key, reverse=True)
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


def live_results_to_search_results(items: list[dict]) -> list[SearchResult]:
    """Wraps `search_official_site_live` hits (title/url/type/subtype only — see its
    docstring) as `SearchResult`s so the existing context/citation pipeline (built for
    indexed chunks) can carry them too, without a parallel code path. `chunk_text` is a
    placeholder the model is told (system prompt) never to treat as real page content —
    there is no excerpt to give it, only a title and a link. `score` is left at 0.0
    (meaningless here, there was no vector search) since these only ever appear when
    `results` was otherwise empty, so the gap cutoff in `select_citation_sources`
    compares them only against each other."""
    results = []
    for item in items:
        url = item.get("url")
        if not url:
            continue
        results.append(
            SearchResult(
                document_id=f"live:{url}",
                title=item.get("title") or url,
                url=url,
                source="official",
                type=item.get("subtype") or item.get("type") or "page",
                published_at=None,
                chunk_text="(live search result — title and link only, page content not fetched)",
                score=0.0,
                metadata={"live": True},
            )
        )
    return results


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
    now = datetime.now(timezone.utc)
    results = prefer_current_year(candidates, k=CHAT_RESULT_K, current_year=now.year, now=now)
    if not results:
        results = live_results_to_search_results(search_official_site_live(payload.message, limit=LIVE_FALLBACK_LIMIT))
    context = build_context(results)
    cited = select_citation_sources(results)

    contents = [
        types.Content(role=_gemini_role(m.role), parts=[types.Part.from_text(text=m.content)])
        for m in payload.history
    ]
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"Today's date: {now.date().isoformat()}\n\nContext:\n{context}\n\nQuestion: {payload.message}"
                )
            ],
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
