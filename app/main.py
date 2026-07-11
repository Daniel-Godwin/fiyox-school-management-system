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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten per-tenant in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": "0.1.0", "docs": "/docs"}
