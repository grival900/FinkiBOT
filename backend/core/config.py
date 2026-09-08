from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://finkibot:finkibot@localhost:5432/finkibot"

    gemini_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"

    embedding_model_name: str = "BAAI/bge-m3"

    # Chat retrieval: a retrieved chunk whose cosine similarity to the question is
    # below this is dropped before it can reach the model's context or the cited
    # source list. Measured on this corpus with bge-m3: a genuinely on-topic chunk
    # scores ~0.45-0.8, an incidental keyword overlap (a name mentioned in passing on
    # an unrelated page) ~0.33-0.40 — so 0.40 clears the noise while keeping real
    # syllabus/bio prose, which sits lower than a short exact-title card. Tunable at
    # runtime without a redeploy via a `chat_min_score` row in the site_settings table.
    chat_min_score: float = 0.40

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "FinkiBOT <noreply@finkibot.local>"
    smtp_use_tls: bool = False

    app_base_url: str = "http://localhost:8000"

    scrape_user_agent: str = "FinkiBOT/0.1"
    scrape_request_delay_seconds: float = 1.0
    scrape_announcement_limit: int | None = None
    # Caps how many official course syllabus pages `official.subjects` fetches per run
    # (one request each, no bulk endpoint — see scrapers/official_site/subjects.py).
    # None = fetch all of them.
    scrape_subjects_limit: int | None = 30

    @field_validator("scrape_announcement_limit", "scrape_subjects_limit", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        return None if value == "" else value

    frontend_origin: str = "http://localhost:8080"

    enable_scheduler: bool = True
    scheduler_interval_minutes: int = 60
    # Weekly by default — slow-cadence scrapers (official course syllabi, professor
    # profiles, recordings pages) cost 100+ rate-limited requests per pass but rarely
    # change; no need to pay that on the same hourly cadence as announcements.
    scheduler_slow_interval_minutes: int = 10080

    # Required, no default — this signs auth tokens, so a shared/hardcoded default
    # would let anyone forge a valid admin session. Generate one with:
    # python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret_key: str
    jwt_expires_minutes: int = 1440  # 24h


@lru_cache
def get_settings() -> Settings:
    return Settings()
