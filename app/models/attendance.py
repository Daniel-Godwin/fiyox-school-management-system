"""Attendance — one row per student per school day.

Marking is an upsert: re-marking the same day updates the row (and the change
is audited old→new), so a teacher can correct a mistake without duplicates.
"""
import enum
from datetime import date
from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class Attendance(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "date", name="uq_attendance_student_day"),
    )

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(String(10))
    remark: Mapped[str | None] = mapped_column(String(200))
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
