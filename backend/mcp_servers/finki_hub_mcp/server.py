"""MCP server exposing finki-hub.com data: courses, staff, recordings/materials,
exam session schedules, plus thesis archive (scraper not implemented yet — see
backend/scrapers/finki_hub/; that tool returns an empty list until it lands).

Run standalone: `python -m backend.mcp_servers.finki_hub_mcp.server`
"""

from mcp.server.fastmcp import FastMCP

from backend.mcp_servers.common import run_search

mcp = FastMCP("finki-hub")


@mcp.tool()
def search_courses(query: str, limit: int = 5) -> list[dict]:
    """Search FINKI courses by name or topic tag (e.g. "Вештачка интелигенција",
    "Бази на податоци"). Returns level, semester, prerequisites, professors/assistants,
    and accreditation years/tags from finki-hub's course listing. For the official
    syllabus text instead, use the finki-official server's `get_course_info` tool."""
    return run_search(query, k=limit, source="finki_hub", type="course")


@mcp.tool()
def search_staff(query: str, limit: int = 5) -> list[dict]:
    """Search FINKI teaching staff by name, position, or email. Returns title,
    position, cabinet, email, consultations link, and course portal link.
    For detailed professor bios and publications, use the finki-official server's
    `get_professor_info` tool instead."""
    return run_search(query, k=limit, source="finki_hub", type="staff")


@mcp.tool()
def search_materials(query: str, limit: int = 5) -> list[dict]:
    """Search recorded-lecture links, playlists, and notes shared per course on
    snimki.finki-hub.com — a student-maintained collection, not official/comprehensive
    (only courses the community has contributed a page for are covered)."""
    return run_search(query, k=limit, source="finki_hub", type="material")


@mcp.tool()
def search_thesis_archive(query: str, limit: int = 5) -> list[dict]:
    """Search completed bachelor's/master's theses by topic, mentor, or year. Not yet
    indexed — diplomski.finki-hub.com scraping isn't implemented."""
    return run_search(query, k=limit, source="finki_hub", type="thesis")


@mcp.tool()
def search_exam_sessions(query: str, limit: int = 5) -> list[dict]:
    """Search exam session schedules by session name or academic year (e.g. "Јуни 2025",
    "зимски колоквиум"). Returns download links to the schedule spreadsheets (XLSX/PDF)
    hosted on assets.finki-hub.com."""
    return run_search(query, k=limit, source="finki_hub", type="schedule")


if __name__ == "__main__":
    mcp.run()
