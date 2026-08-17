"""MCP server exposing the official finki.ukim.mk data: announcements (exam schedules,
enrollment notices, etc.), and course/professor pages (not scraped yet — see
backend/scrapers/registry.py; these tools return an empty list until that lands).

Run standalone: `python -m backend.mcp_servers.official_mcp.server`
"""

from mcp.server.fastmcp import FastMCP

from backend.mcp_servers.common import run_search

mcp = FastMCP("finki-official")


@mcp.tool()
def search_announcements(query: str, limit: int = 5) -> list[dict]:
    """Search the official student announcement board (огласна табла): enrollment
    notices, FSS elections, guest lectures, and exam-session schedule postings."""
    return run_search(query, k=limit, source="official", type="announcement")


@mcp.tool()
def get_exam_schedule(query: str = "испитна сесија распоред", limit: int = 5) -> list[dict]:
    """Find exam-session schedule references. Exact dates live in linked SharePoint
    spreadsheets, not in any page text — this returns the reference link (title + url)
    pointing to the right schedule file, not the dates themselves."""
    return run_search(query, k=limit, source="official", type="schedule")


@mcp.tool()
def get_course_info(query: str, limit: int = 5) -> list[dict]:
    """Search official course/subject pages by name or topic. Not yet indexed from
    finki.ukim.mk directly — prefer finki-hub's `search_courses` tool for now, which
    already covers course names, accreditation years, and tags."""
    return run_search(query, k=limit, source="official", type="course")


@mcp.tool()
def get_professor_info(query: str, limit: int = 5) -> list[dict]:
    """Search professor/staff directory pages by name. Not yet indexed."""
    return run_search(query, k=limit, source="official", type="professor")


if __name__ == "__main__":
    mcp.run()
