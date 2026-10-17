"""CBT module — computer-based testing (exams, questions, attempts).

Adds three tenant-scoped tables:
  * cbt_exams     — a test for one subject + arm + term, with a lifecycle
                    (draft -> published -> closed) and scheduling window.
  * cbt_questions — objective questions (single/multiple/boolean/short) whose
                    answer key is auto-graded on submit.
  * cbt_attempts  — one student's sitting, graded the moment it is submitted.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cbt_exams",
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("arm_id", sa.String(length=36), nullable=False),
        sa.Column("term_id", sa.String(length=36), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_results_immediately", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_marks", sa.Float(), nullable=False, server_default="0"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["arm_id"], ["class_arms.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"]),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cbt_exams", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cbt_exams_school_id"), ["school_id"], unique=False)

    op.create_table(
        "cbt_questions",
        sa.Column("exam_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False, server_default="single"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct", sa.JSON(), nullable=True),
        sa.Column("marks", sa.Float(), nullable=False, server_default="1"),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["cbt_exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cbt_questions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cbt_questions_exam_id"), ["exam_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cbt_questions_school_id"), ["school_id"], unique=False)

    op.create_table(
        "cbt_attempts",
        sa.Column("exam_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="in_progress"),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("auto_submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["cbt_exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_id", "student_id", "attempt_no", name="uq_cbt_attempt"),
    )
    with op.batch_alter_table("cbt_attempts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cbt_attempts_exam_id"), ["exam_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cbt_attempts_student_id"), ["student_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cbt_attempts_school_id"), ["school_id"], unique=False)


def downgrade() -> None:
    op.drop_table("cbt_attempts")
    op.drop_table("cbt_questions")
    op.drop_table("cbt_exams")
