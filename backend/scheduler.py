import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.ingestion.pipeline import run_full_ingestion
from backend.notifier.job import run_notification_job

logger = logging.getLogger(__name__)


def scrape_and_notify() -> None:
    stats = run_full_ingestion()
    logger.info("Ingestion complete: %s", stats)
    notified = run_notification_job()
    logger.info("Sent %d announcement notifications", notified)


def start_scheduler(interval_minutes: int = 60) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(scrape_and_notify, "interval", minutes=interval_minutes, id="scrape_and_notify")
    scheduler.start()
    return scheduler
