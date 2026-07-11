"""Async SQLAlchemy 2.0 engine + session factory."""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings

# For SQLite we relax same-thread checks; Postgres uses a real pool.
connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=not settings.is_sqlite,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
