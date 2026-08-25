from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import admin, auth, chat, documents, insights, mcp_tools, quiz, search, subscribe
from backend.core.config import get_settings
from backend.ingestion.embeddings import embed_texts
from backend.scheduler import start_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Loading BAAI/bge-m3 (~20s) happens lazily on first use otherwise — pay that cost
    # once at boot instead of making whichever student sends the first /chat or /search
    # after a (re)start eat it as request latency. No requests are being served yet at
    # this point in the lifespan, so blocking here is free.
    embed_texts(["warmup"])

    # Always created (not just when enable_scheduler=true) and stashed on app.state so
    # the admin settings endpoint can pause/resume/reschedule jobs live — this used to
    # be a lifespan-closure-local variable, unreachable from any request handler.
    scheduler = start_scheduler(settings.scheduler_interval_minutes, settings.scheduler_slow_interval_minutes)
    if not settings.enable_scheduler:
        for job_id in ("scrape_and_notify", "scrape_slow"):
            scheduler.pause_job(job_id)
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="FinkiBOT API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(documents.router)
app.include_router(mcp_tools.router)
app.include_router(insights.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(subscribe.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
