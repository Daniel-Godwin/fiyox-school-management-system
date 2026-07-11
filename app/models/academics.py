"""Nigerian academic structure: 3-term sessions, JSS/SSS classes, arms, subjects."""
import enum
from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class ClassCategory(str, enum.Enum):
    JUNIOR = "junior"   # JSS1-3
    SENIOR = "senior"   # SS1-3


class TermName(str, enum.Enum):
    FIRST = "first"
    SECOND = "second"
    THIRD = "third"


class AcademicSession(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """e.g. '2025/2026'."""
    __tablename__ = "academic_sessions"

    name: Mapped[str] = mapped_column(String(20))
    start_date: Mapped["Date | None"] = mapped_column(Date)
    end_date: Mapped["Date | None"] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class Term(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "terms"

    session_id: Mapped[str] = mapped_column(ForeignKey("academic_sessions.id"))
    name: Mapped[TermName] = mapped_column(String(10))
    start_date: Mapped["Date | None"] = mapped_column(Date)
    end_date: Mapped["Date | None"] = mapped_column(Date)
    next_term_begins: Mapped["Date | None"] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class SchoolClass(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A grade level, e.g. 'JSS1', 'SS2'."""
    __tablename__ = "school_classes"

    name: Mapped[str] = mapped_column(String(20))
    category: Mapped[ClassCategory] = mapped_column(String(10))
    level_order: Mapped[int] = mapped_column(Integer, default=0)  # for promotion


class ClassArm(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A specific stream, e.g. JSS1 'A'. Has a form (class) teacher."""
    __tablename__ = "class_arms"

    class_id: Mapped[str] = mapped_column(ForeignKey("school_classes.id"))
    name: Mapped[str] = mapped_column(String(20))  # A, B, Gold, Silver...
    form_teacher_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Subject(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(20))
    # which section this subject applies to
    category: Mapped[ClassCategory | None] = mapped_column(String(10))
    is_core: Mapped[bool] = mapped_column(Boolean, default=True)
