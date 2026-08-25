"""Admin-editable operational settings, backed by the `site_settings` key/value table.

Deliberately covers only a curated, "safe" subset: scraper limits, the scrape rate
delay, scheduler intervals/on-off, and per-scraper enable/disable. Secrets (API keys,
DB/SMTP credentials, the JWT signing key) are never in this table — they stay
`.env`-only and are never returned by any endpoint in this module's orbit.

`get_settings()` (core/config.py) is a process-wide `lru_cache`d singleton that only
ever reads `.env` — it has no awareness of this table. Every curated field's env value
is used only as the *fallback default* when no DB override row exists; the DB always
wins once an admin has set something.

Two access patterns:
- `get_setting`/`get_all_settings`/`set_settings` — request-scoped, take an open `db`
  Session (used by the admin router).
- `get_setting_cached` — for scraper code with no ambient request/session (e.g.
  `scrapers/http.py`'s `get()`, called hundreds of times per reindex). Opens its own
  short-lived session and caches the whole table for a few seconds so a live setting
  change is visible within moments, not immediately, without hammering the DB.
"""

import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from backend.db import SessionLocal
from backend.models import SiteSetting

T = TypeVar("T")

parse_int_or_none: Callable[[str], int | None] = lambda s: None if s == "" else int(s)  # noqa: E731
_parse_float: Callable[[str], float] = float
_parse_bool: Callable[[str], bool] = lambda s: s.lower() == "true"  # noqa: E731


def _serialize(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def get_setting(db: Session, key: str, default: T, parse: Callable[[str], T]) -> T:
    row = db.get(SiteSetting, key)
    if row is None:
        return default
    return parse(row.value)


def get_int_or_none_setting(db: Session, key: str, default: int | None) -> int | None:
    return get_setting(db, key, default, parse_int_or_none)


def get_int_setting(db: Session, key: str, default: int) -> int:
    return get_setting(db, key, default, int)


def get_float_setting(db: Session, key: str, default: float) -> float:
    return get_setting(db, key, default, _parse_float)


def get_bool_setting(db: Session, key: str, default: bool) -> bool:
    return get_setting(db, key, default, _parse_bool)


def set_setting(db: Session, key: str, value: object) -> None:
    row = db.get(SiteSetting, key)
    serialized = _serialize(value)
    if row is None:
        db.add(SiteSetting(key=key, value=serialized))
    else:
        row.value = serialized
    db.commit()
    _cache_invalidate()


# --- cached, session-free access for scraper code -------------------------------

_cache: dict[str, str] | None = None
_cache_loaded_at: float = 0.0
_CACHE_TTL_SECONDS = 30.0


def _cache_invalidate() -> None:
    global _cache
    _cache = None


def _load_cache() -> dict[str, str]:
    global _cache, _cache_loaded_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_loaded_at) < _CACHE_TTL_SECONDS:
        return _cache
    with SessionLocal() as db:
        rows = db.query(SiteSetting).all()
    _cache = {row.key: row.value for row in rows}
    _cache_loaded_at = now
    return _cache


def get_setting_cached(key: str, default: T, parse: Callable[[str], T]) -> T:
    raw = _load_cache().get(key)
    if raw is None:
        return default
    return parse(raw)
