"""Online admissions.

A prospective parent fills in a public application form on the school's own
admissions link (no login). The application becomes an Applicant the school
reviews in its dashboard, optionally with an auto-graded entrance test the
applicant sits with a code. When the school accepts one, a single action turns
the Applicant into a full Student record.

Statuses are plain strings (like the CBT and result-approval designs): new
states never need a migration.

The entrance test reuses the CBT grading service — AdmissionQuestion carries the
same shape (type, options, correct, marks) the grader reads, so no logic is
duplicated.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Date, Float, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin

# applicant lifecycle
APPLIED = "applied"
SHORTLISTED = "shortlisted"
ADMITTED = "admitted"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"
APPLICANT_STATUSES = (APPLIED, SHORTLISTED, ADMITTED, REJECTED, WITHDRAWN)

# a reconciliation may propose one of these; the principal approves to finalise
PROPOSABLE = (SHORTLISTED, ADMITTED, REJECTED)
SRC_AUTO = "auto"
SRC_MANUAL = "manual"


class Applicant(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One application to a school."""
    __tablename__ = "applicants"

    # human-friendly, unique within the school, e.g. APP/26/0001
    application_number: Mapped[str] = mapped_column(String(40), index=True)
    # the applicant proves ownership of their application with this short code
    access_code: Mapped[str] = mapped_column(String(12))

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    other_names: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[str] = mapped_column(String(10))
    date_of_birth: Mapped["Date | None"] = mapped_column(Date)

    # the class they are applying into
    applying_class_id: Mapped[str] = mapped_column(ForeignKey("school_classes.id"))
    previous_school: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))

    guardian_name: Mapped[str] = mapped_column(String(160))
    guardian_phone: Mapped[str] = mapped_column(String(40))
    guardian_email: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(12), default=APPLIED)
    status_note: Mapped[str] = mapped_column(String(300), default="")

    # a decision proposed by reconciliation (auto or manual) that is waiting for
    # the principal to approve. The applicant-facing `status` only changes on
    # approval, so no decision reaches the applicant before the principal signs
    # off. One of SHORTLISTED / ADMITTED / REJECTED, or null when none pending.
    proposed_status: Mapped[str | None] = mapped_column(String(12))
    proposal_source: Mapped[str | None] = mapped_column(String(10))  # "auto" | "manual"
    # who approved the decision, and when (the principal)
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # entrance test result (null until sat)
    entrance_score: Mapped[float | None] = mapped_column(Float)
    entrance_max: Mapped[float | None] = mapped_column(Float)
    entrance_taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entrance_answers: Mapped[dict] = mapped_column(JSON, default=dict)

    # set when admitted — links to the Student record created from this application
    admitted_student_id: Mapped[str | None] = mapped_column(ForeignKey("students.id"))


class AdmissionTest(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A school's entrance test. Optional — a school may admit without one.

    `applying_class_id` null means the test applies to every applying class;
    set it to target one class (e.g. an SS1 entrance test).
    """
    __tablename__ = "admission_tests"

    title: Mapped[str] = mapped_column(String(160))
    instructions: Mapped[str] = mapped_column(Text, default="")
    applying_class_id: Mapped[str | None] = mapped_column(ForeignKey("school_classes.id"))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True)
    total_marks: Mapped[float] = mapped_column(Float, default=0.0)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    # only an active test is served to applicants
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class AdmissionQuestion(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A question on an entrance test — same shape the CBT grader reads."""
    __tablename__ = "admission_questions"

    test_id: Mapped[str] = mapped_column(
        ForeignKey("admission_tests.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(12), default="single")
    text: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct: Mapped[dict | list | str | bool] = mapped_column(JSON, default=dict)
    marks: Mapped[float] = mapped_column(Float, default=1.0)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
