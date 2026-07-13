"""Result engine tables.

Design: raw ScoreEntry rows (one per component) are the source of truth teachers
edit. SubjectResult and TermResult are *computed* views produced by the compute
service — they hold totals, grades and positions so report cards render instantly.
"""
from sqlalchemy import (
    Boolean, Float, ForeignKey, Integer, JSON, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class AssessmentComponent(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A configurable column on the result sheet, e.g. 'Test 1' (max 10) or
    'Exam' (max 70). Each school defines its own; components should sum to 100."""
    __tablename__ = "assessment_components"

    name: Mapped[str] = mapped_column(String(60))
    max_score: Mapped[int] = mapped_column(Integer, default=10)
    is_exam: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)  # column order


class ScoreEntry(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One raw score: a student's mark on one component of one subject this term."""
    __tablename__ = "score_entries"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", "term_id", "component_id",
                         name="uq_score_unique"),
    )

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"))
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"))
    component_id: Mapped[str] = mapped_column(ForeignKey("assessment_components.id"))
    score: Mapped[float] = mapped_column(Float, default=0.0)


class SubjectResult(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Computed per student/subject/term."""
    __tablename__ = "subject_results"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", "term_id",
                         name="uq_subject_result"),
    )

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"))
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"))
    total: Mapped[float] = mapped_column(Float, default=0.0)
    grade: Mapped[str] = mapped_column(String(4), default="")
    remark: Mapped[str] = mapped_column(String(40), default="")
    subject_position: Mapped[int] = mapped_column(Integer, default=0)
    class_average: Mapped[float] = mapped_column(Float, default=0.0)
    # raw component scores kept for the report card grid, e.g. {"Test 1": 8, ...}
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)


class TermResult(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Computed per student/term — drives the report card summary + comments."""
    __tablename__ = "term_results"
    __table_args__ = (
        UniqueConstraint("student_id", "term_id", name="uq_term_result"),
    )

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"))
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"))
    grand_total: Mapped[float] = mapped_column(Float, default=0.0)
    average: Mapped[float] = mapped_column(Float, default=0.0)
    subjects_count: Mapped[int] = mapped_column(Integer, default=0)
    class_size: Mapped[int] = mapped_column(Integer, default=0)
    overall_position: Mapped[int] = mapped_column(Integer, default=0)
    # the arm's mean average this term — lets the report card say where the
    # student stands relative to the class, and drives comment generation
    class_average: Mapped[float] = mapped_column(Float, default=0.0)
    # affective/psychomotor domain, e.g. {"Punctuality": "A", "Neatness": "B"}
    affective: Mapped[dict] = mapped_column(JSON, default=dict)
    # generated on compute; set comments_edited when a human overrides them, so
    # recomputing the term never destroys what a teacher actually wrote
    form_teacher_comment: Mapped[str] = mapped_column(String(500), default="")
    principal_comment: Mapped[str] = mapped_column(String(500), default="")
    comments_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
