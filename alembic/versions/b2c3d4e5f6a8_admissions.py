"""Online admissions — applicants and entrance tests.

Adds three tenant-scoped tables:
  * applicants         — one public application to a school, with its lifecycle
                         and optional entrance-test result.
  * admission_tests    — a school's optional entrance test.
  * admission_questions — objective questions for an entrance test (same shape
                         the CBT grader reads).

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applicants",
        sa.Column("application_number", sa.String(length=40), nullable=False),
        sa.Column("access_code", sa.String(length=12), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("other_names", sa.String(length=100), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("applying_class_id", sa.String(length=36), nullable=False),
        sa.Column("previous_school", sa.String(length=200), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("guardian_name", sa.String(length=160), nullable=False),
        sa.Column("guardian_phone", sa.String(length=40), nullable=False),
        sa.Column("guardian_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="applied"),
        sa.Column("status_note", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("entrance_score", sa.Float(), nullable=True),
        sa.Column("entrance_max", sa.Float(), nullable=True),
        sa.Column("entrance_taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entrance_answers", sa.JSON(), nullable=False),
        sa.Column("admitted_student_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["applying_class_id"], ["school_classes.id"]),
        sa.ForeignKeyConstraint(["admitted_student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("applicants", schema=None) as b:
        b.create_index(b.f("ix_applicants_application_number"), ["application_number"], unique=False)
        b.create_index(b.f("ix_applicants_school_id"), ["school_id"], unique=False)

    op.create_table(
        "admission_tests",
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("applying_class_id", sa.String(length=36), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("total_marks", sa.Float(), nullable=False, server_default="0"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["applying_class_id"], ["school_classes.id"]),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("admission_tests", schema=None) as b:
        b.create_index(b.f("ix_admission_tests_school_id"), ["school_id"], unique=False)

    op.create_table(
        "admission_questions",
        sa.Column("test_id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["test_id"], ["admission_tests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("admission_questions", schema=None) as b:
        b.create_index(b.f("ix_admission_questions_test_id"), ["test_id"], unique=False)
        b.create_index(b.f("ix_admission_questions_school_id"), ["school_id"], unique=False)


def downgrade() -> None:
    op.drop_table("admission_questions")
    op.drop_table("admission_tests")
    op.drop_table("applicants")
