"""MCP server exposing finki-hub.com data: courses (indexed), plus materials, thesis
archive, and schedules (scrapers not implemented yet — see backend/scrapers/finki_hub/;
these tools return an empty list until that lands).

Run standalone: `python -m backend.mcp_servers.finki_hub_mcp.server`
"""

from mcp.server.fastmcp import FastMCP

from backend.mcp_servers.common import run_search

mcp = FastMCP("finki-hub")


@mcp.tool()
def search_courses(query: str, limit: int = 5) -> list[dict]:
    """Search FINKI courses by name or topic tag (e.g. "Вештачка интелигенција",
    "Бази на податоци"). Returns accreditation years and tags; each result's `url`
    links to the course on predmeti.finki-hub.com or, when available, the official
    finki.ukim.mk subject page."""
    return run_search(query, k=limit, source="finki_hub", type="course")


@mcp.tool()
def search_materials(query: str, limit: int = 5) -> list[dict]:
    """Search course materials (slides, notes) shared on finki-hub. Not yet indexed —
    snimki.finki-hub.com/predmeti materials scraping isn't implemented."""
    return run_search(query, k=limit, source="finki_hub", type="material")


@mcp.tool()
def search_thesis_archive(query: str, limit: int = 5) -> list[dict]:
    """Search completed bachelor's/master's theses by topic, mentor, or year. Not yet
    indexed — diplomski.finki-hub.com scraping isn't implemented."""
    return run_search(query, k=limit, source="finki_hub", type="thesis")


@mcp.tool()
def get_schedule(query: str, limit: int = 5) -> list[dict]:
    """Look up class schedules. Not yet indexed — rasporedi.finki-hub.com scraping
    isn't implemented; for exam-session schedules in the meantime, prefer the
    finki-official server's `get_exam_schedule` tool."""
    return run_search(query, k=limit, source="finki_hub", type="schedule")


if __name__ == "__main__":
    mcp.run()
