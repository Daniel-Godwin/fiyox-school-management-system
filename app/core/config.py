"""Central configuration. Everything env-driven so the same image runs in dev and prod."""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Fiyox School Management System"
    ENV: str = "dev"  # dev | prod
    SECRET_KEY: str = "change-me-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    ALGORITHM: str = "HS256"

    # SQLite (async) for local dev; asyncpg Postgres (Neon) in prod.
    # You can paste Neon's URL as-is (postgres://...?sslmode=require) —
    # it is normalized to the async driver below.
    DATABASE_URL: str = "sqlite+aiosqlite:///./school.db"

    # In prod, set this to your Vercel URL (e.g. https://fiyox.vercel.app)
    # so browsers are only allowed to call the API from your frontend.
    FRONTEND_ORIGIN: str = "*"

    # Nigerian integrations (filled in later phases)
    PAYSTACK_SECRET_KEY: str | None = None
    TERMII_API_KEY: str | None = None
    TERMII_SENDER_ID: str = "Fiyox"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        """Accept URLs exactly as Neon/Render hand them out."""
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        # asyncpg uses `ssl=` rather than libpq's `sslmode=`
        v = v.replace("sslmode=require", "ssl=require")
        v = v.replace("channel_binding=require", "channel_binding=prefer")
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
