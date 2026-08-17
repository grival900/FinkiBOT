# Backend

FastAPI app, scrapers, ingestion/RAG pipeline, MCP servers, notifier, and quiz logic.

## Layout

| Path | Purpose |
|---|---|
| `api/` | FastAPI app + routers (`search`, `chat`, `quiz`, `subscribe`/announcements, `admin`) |
| `core/` | Shared config, LLM client wrapper, `retrieval.py` (the one place vector search lives) |
| `scrapers/official_site/` | `announcements.py` (the board itself) and `schedule_links.py` (a separate reference-links widget in the board's page header — this is where exam-session schedule links actually live, see below) |
| `scrapers/finki_hub/` | `courses.py` (implemented) plus stubs for thesis/recordings/schedules — see Known gaps |
| `scrapers/` (root) | `normalize.py` (common schema), `registry.py` (what `/admin/reindex` runs), `http.py` (shared rate-limited client) |
| `ingestion/` | Chunking, local embeddings (BGE-M3), pgvector indexing |
| `mcp_servers/` | `official_mcp/` and `finki_hub_mcp/` — thin tool layers over `core/retrieval.py` |
| `notifier/` | Subscription management, filter-matching diff, SMTP sending |
| `quiz/` | LLM quiz generation (RAG-based and upload-based) + PDF/PPTX text extraction |
| `models.py`, `db.py` | SQLAlchemy models and session setup |
| `alembic/` | DB migrations |
| `scheduler.py` | Periodic scrape → index → notify job (APScheduler) |
| `tests/` | Unit tests — pure-logic and fixture-based, no live network or DB required |

## Local dev

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

## Exam-session schedules

The announcement board's own posts don't contain exam dates — they're published as
SharePoint spreadsheets linked from a small "Распоред на часови и консултации" widget
in the board's page header, scraped separately by `schedule_links.py` (`type=schedule`
documents). We only index the reference link (title + URL), not the spreadsheet's
contents, so the assistant can point a student to the right file but can't state exact
dates itself — this is expected, not a bug, until someone adds spreadsheet parsing.

## Known gaps (see `scrapers/registry.py`)

- `finki_hub.thesis_archive`, `finki_hub.recordings`, `finki_hub.schedules` are stubs —
  `diplomski.finki-hub.com`, `snimki.finki-hub.com`, and `rasporedi.finki-hub.com` use a
  different DOM (not the plain `<table>` `predmeti.finki-hub.com` has) and need their own
  selector investigation before they can be scraped. They're registered but `enabled=False`
  so `/admin/reindex` skips them instead of failing.
- Official course/subject pages (`finki.ukim.mk/mk/subject/<code>`) and professor pages
  aren't scraped directly yet — `finki_hub.courses` (run with `deep=True`) already links
  each course to its official subject page URL, which is the natural next step for a
  proper official-site course scraper.
