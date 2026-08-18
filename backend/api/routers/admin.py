from fastapi import APIRouter

from backend.ingestion.pipeline import run_full_ingestion
from backend.notifier.job import run_notification_job

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reindex")
def reindex() -> dict[str, int]:
    """Runs every enabled scraper and ingests results. Synchronous and can take a
    while (Playwright-driven finki_hub scrapers especially) — fine for a manual admin
    trigger, but the periodic run in `backend/scheduler.py` calls the same function."""
    return run_full_ingestion()


@router.post("/notify")
def notify() -> dict[str, int]:
    """Diffs every confirmed subscription against indexed announcements and emails any
    unsent matches — the same function the scheduler calls after each reindex, exposed
    here so it can be triggered on its own (e.g. to test the email flow without waiting
    for/running a full reindex first)."""
    return {"notified": run_notification_job()}
