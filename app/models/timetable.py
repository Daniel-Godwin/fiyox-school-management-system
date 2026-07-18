"""Timetable — the week's lesson grid.

Two pieces:

* **Period** — a row of the timetable: "Period 1, 08:00–08:40". Defined once per
  school, shared by every class. Break and assembly are periods too (is_break),
  so the printed timetable looks like the one on the staffroom wall.

* **Lesson** — one cell: on Monday, in Period 2, JSS1 A does Mathematics with
  Mr Bello. Uniqueness is enforced where it matters: an arm cannot be in two
  places at once, and a teacher cannot be in two classrooms at once.
"""
import enum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Weekday(str, enum.Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"


WEEKDAY_ORDER = [d.value for d in Weekday]


class Period(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A time row on the timetable, e.g. 'Period 1' 08:00-08:40, or 'Break'."""
    __tablename__ = "periods"
    # uniqueness applies to LIVE rows only: a deleted period must not block a
    # new one from taking its row number (partial unique index, both dialects)
    __table_args__ = (
        Index("uq_period_sequence_active", "school_id", "sequence",
              unique=True,
              sqlite_where=text("deleted_at IS NULL"),
              postgresql_where=text("deleted_at IS NULL")),
    )

    name: Mapped[str] = mapped_column(String(40))
    sequence: Mapped[int] = mapped_column(Integer, default=0)   # row order
    start_time: Mapped["Time | None"] = mapped_column(Time)
    end_time: Mapped["Time | None"] = mapped_column(Time)
    # break / assembly / lunch: shown on the grid, but no lesson is scheduled
    is_break: Mapped[bool] = mapped_column(Boolean, default=False)


class Lesson(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One cell: this arm, this day, this period — this subject, this teacher."""
    __tablename__ = "lessons"
    __table_args__ = (
        # an arm cannot be in two LIVE lessons at the same time; removed
        # lessons must not haunt the slot (partial unique index)
        Index("uq_lesson_arm_slot_active", "school_id", "arm_id", "day",
              "period_id", unique=True,
              sqlite_where=text("deleted_at IS NULL"),
              postgresql_where=text("deleted_at IS NULL")),
    )

    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"), index=True)
    day: Mapped[Weekday] = mapped_column(String(10), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    # optional: a slot can be timetabled before a teacher is assigned to it
    teacher_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    room: Mapped[str | None] = mapped_column(String(40))
