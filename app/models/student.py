"""Students, per-session enrollment (promotion history), guardians, teaching load."""
import enum
from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class Student(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "students"

    admission_number: Mapped[str] = mapped_column(String(40), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    other_names: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[Gender] = mapped_column(String(10))
    date_of_birth: Mapped["Date | None"] = mapped_column(Date)
    date_admitted: Mapped["Date | None"] = mapped_column(Date)
    # current placement (denormalised for fast lookups; history lives in Enrollment)
    current_arm_id: Mapped[str | None] = mapped_column(ForeignKey("class_arms.id"))
    # optional login account for the student
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Enrollment(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Which arm a student sat in for a given session — the promotion trail."""
    __tablename__ = "enrollments"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    session_id: Mapped[str] = mapped_column(ForeignKey("academic_sessions.id"))
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"))


class Guardian(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Links a parent User to a student (a parent can have several wards)."""
    __tablename__ = "guardians"

    parent_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    relationship: Mapped[str | None] = mapped_column(String(40))  # Father, Mother...


class TeachingAssignment(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A teacher teaches a subject to a specific arm — drives result-entry access."""
    __tablename__ = "teaching_assignments"

    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"))
