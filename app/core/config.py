"""Central configuration. Everything env-driven so the same image runs in dev and prod."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Fiyox School Management System"
    ENV: str = "dev"  # dev | prod
    SECRET_KEY: str = "change-me-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    ALGORITHM: str = "HS256"

    # SQLite (async) for local dev; asyncpg Postgres (Neon) in prod.
    # e.g. postgresql+asyncpg://user:pass@host/db
    DATABASE_URL: str = "sqlite+aiosqlite:///./school.db"

    # Nigerian integrations (filled in later phases)
    PAYSTACK_SECRET_KEY: str | None = None
    TERMII_API_KEY: str | None = None
    TERMII_SENDER_ID: str = "Fiyox"

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
