"""Demo requests from the public landing page.

Platform-level (not tied to any school): a prospective school fills in the
"Request a demo" form and the platform owner sees the request in their console.
"""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class DemoRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "demo_requests"

    school_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    handled: Mapped[bool] = mapped_column(Boolean, default=False)
