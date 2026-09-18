import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.routers import admin, auth, chat, courses, documents, insights, mcp_tools, quiz, search, subscribe
from backend.core.config import get_settings
from backend.ingestion.embeddings import embed_texts
from backend.scheduler import start_scheduler

logger = logging.getLogger(__name__)
settings = get_settings()


class UnhandledExceptionMiddleware(BaseHTTPMiddleware):
    """An exception a route handler raises *before* producing any response (e.g.
    `/chat` picking an LLM provider — see `llm_providers.stream_chat_with_failover`,
    called synchronously before `StreamingResponse` is even constructed) would
    otherwise be caught by Starlette's own `ServerErrorMiddleware`, not FastAPI's
    `@app.exception_handler`. That matters because `ServerErrorMiddleware` is always
    the outermost layer, wrapped *around* `CORSMiddleware` below regardless of
    registration order (confirmed live against this exact Starlette version's
    `Starlette.build_middleware_stack` — a handler registered for the bare
    `Exception` class is pulled out and passed to `ServerErrorMiddleware` itself,
    which then bypasses `CORSMiddleware` entirely) — so an unhandled 500 carries no
    CORS headers at all, and the browser can't even read it: `fetch()` reports an
    opaque "Failed to fetch" instead of a real, displayable error. This middleware
    must be added *before* `CORSMiddleware` (below) so it ends up positioned inside
    it (`Starlette.add_middleware` prepends, so source order here is the reverse of
    wrap order) — a plain `Response` it returns still passes back out through
    `CORSMiddleware` normally and gets the same headers a success response would.

    Only catches a failure that happens *before* any response starts (a regular
    route handler raising, or a streaming one raising before its first byte) —
    once a `StreamingResponse` has begun sending its body, `call_next` has already
    returned successfully and a later exception inside the generator is outside
    this middleware's reach; that failure mode was already an accepted, documented
    limitation (see `stream_chat_with_failover`'s docstring), not something this
    changes."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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

# Added before CORSMiddleware so it ends up wrapped *by* it - see the class docstring
# for why that ordering (not registration as an `@app.exception_handler`) is what
# actually gets CORS headers onto an unhandled-exception response.
app.add_middleware(UnhandledExceptionMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers only expose the CORS-safelisted response headers to JS by default
    # (Content-Type etc.) - without this, /chat's X-LLM-Provider header (which model
    # answered the request) is sent but invisible to the frontend's fetch() response.
    expose_headers=["X-LLM-Provider"],
)

app.include_router(search.router)
app.include_router(courses.router)
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
