"""Nigerian academic structure: 3-term sessions, nursery/primary/JSS/SSS
classes, arms, subjects."""
import enum
import re
from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class ClassCategory(str, enum.Enum):
    NURSERY = "nursery"   # Creche, Playgroup, Pre-Nursery, Nursery, KG, Reception
    PRIMARY = "primary"   # Primary/Basic 1-6
    JUNIOR = "junior"     # JSS1-3 (Basic 7-9)
    SENIOR = "senior"     # SS1-3


# Banded level_order so a full ladder sorts correctly across levels:
#   nursery 1-9  <  primary 10-19  <  junior 20-29  <  senior 30-39
# The exact value within a band only needs to order classes in that band; ties
# fall back to the class name wherever level_order is used (promotion, reports).
_NURSERY = 1
_PRIMARY = 10
_JUNIOR = 20
_SENIOR = 30


def infer_level(class_name: str) -> tuple[ClassCategory, int]:
    """Guess (category, level_order) from a Nigerian class name.

    Recognises the common pre-primary, primary and secondary namings, including
    the UBE "Basic" scale (Basic 1-6 = primary, Basic 7-9 = JSS). Unknown names
    fall back to junior, preserving the previous default.
    """
    up = (class_name or "").upper().strip()
    digits = re.findall(r"\d+", up)
    n = int(digits[0]) if digits else 0

    # pre-primary (ordered: creche < playgroup/pre < kg/reception < nursery)
    if "CRECHE" in up or "CRÈCHE" in up:
        return ClassCategory.NURSERY, _NURSERY
    if "PLAYGROUP" in up or up.startswith("PRE"):
        return ClassCategory.NURSERY, _NURSERY + 1
    if "NURSERY" in up or up.startswith("NUR"):
        return ClassCategory.NURSERY, _NURSERY + 2 + n
    # KG / reception is the final pre-primary year, just before Primary 1
    if up.startswith("KG") or "KINDERGARTEN" in up or "RECEPTION" in up:
        return ClassCategory.NURSERY, _NURSERY + 6 + n

    # UBE "Basic" scale spans primary (1-6) and junior secondary (7-9)
    if "BASIC" in up and n:
        if n <= 6:
            return ClassCategory.PRIMARY, _PRIMARY + n
        return ClassCategory.JUNIOR, _JUNIOR + (n - 6)

    # senior secondary (check SSS/SS before the generic 'S')
    if up.startswith("SSS") or up.startswith("SS") or "SENIOR" in up:
        return ClassCategory.SENIOR, _SENIOR + n
    # junior secondary
    if up.startswith("JSS") or up.startswith("JS") or "JUNIOR" in up:
        return ClassCategory.JUNIOR, _JUNIOR + n
    # primary
    if up.startswith("PRIMARY") or up.startswith("PRY") or up.startswith("PRI") \
            or up.startswith("GRADE") or up.startswith("CLASS") or up.startswith("P"):
        return ClassCategory.PRIMARY, _PRIMARY + n

    return ClassCategory.JUNIOR, _JUNIOR + n


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
