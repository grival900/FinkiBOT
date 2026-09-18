"""Retrieval tools exposed to the chat LLM as Gemini automatic-function-calling
tools, so it can look up related FINKI data itself — e.g. which courses a named
professor teaches, then each of those courses' exam schedule/materials/consultations
— instead of relying on a single upfront search plus one hardcoded heuristic hop.

Each tool wraps `backend.core.retrieval.search` (or, for `find_courses_taught_by`, a
small structured query) scoped to one source/type — mirroring the MCP servers'
existing tool surface (`official_mcp`, `finki_hub_mcp`: the same well-scoped lookups,
just made directly callable by the chat model itself instead of only reachable
through a separate MCP client). The google-genai SDK derives each tool's schema from
its Python signature and docstring (no `Args:` section needed — only the function-
level description and parameter names/types feed the schema), so the docstrings here
double as what the model actually sees.

Every tool call's results are also appended to `collected` (a list the caller owns)
so they can be folded into the citation pipeline alongside the upfront search
results — custom function calling carries no built-in grounding/citation metadata
the model reports back, so the existing score-based `select_citation_sources` is
reused on the combined pool rather than trusting the model to say what it used.
"""

import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.core.retrieval import SearchResult, search
from backend.mcp_servers.common import result_to_dict
from backend.mcp_servers.official_live_mcp.server import search_official_site_live
from backend.models import Document

# Official-site professor titles bake a leading academic honorific into the name
# text itself ("д-р Слободан Калајџиски") — confirmed live against the seeded data,
# only "д-р"/"м-р" (with an occasional stray trailing period, "м-р.") actually occur.
# finki_hub course content's own "Професори: ..." line never carries one, so this
# must be stripped before matching a resolved professor name against it.
_ACADEMIC_TITLE_RE = re.compile(r"^(?:д-р|м-р\.?)\s+", re.IGNORECASE)
# Bounded so one prolific professor's course list can't itself balloon the number of
# follow-up tool calls the model then makes one per course.
_COURSES_PER_PROFESSOR_LIMIT = 8


def _strip_academic_title(name: str) -> str:
    return _ACADEMIC_TITLE_RE.sub("", name).strip()


def find_courses_taught_by(db: Session, professor_name: str, limit: int = _COURSES_PER_PROFESSOR_LIMIT) -> list[dict]:
    """Pure-ish query, unit-testable with a mocked `db`: matches every whitespace
    token of the (honorific-stripped) name independently, AND'ed together, rather
    than requiring the whole name as one exact substring. Two reasons: it tolerates
    the honorific-stripped query still not exactly equalling how the name appears in
    finki_hub content (official-site names sometimes use a shorter public form than
    finki_hub's full name — confirmed live, e.g. official "д-р Магдалена Костоска" vs
    finki_hub "Магдалена Костоска Ѓорчевска" — a whole-string substring check would
    never match either direction), and it means the honorific words themselves just
    need excluding up front rather than tolerated as noise inside a single substring."""
    bare_name = _strip_academic_title(professor_name)
    tokens = [t for t in bare_name.split() if len(t) > 1]
    if not tokens:
        return []
    rows = (
        db.query(Document)
        .filter(
            Document.source == "finki_hub",
            Document.type == "course",
            and_(*[Document.content.ilike(f"%{t}%") for t in tokens]),
        )
        .limit(limit)
        .all()
    )
    return [{"title": r.title, "url": r.url} for r in rows]


