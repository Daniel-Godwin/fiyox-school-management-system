"""The tenant (School) and platform/tenant Users with RBAC roles."""
import enum
from sqlalchemy import Boolean, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin


class Role(str, enum.Enum):
    SUPER_ADMIN = "super_admin"      # you: the platform owner, no school
    SCHOOL_ADMIN = "school_admin"    # proprietor / principal
    BURSAR = "bursar"                # fees & payments
    TEACHER = "teacher"              # subject and/or form teacher
    STUDENT = "student"
    PARENT = "parent"                # guardian, read-only on their ward(s)


# Sensible Nigerian default grading: CA 40 + Exam 60, WAEC-style bands.
DEFAULT_GRADING = {
    "ca_weight": 40,
    "exam_weight": 60,
    "bands": [
        {"min": 75, "grade": "A1", "remark": "Excellent"},
        {"min": 70, "grade": "B2", "remark": "Very Good"},
        {"min": 65, "grade": "B3", "remark": "Good"},
        {"min": 60, "grade": "C4", "remark": "Credit"},
        {"min": 55, "grade": "C5", "remark": "Credit"},
        {"min": 50, "grade": "C6", "remark": "Credit"},
        {"min": 45, "grade": "D7", "remark": "Pass"},
        {"min": 40, "grade": "E8", "remark": "Pass"},
        {"min": 0, "grade": "F9", "remark": "Fail"},
    ],
}


class School(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "schools"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # login subdomain / code, e.g. "gss-ikeja" -> gss-ikeja.fiyox.ng
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(300))
    state: Mapped[str | None] = mapped_column(String(60))
    logo_url: Mapped[str | None] = mapped_column(String(400))
    primary_color: Mapped[str] = mapped_column(String(9), default="#0B1F3A")
    # per-school configurable grading & policies
    grading_config: Mapped[dict] = mapped_column(JSON, default=DEFAULT_GRADING)
    withhold_results_on_debt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    # email is unique *within* a school; super_admin has school_id = None
    __table_args__ = (UniqueConstraint("school_id", "email", name="uq_user_school_email"),)

    # nullable because the platform super_admin belongs to no school
    school_id: Mapped[str | None] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(String(20), default=Role.STUDENT)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
