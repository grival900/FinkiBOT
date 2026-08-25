import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.api.schemas import AdminUserPatch, ScraperEnabledOut, SiteSettingsOut, SiteSettingsPatch, UserOut
from backend.core.auth import require_admin
from backend.core.config import get_settings
from backend.core.site_settings import (
    get_bool_setting,
    get_float_setting,
    get_int_or_none_setting,
    get_int_setting,
    set_setting,
)
from backend.core.users import (
    LastAdminError,
    SelfActionError,
    count_other_active_admins,
    delete_user,
    guard_last_admin,
    guard_not_self,
    set_active_status,
    set_admin_status,
)
from backend.db import get_db
from backend.ingestion.pipeline import run_ingestion
from backend.models import User
from backend.notifier.emailer import send_password_reset_email
from backend.notifier.job import run_notification_job
from backend.scrapers.registry import SCRAPERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


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


# --- user management --------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.created_at).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(
    user_id: UUID,
    payload: AdminUserPatch,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    will_demote = payload.is_admin is False and target.is_admin
    will_deactivate = payload.is_active is False and target.is_active
    if will_demote or will_deactivate:
        try:
            guard_not_self(target.id, current.id)
            guard_last_admin(target.is_admin and target.is_active, count_other_active_admins(db, target.id))
        except (SelfActionError, LastAdminError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if payload.is_admin is not None:
        set_admin_status(db, target, payload.is_admin)
    if payload.is_active is not None:
        set_active_status(db, target, payload.is_active)
    return target


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(user_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_admin)) -> None:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        guard_not_self(target.id, current.id)
        guard_last_admin(target.is_admin and target.is_active, count_other_active_admins(db, target.id))
    except (SelfActionError, LastAdminError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    delete_user(db, target)


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(user_id: UUID, db: Session = Depends(get_db)) -> dict[str, str]:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    target.reset_token = secrets.token_urlsafe(32)
    target.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.commit()

    reset_url = f"{get_settings().frontend_origin}/reset-password?token={target.reset_token}"
    send_password_reset_email(target.email, reset_url)
    return {"status": "reset_email_sent"}


# --- site settings -----------------------------------------------------------------


def _effective_settings(db: Session) -> SiteSettingsOut:
    defaults = get_settings()
    return SiteSettingsOut(
        scrape_announcement_limit=get_int_or_none_setting(
            db, "scrape_announcement_limit", defaults.scrape_announcement_limit
        ),
        scrape_subjects_limit=get_int_or_none_setting(db, "scrape_subjects_limit", defaults.scrape_subjects_limit),
        scrape_request_delay_seconds=get_float_setting(
            db, "scrape_request_delay_seconds", defaults.scrape_request_delay_seconds
        ),
        enable_scheduler=get_bool_setting(db, "enable_scheduler", defaults.enable_scheduler),
        scheduler_interval_minutes=get_int_setting(
            db, "scheduler_interval_minutes", defaults.scheduler_interval_minutes
        ),
        scheduler_slow_interval_minutes=get_int_setting(
            db, "scheduler_slow_interval_minutes", defaults.scheduler_slow_interval_minutes
        ),
        scrapers=[
            ScraperEnabledOut(
                name=entry.name,
                enabled=entry.enabled and get_bool_setting(db, f"scraper_enabled:{entry.name}", True),
            )
            for entry in SCRAPERS
        ],
    )


@router.get("/settings", response_model=SiteSettingsOut)
def get_site_settings(db: Session = Depends(get_db)) -> SiteSettingsOut:
    return _effective_settings(db)


@router.put("/settings", response_model=SiteSettingsOut)
def update_site_settings(payload: SiteSettingsPatch, request: Request, db: Session = Depends(get_db)) -> SiteSettingsOut:
    fields = payload.model_fields_set  # distinguishes "sent as null" from "not sent" for the nullable ints
    scheduler = getattr(request.app.state, "scheduler", None)

    if "scrape_announcement_limit" in fields:
        set_setting(db, "scrape_announcement_limit", payload.scrape_announcement_limit)
    if "scrape_subjects_limit" in fields:
        set_setting(db, "scrape_subjects_limit", payload.scrape_subjects_limit)
    if payload.scrape_request_delay_seconds is not None:
        set_setting(db, "scrape_request_delay_seconds", payload.scrape_request_delay_seconds)

    if payload.enable_scheduler is not None and scheduler is not None:
        set_setting(db, "enable_scheduler", payload.enable_scheduler)
        for job_id in ("scrape_and_notify", "scrape_slow"):
            (scheduler.resume_job if payload.enable_scheduler else scheduler.pause_job)(job_id)

    if payload.scheduler_interval_minutes is not None:
        set_setting(db, "scheduler_interval_minutes", payload.scheduler_interval_minutes)
        if scheduler is not None:
            scheduler.reschedule_job("scrape_and_notify", trigger="interval", minutes=payload.scheduler_interval_minutes)
    if payload.scheduler_slow_interval_minutes is not None:
        set_setting(db, "scheduler_slow_interval_minutes", payload.scheduler_slow_interval_minutes)
        if scheduler is not None:
            scheduler.reschedule_job("scrape_slow", trigger="interval", minutes=payload.scheduler_slow_interval_minutes)

    if payload.scraper_enabled:
        valid_names = {entry.name for entry in SCRAPERS}
        for name, enabled in payload.scraper_enabled.items():
            if name not in valid_names:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown scraper: {name}")
            set_setting(db, f"scraper_enabled:{name}", enabled)

    return _effective_settings(db)