def build_chat_tools(
    db: Session, min_score: float | None, now: datetime, collected: list[SearchResult]
) -> list[Callable]:
    """Returns this request's tool set as plain Python callables for
    `GenerateContentConfig.tools` — closing over `db`/`min_score`/`now` (none of
    which the model itself ever supplies) and appending every tool call's results to
    `collected` so the caller can fold them into citations after the stream ends."""

    def _run(query: str, limit: int, source: str, doc_type: str) -> list[dict]:
        # recency_boost, same reasoning as the MCP tools' own `run_search`: a
        # deliberate tool call for "the latest X" almost always wants the current
        # posting of a recurring announcement/schedule, not whichever year's copy
        # happens to score highest on vector similarity alone.
        results = search(db, query, k=limit, source=source, type=doc_type, min_score=min_score, recency_boost=True)
        collected.extend(results)
        return [result_to_dict(r) for r in results]

    def search_announcements(query: str, limit: int = 5) -> list[dict]:
        """Search the official student announcement board (огласна табла): enrollment
        notices, FSS elections, guest lectures, and exam-session schedule postings."""
        return _run(query, limit, "official", "announcement")

    def get_course_info(query: str, limit: int = 5) -> list[dict]:
        """Search official course syllabus pages by name or topic: full syllabus
        text — prerequisites, teacher, ECTS credits, learning objectives, content
        outline, and literature."""
        return _run(query, limit, "official", "course")

    def get_professor_info(query: str, limit: int = 5) -> list[dict]:
        """Search official professor/staff directory pages by name: bio/resume,
        publications, and contact email when filled in."""
        return _run(query, limit, "official", "professor")

    def search_faculty_info(query: str, limit: int = 5) -> list[dict]:
        """Search static faculty info pages: organization/leadership, study
        programs, admissions requirements, international-student info, and contact
        details. Not for announcements, course syllabi, or professor bios."""
        return _run(query, limit, "official", "page")

    def get_exam_schedule_reference(query: str, limit: int = 5) -> list[dict]:
        """Find the official exam-session reference link (finki.ukim.mk) for a
        session by name — title and URL only, the exact per-course dates live in a
        linked spreadsheet this does not parse. Prefer `search_exam_sessions` for
        actual per-course exam dates/times/rooms."""
        return _run(query, limit, "official", "schedule")

    def search_courses(query: str, limit: int = 5) -> list[dict]:
        """Search FINKI courses by name or topic (finki-hub.com): level, semester,
        prerequisites, professors/assistants, and accreditation years/tags."""
        return _run(query, limit, "finki_hub", "course")

    def search_staff(query: str, limit: int = 5) -> list[dict]:
        """Search FINKI teaching staff by name, position, or email (finki-hub.com):
        title, position, cabinet, email, and course portal link."""
        return _run(query, limit, "finki_hub", "staff")

    def search_consultations(query: str, limit: int = 5) -> list[dict]:
        """Search a named professor's scheduled consultation slots: actual
        date/time/room for each upcoming slot, or that none are currently
        scheduled."""
        return _run(query, limit, "finki_hub", "consultation")

    def search_materials(query: str, limit: int = 5) -> list[dict]:
        """Search recorded-lecture links, playlists, and notes shared per course
        (snimki.finki-hub.com) — student-maintained, not comprehensive."""
        return _run(query, limit, "finki_hub", "material")

    def search_exam_sessions(query: str, limit: int = 5) -> list[dict]:
        """Search exam session schedules by session name, academic year, or course
        name (e.g. "Јуни 2025", "Дистрибуирани системи"). Returns the actual
        per-course date/time/room extracted from the schedule spreadsheets — this is
        the tool for "when is X's exam" questions, not `get_exam_schedule_reference`.
        Raise `limit` (up to ~20) for a broad "the whole session's schedule" question
        instead of one specific course."""
        return _run(query, limit, "finki_hub", "schedule")

    def find_courses_taught_by_(professor_name: str, limit: int = _COURSES_PER_PROFESSOR_LIMIT) -> list[dict]:
        """Find every course a named professor or assistant teaches. A professor's
        name has no direct semantic link to their own exam schedule, materials, or
        consultation slots — those only ever name courses/rooms/times, never who
        teaches them, so this is the tool to bridge person -> courses first. Use it
        before answering a compound question like "when does professor X's course
        get examined" or "what courses does X teach", then call
        `search_exam_sessions`/`search_materials`/etc. once per course name found."""
        return find_courses_taught_by(db, professor_name, limit)

    find_courses_taught_by_.__name__ = "find_courses_taught_by"

    def live_site_search(query: str, limit: int = 3) -> list[dict]:
        """Search finki.ukim.mk's own live site search (not the local index) — use
        this only when the other tools above found nothing relevant, to check
        whether the official site has something newer than the local index."""
        return search_official_site_live(query, limit=limit)

    return [
        search_announcements,
        get_course_info,
        get_professor_info,
        search_faculty_info,
        get_exam_schedule_reference,
        search_courses,
        search_staff,
        search_consultations,
        search_materials,
        search_exam_sessions,
        find_courses_taught_by_,
        live_site_search,
    ]
