import logging
import threading
from typing import Literal

from fastapi import APIRouter

from backend.ingestion.pipeline import run_ingestion
from backend.notifier.job import run_notification_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _background_reindex(cadence: str | None) -> None:
    try:
        stats = run_ingestion(cadence)
        logger.info("Reindex (%s) finished: %s", cadence or "full", stats)
    except Exception:
        logger.exception("Background reindex failed")


@router.post("/reindex")
def reindex(cadence: Literal["frequent", "slow"] | None = None) -> dict[str, str]:
    """Kicks off a reindex in a background thread and returns immediately so the
    server stays responsive for search/chat requests during the run.

    `cadence` scopes the run: "frequent" hits only cheap/time-sensitive sources
    (announcements, JSON feeds — seconds to low minutes), "slow" hits only the
    sources with one HTTP request per item and no bulk endpoint (official course
    syllabi, professor profiles, recordings — 100+ rate-limited requests, several
    minutes). Omit for a full reindex of everything (also several minutes, dominated
    by the same slow sources). The scheduler already runs both cadences on their own
    intervals (see `scheduler.py`) — this endpoint is for an on-demand/manual run."""
    thread = threading.Thread(target=_background_reindex, args=(cadence,), daemon=True)
    thread.start()
    return {"status": f"reindex ({cadence or 'full'}) started in background"}


@router.post("/notify")
def notify() -> dict[str, int]:
    """Diffs every confirmed subscription against indexed announcements and emails any
    unsent matches — the same function the scheduler calls after each reindex, exposed
    here so it can be triggered on its own (e.g. to test the email flow without waiting
    for/running a full reindex first)."""
    return {"notified": run_notification_job()}
