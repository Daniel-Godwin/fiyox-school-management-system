"""Computer-Based Testing (CBT) tables.

A teacher (or admin) authors a CBTExam for one subject + arm + term, adds
CBTQuestions, then publishes it. Students in that arm sit the exam within its
open window; each sitting is a CBTAttempt whose objective answers are graded
automatically the moment it is submitted.

Statuses are plain strings (not DB enums), matching the result-approval design:
new states never need a migration, only app-level validation.

Question types (all auto-gradable, so a sitting scores instantly):
    single    - one correct option  (radio)
    multiple  - several correct options, all-or-nothing (checkboxes)
    boolean   - True / False
    short      - short typed answer, matched case/space-insensitively against
                a list of accepted answers
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin

# exam lifecycle
EXAM_DRAFT = "draft"
EXAM_PUBLISHED = "published"
EXAM_CLOSED = "closed"
EXAM_STATUSES = (EXAM_DRAFT, EXAM_PUBLISHED, EXAM_CLOSED)

# question types
Q_SINGLE = "single"
Q_MULTIPLE = "multiple"
Q_BOOLEAN = "boolean"
Q_SHORT = "short"
QUESTION_TYPES = (Q_SINGLE, Q_MULTIPLE, Q_BOOLEAN, Q_SHORT)

# attempt lifecycle
ATTEMPT_IN_PROGRESS = "in_progress"
ATTEMPT_SUBMITTED = "submitted"


class CBTExam(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One computer-based test for a subject + arm + term."""
    __tablename__ = "cbt_exams"

    title: Mapped[str] = mapped_column(String(160))
    instructions: Mapped[str] = mapped_column(Text, default="")
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"))
    arm_id: Mapped[str] = mapped_column(ForeignKey("class_arms.id"))
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"))
    # optional link to a result-sheet column (Test 1, Exam, ...). When set, each
    # sitting's score is scaled to that component's max and written into the
    # student's ScoreEntry on submit, so CBT results flow into the report card.
    # Null means "practice only — does not count towards results".
    component_id: Mapped[str | None] = mapped_column(
        ForeignKey("assessment_components.id"))

    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # scheduling window — null means "available as soon as published"
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True)
    # does the student see their score the moment they submit?
    show_results_immediately: Mapped[bool] = mapped_column(Boolean, default=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)

    # cached on publish so lists/results need not re-sum the questions
    total_marks: Mapped[float] = mapped_column(Float, default=0.0)
    question_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(12), default=EXAM_DRAFT)


class CBTQuestion(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A single question on an exam.

    `options` holds [{"id": "a", "text": "..."}, ...] for single/multiple;
    boolean and short store no options.
    `correct` holds the answer key, shape depending on type:
        single   -> option id            e.g. "b"
        multiple -> list of option ids    e.g. ["a", "c"]
        boolean  -> bool                  e.g. true
        short    -> list of accepted str  e.g. ["8", "eight"]
    The answer key is NEVER sent to a student while they sit the exam.
    """
    __tablename__ = "cbt_questions"

    exam_id: Mapped[str] = mapped_column(
        ForeignKey("cbt_exams.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(12), default=Q_SINGLE)
    text: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct: Mapped[dict | list | str | bool] = mapped_column(JSON, default=dict)
    marks: Mapped[float] = mapped_column(Float, default=1.0)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class CBTAttempt(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One student's sitting of one exam. Auto-graded on submit."""
    __tablename__ = "cbt_attempts"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "attempt_no",
                         name="uq_cbt_attempt"),
    )

    exam_id: Mapped[str] = mapped_column(
        ForeignKey("cbt_exams.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # the moment this sitting must end by (started_at + duration, capped at
    # closes_at). Stored so a resumed sitting keeps its original deadline.
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(12), default=ATTEMPT_IN_PROGRESS)
    # {question_id: answer} — answer shape mirrors a question's `correct`
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    # per-question outcome snapshot at grading: {question_id: {"correct":bool,"marks":n}}
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=0.0)
    # true when submitted because the timer ran out rather than by the student
    auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
