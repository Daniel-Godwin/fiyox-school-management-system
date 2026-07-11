"""Audit trail — the 'who changed this result?' accountability table.

Deliberately minimal and append-only: no soft delete, no updates. One row per
sensitive action, capturing the actor, the target row, and old→new values.
"""
from datetime import datetime, timezone
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"

    school_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(30))          # create | update | delete | publish
    table_name: Mapped[str] = mapped_column(String(60), index=True)
    record_id: Mapped[str | None] = mapped_column(String(36), index=True)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)  # {field: {old, new}}
    ip_address: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
