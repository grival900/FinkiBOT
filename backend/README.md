# Backend

FastAPI app, scrapers, ingestion/RAG pipeline, MCP servers, notifier, and quiz logic.

## Layout

| Path | Purpose |
|---|---|
| `api/` | FastAPI app + routers (`search`, `documents`, `chat`, `quiz`, `subscribe`/announcements, `admin`, `mcp_tools`) |
| `core/` | Shared config, LLM client wrapper, `retrieval.py` (the one place vector search lives) |
| `scrapers/official_site/` | `announcements.py` (the board), `schedule_links.py` (exam-session schedule reference links), `subjects.py` (official course syllabus prose — the gap on top of `finki_hub.courses`), `professors.py` (bios/publications — the gap on top of `finki_hub.staff`) |
| `scrapers/finki_hub/` | `courses.py` (course listing), `staff.py` (teaching staff), `sessions.py` (exam session schedules), `recordings.py` (recorded-lecture links/notes) — all fetch JSON from `assets.finki-hub.com`; thesis archive stub — see Known gaps |
| `scrapers/` (root) | `normalize.py` (common schema), `registry.py` (what `/admin/reindex` runs), `http.py` (shared rate-limited client) |
| `ingestion/` | Chunking, local embeddings (BGE-M3), pgvector indexing |
| `mcp_servers/` | `official_mcp/` and `finki_hub_mcp/` — thin tool layers over `core/retrieval.py` |
| `notifier/` | Subscription management, filter-matching diff, SMTP sending |
| `quiz/` | LLM quiz generation from an uploaded PDF/PPTX + text extraction (upload-only — see root README's "Where the LLM is used") |
| `models.py`, `db.py` | SQLAlchemy models and session setup |
| `alembic/` | DB migrations |
| `scheduler.py` | Periodic scrape → index → notify job (APScheduler) |
| `scripts/` | `reindex.py` (manual scrape + index), `seed.py`/`export_seed.py` (fast offline bootstrap from `seed/documents.json` — see "First time on a new machine" in the root README) |
| `tests/` | Unit tests — pure-logic and fixture-based, no live network or DB required |

## Local dev (without Docker)

```bash
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.sample .env  # fill in GEMINI_API_KEY at minimum for /chat and /quiz
alembic -c backend/alembic.ini upgrade head  # requires a running Postgres (see root docker-compose.yml)

uvicorn backend.api.main:app --reload
```

Run the test suite (no live services needed):

```bash
pytest backend/tests
```

Populate the database (fast, offline, no live scraping) from the bundled seed —
this is the recommended way to bootstrap a fresh Postgres, and is what a new machine
should run first (see "First time on a new machine" in the root README):

```bash
python -m backend.scripts.seed
```

Run an MCP server standalone (e.g. to point Claude Desktop or an MCP inspector at it):

```bash
python -m backend.mcp_servers.official_mcp.server
python -m backend.mcp_servers.finki_hub_mcp.server
```

Trigger a manual scrape + index pass:

```bash
curl -X POST http://localhost:8000/admin/reindex               # everything
curl -X POST "http://localhost:8000/admin/reindex?cadence=frequent"  # cheap sources only
curl -X POST "http://localhost:8000/admin/reindex?cadence=slow"      # expensive sources only
```

Each scraper in `registry.py` is tagged `frequent` or `slow`, and the two run on
separate scheduler intervals (`SCHEDULER_INTERVAL_MINUTES` and
`SCHEDULER_SLOW_INTERVAL_MINUTES`, once `ENABLE_SCHEDULER=true`) instead of together:

- **frequent** — announcements + the three `assets.finki-hub.com` JSON feeds
  (courses/staff/sessions). A handful of requests total; seconds to low minutes. These
  are also the time-sensitive ones (exam sessions, announcements), so they run hourly
  by default.
- **slow** — official course syllabi, professor profiles, and community recordings
  pages. None of these have a bulk endpoint, so it's one HTTP request per item —
  100+ requests at the deliberate 1 request/second rate limit against finki.ukim.mk
  and finki-hub.com (polite scraping, not something worth "fixing" by speeding up).
  Several minutes per pass, but this content rarely changes day to day, so it defaults
  to a weekly cadence instead of hourly.

A full reindex (no `cadence`, or the CLI script with no argument) runs both and takes
as long as the slow pass does. None of this is something a site visitor ever waits
through either way — `/search`, `/chat`, and the MCP tools only ever read whatever's
already indexed, regardless of what's running in the background.

## The seed (`seed/documents.json`)

A committed JSON snapshot of the `documents` table — title/url/content/metadata for
everything that was indexed at export time, deliberately **without** chunk
embeddings (they're cheap and fast to regenerate locally, ~2 minutes for everything
currently seeded, and re-deriving them avoids shipping vectors tied to a specific
embedding model version).

- `python -m backend.scripts.seed` loads it: chunks + embeds + upserts everything
  locally, no network calls to finki.ukim.mk/finki-hub.com at all. This is how a new
  machine should bootstrap instead of waiting on a live scrape.
- `python -m backend.scripts.export_seed` regenerates it from whatever's currently in
  the DB. Maintainer-only, manual — run it after a full reindex and commit the
  result if you want future first-time setups to start from fresher data. It's a
  snapshot, not a sync: it will drift stale between refreshes, which is fine, since
  the seed's job is a fast bootstrap, not a freshness guarantee — live scraping
  (scheduler or manual reindex) is what keeps things current after setup.
- Both go through the same `ingest_normalized_document` upsert path a live scrape
  does (matched by URL, unchanged content skipped), so seeding, reindexing, and
  re-seeding in any order/combination is safe and idempotent.

## Exam-session schedules

Two scrapers both produce `type=schedule` documents, deliberately — they're not
duplicates, they're two different reference sources students might search for by
different names:

- `finki_hub.sessions` (`source=finki_hub`) — `assets.finki-hub.com/sessions.json`,
  direct download links to the actual schedule spreadsheets, one clean JSON fetch.
  This is the primary source; prefer it.
- `official.schedule_links` (`source=official`) — the announcement board's own
  "Распоред на часови и консултации" widget, which links the same kind of SharePoint
  spreadsheet plus other reference links (e.g. the campus map) that aren't on
  finki-hub at all. Kept because it's cheap (one page, no per-item requests) and
  surfaces things finki-hub doesn't have, not because the exam-session part is
  uniquely necessary.

Neither parses the spreadsheet's contents — we only index the reference link (title +
URL), so the assistant can point a student to the right file but can't state exact
dates itself. This is expected, not a bug, until someone adds spreadsheet parsing.

## Known gaps (see `scrapers/registry.py`)

- `finki_hub.thesis_archive` (`diplomski.finki-hub.com`) — 4000+ individual thesis
  records across 68 mentors, reachable only via per-mentor click interactions (no API).
  Deliberately deferred — needs a scoping decision (index everything vs. a
  per-mentor summary vs. capped to recent years) before it's worth building.
- `finki_hub.schedules` (`rasporedi.finki-hub.com`) — class/lecture timetables, a
  different thing from exam-session schedules above. DOM not yet investigated.

Both registered but `enabled=False`, so `/admin/reindex` skips them instead of failing.
