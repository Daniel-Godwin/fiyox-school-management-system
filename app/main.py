"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine
from app.models import Base
from app.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: auto-create tables on SQLite. In prod use Alembic migrations.
    if settings.is_sqlite:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

def _cors_origins() -> list[str]:
    """FRONTEND_ORIGIN may hold one origin or a comma-separated list.
    Trailing slashes are stripped — 'https://x.vercel.app/' and
    'https://x.vercel.app' must both work, since a stray slash would
    otherwise silently break every browser preflight.
    """
    raw = (settings.FRONTEND_ORIGIN or "*").strip()
    if raw == "*":
        return ["*"]
    origins = []
    for part in raw.split(","):
        o = part.strip().rstrip("/")
        if o:
            origins.append(o)
    return origins or ["*"]


_origins = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Vercel gives every deployment a preview URL; allow those too so testing
    # from a preview build does not fail with an opaque "Failed to fetch".
    allow_origin_regex=None if _origins == ["*"] else r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],   # so the browser can name PDFs
    max_age=3600,                              # cache preflights for an hour
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": "0.1.0", "docs": "/docs"}
