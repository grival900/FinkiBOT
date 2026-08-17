# Backend

FastAPI app, scrapers, ingestion/RAG pipeline, MCP servers, notifier, and quiz logic.

## Layout

| Path | Purpose |
|---|---|
| `api/` | FastAPI app + routers (`search`, `documents`, `chat`, `quiz`, `subscribe`/announcements, `admin`, `mcp_tools`) |
| `core/` | Shared config, LLM client wrapper, `retrieval.py` (the one place vector search lives) |
| `scrapers/official_site/` | `announcements.py` (the board), `schedule_links.py` (exam-session schedule links), `pages.py` (static info pages, sitemap-driven), `subjects.py` (official course syllabi), `professors.py` (staff profiles) |
| `scrapers/finki_hub/` | `courses.py` (course listing) and `recordings.py` (recorded-lecture links/notes) — implemented; stubs for thesis archive/schedules — see Known gaps |
| `scrapers/` (root) | `normalize.py` (common schema), `registry.py` (what `/admin/reindex` runs), `http.py` (shared rate-limited client) |
| `ingestion/` | Chunking, local embeddings (BGE-M3), pgvector indexing |
| `mcp_servers/` | `official_mcp/` and `finki_hub_mcp/` — thin tool layers over `core/retrieval.py` |
| `notifier/` | Subscription management, filter-matching diff, SMTP sending |
| `quiz/` | LLM quiz generation (RAG-based and upload-based) + PDF/PPTX text extraction |
| `models.py`, `db.py` | SQLAlchemy models and session setup |
| `alembic/` | DB migrations |
| `scheduler.py` | Periodic scrape → index → notify job (APScheduler) |
| `tests/` | Unit tests — pure-logic and fixture-based, no live network or DB required |

## Local dev (without Docker)

```bash
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium   # needed for the finki_hub scrapers

cp .env.sample .env  # fill in GEMINI_API_KEY at minimum for /chat and /quiz
alembic -c backend/alembic.ini upgrade head  # requires a running Postgres (see root docker-compose.yml)

uvicorn backend.api.main:app --reload
```

Run the test suite (no live services needed):

```bash
pytest backend/tests
```

Run an MCP server standalone (e.g. to point Claude Desktop or an MCP inspector at it):

```bash
python -m backend.mcp_servers.official_mcp.server
python -m backend.mcp_servers.finki_hub_mcp.server
```

Trigger a manual scrape + index pass (also runs automatically every `SCHEDULER_INTERVAL_MINUTES`
once `ENABLE_SCHEDULER=true`):

```bash
curl -X POST http://localhost:8000/admin/reindex
```

A full reindex touches every enabled scraper in `registry.py` and takes ~15-20
minutes — most of that is a deliberate 1 request/second rate limit against
finki.ukim.mk and finki-hub.com (polite scraping, not something worth "fixing" by
speeding up). It's a one-time/periodic maintenance operation, not something a site
visitor ever waits through — `/search`, `/chat`, and the MCP tools only ever read
whatever's already indexed.

## Exam-session schedules

The announcement board's own posts don't contain exam dates — they're published as
SharePoint spreadsheets linked from a small "Распоред на часови и консултации" widget
on the announcement board page, scraped separately by `schedule_links.py` (`type=schedule`
documents). We only index the reference link (title + URL), not the spreadsheet's
contents, so the assistant can point a student to the right file but can't state exact
dates itself — this is expected, not a bug, until someone adds spreadsheet parsing.

## Known gaps (see `scrapers/registry.py`)

- `finki_hub.thesis_archive` (`diplomski.finki-hub.com`) — 4000+ individual thesis
  records across 68 mentors, reachable only via per-mentor click interactions (no API).
  Deliberately deferred — needs a scoping decision (index everything vs. a
  per-mentor summary vs. capped to recent years) before it's worth building.
- `finki_hub.schedules` (`rasporedi.finki-hub.com`) — different DOM, not yet
  investigated.

Both are registered but `enabled=False`, so `/admin/reindex` skips them instead of
failing.
