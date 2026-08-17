from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://finkibot:finkibot@localhost:5432/finkibot"

    gemini_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"

    embedding_model_name: str = "BAAI/bge-m3"

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

    @field_validator("scrape_announcement_limit", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        return None if value == "" else value

    frontend_origin: str = "http://localhost:5173"

    enable_scheduler: bool = True
    scheduler_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
