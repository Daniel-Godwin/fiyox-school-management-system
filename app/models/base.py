"""Declarative base + reusable mixins.

TenantMixin is the heart of multi-tenancy: every school-owned row carries a
school_id. Combined with the tenant dependency, this guarantees one school can
never read or write another school's data.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    # Soft delete: records are never hard-destroyed; queries filter deleted_at IS NULL.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    # Authorship for accountability (user ids); populated on writes.
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class TenantMixin:
    """Attach to every table that belongs to a specific school."""

    school_id: Mapped[str] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True, nullable=False
    )
