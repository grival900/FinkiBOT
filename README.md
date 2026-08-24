# FinkiBOT — Smart College Assistant for FINKI

FinkiBOT scrapes the official FINKI site (`finki.ukim.mk`) and the student-run
[finki-hub.com](https://finki-hub.com), indexes everything into a RAG-ready vector
store (Postgres + pgvector), and gives students a few ways to use it:

- **Chat** — ask a question, get a cited answer grounded in what's actually indexed
- **Search** — raw ranked results instead of an LLM-written answer
- **Quiz maker** — generates quiz questions from a course or an uploaded PDF/PPTX
- **Subscribe** — email alerts when new announcements match your keywords/courses
- **MCP tools playground** — the same tools an MCP client (e.g. Claude Desktop) can
  call, runnable/inspectable directly on the site

Two **MCP servers** (`official_mcp`, `finki_hub_mcp`) expose that same indexed data
as standardized tools for external AI clients — see [`backend/mcp_servers/`](backend/mcp_servers).

## Layout

```
backend/    FastAPI app, scrapers, RAG/ingestion pipeline, MCP servers, notifier, quiz logic
frontend/   React web app (chat, search, quiz, subscribe, MCP playground)
```

For module-by-module detail, non-Docker local dev, and known scraper gaps, see
[backend/README.md](backend/README.md).

## Prerequisites

- **Docker Desktop**, running
- A free **Gemini API key** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (no card required)

That's it — everything else (Postgres, the embedding model, Node, Python) runs inside
containers.

## Getting started (first time)

Run these in order from the repo root:

```bash
# 1. Copy the env template and fill in GEMINI_API_KEY (required for chat + quiz)
cp backend/.env.sample backend/.env

# 2. Build and start everything: Postgres, backend API, frontend
docker compose up --build
```

Leave that running in one terminal. In a second terminal, populate the database —
it starts empty, so nothing will show up in chat/search until you run this:

```bash
# 3. Scrape + index the cheap/time-sensitive sources first (well under a minute) —
#    announcements + finki-hub's courses/staff/sessions JSON feeds
docker compose exec backend python -m backend.scripts.reindex frequent

# 4. Then the slower sources (official course syllabi, professor profiles,
#    finki-hub recordings — one HTTP request per item, several minutes)
docker compose exec backend python -m backend.scripts.reindex slow
```

(Or just `python -m backend.scripts.reindex` with no argument for both at once.)

That's the whole setup. Once it finishes, open:

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API docs | http://localhost:8000/docs |
| Mailhog (catches subscription emails, nothing sent for real) | http://localhost:8025 |
| Adminer (browse the database directly) | http://localhost:8090 — server `db`, user/pass/db `finkibot` |

Optionally, confirm the backend tests pass:

```bash
docker compose exec backend pytest backend/tests
```

## Day-to-day

Once the one-time setup above is done, this is all you need:

```bash
docker compose up -d      # start everything (no --build needed unless you changed
                           # the Dockerfile, requirements.txt, or package.json)
docker compose down       # stop everything — your data is untouched (see below)
```

Both backend and frontend are bind-mounted with hot reload already wired up, so
editing code and saving just works — no rebuild, no restart.

Your scraped data persists in a Docker volume, not in the containers, so
`docker compose down` / `up` won't lose it. Re-run the reindex whenever you want
fresh data (new announcements, updated course info) — it doesn't happen
automatically in dev (`ENABLE_SCHEDULER=false` in `.env`; when enabled, frequent
sources refresh hourly and slow ones weekly by default — see `backend/README.md`):

```bash
docker compose exec backend python -m backend.scripts.reindex frequent  # seconds
docker compose exec backend python -m backend.scripts.reindex slow      # minutes
```

Other useful commands:

```bash
docker compose ps                  # what's running
docker compose logs -f backend     # tail logs (or: frontend, db, mailhog, adminer)
docker compose up -d --build       # rebuild after touching Dockerfile/requirements.txt/package.json
```

> **Windows/Docker Desktop note:** the frontend's file-watcher doesn't always pick up
> edits made from outside the container (a known bind-mount limitation). If a saved
> change isn't showing up in the browser, run `docker compose restart frontend`.
>
> Similarly, editing `backend/.env` requires recreating the backend container to take
> effect — `docker compose restart backend` is not enough, since Docker Compose only
> re-reads `.env` on creation:
> ```bash
> docker compose up -d --force-recreate backend
> ```

## Where the LLM is used

1. **Chat** (`/chat`) — retrieves top-k matching chunks, sends them + your question to
   Gemini in one call, streams back a cited answer.
2. **Quiz generation** (`/quiz/generate`, `/quiz/upload`) — turns retrieved course
   content or an uploaded file into structured quiz questions.
3. **Embeddings** — a local model (`BAAI/bge-m3`), not an API call, since content is
   mostly Macedonian and this avoids per-embedding cost.

Scraping, normalization, and the email notifier are deliberately LLM-free — search and
MCP tools return raw indexed data, not generated text.

Uses the **Gemini API free tier** (`gemini-2.5-flash`) — free for a project this size,
but rate-limited (1,500 requests/day) and Google may use free-tier prompts to improve
their products, worth knowing if students upload their own materials to the quiz
maker. Swapping providers means touching `backend/core/llm.py`,
`backend/api/routers/chat.py`, and `backend/quiz/generation.py`.

## What's indexed right now

finki-hub.com is preferred wherever it has the data — cheap single JSON fetches vs.
finki.ukim.mk's one-request-per-item pages with no bulk endpoint. Official is only
scraped for what finki-hub genuinely doesn't have (or doesn't have in full: syllabus
prose beyond finki-hub's course metadata).

| Source | Content | Scraper |
|---|---|---|
| finki-hub.com | Course listing (level, semester, professors, prerequisites, accreditation) | `finki_hub.courses` |
| finki-hub.com | Teaching staff directory (title, position, cabinet, email, consultations) | `finki_hub.staff` |
| finki-hub.com | Exam-session schedule download links | `finki_hub.sessions` |
| finki-hub.com | Recorded-lecture links & notes per course | `finki_hub.recordings` |
| finki.ukim.mk | Announcement board | `official.announcements` |
| finki.ukim.mk | Exam-session schedule reference links (from the announcement board widget) | `official.schedule_links` |
| finki.ukim.mk | Official course syllabus prose — objectives, content outline, literature (capped, see `SCRAPE_SUBJECTS_LIMIT`) | `official.subjects` |
| finki.ukim.mk | Professor bios/publications (finki-hub's staff directory has contact info only, no bios) | `official.professors` |

**Not yet implemented** (registered but disabled in `backend/scrapers/registry.py`,
so a reindex skips them instead of failing): finki-hub's thesis archive (4000+
records, needs its own scoping) and class schedules (`rasporedi.finki-hub.com`).

**Known broken:** none currently — `official.pages` (static info pages) was removed
this session; its only discovery mechanism (finki.ukim.mk's WordPress sitemap)
dead-redirects after the site's redesign, so it had been silently indexing nothing.
If someone wants that content back, it needs a real listing page found on the live
site first (same fix `official.professors` got — see its docstring).

## A quick heads-up if something's not scraping right

The scrapers target live external sites that occasionally change their HTML/URL
structure — if a reindex comes back oddly empty or search results look off, that's
usually the first thing to check, not a bug in the pipeline itself.
