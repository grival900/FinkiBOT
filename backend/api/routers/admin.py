from fastapi import APIRouter

from backend.ingestion.pipeline import run_full_ingestion

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reindex")
def reindex() -> dict[str, int]:
    """Runs every enabled scraper and ingests results. Synchronous and can take a
    while (Playwright-driven finki_hub scrapers especially) — fine for a manual admin
    trigger, but the periodic run in `backend/scheduler.py` calls the same function."""
    return run_full_ingestion()
