"""Communication — school announcements targeted at role groups."""
import enum
from datetime import datetime
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class AnnouncementTarget(str, enum.Enum):
    ALL = "all"
    TEACHERS = "teachers"
    PARENTS = "parents"
    STUDENTS = "students"


class Announcement(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "announcements"

    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    target: Mapped[AnnouncementTarget] = mapped_column(String(10),
                                                       default=AnnouncementTarget.ALL)
    # null = draft (visible only to admins); set = visible to the target group
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
