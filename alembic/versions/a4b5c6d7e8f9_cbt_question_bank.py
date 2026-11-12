"""CBT question bank + pool-exam configuration.

Adds cbt_bank_questions (a tenant-scoped pool tagged by topic + difficulty) and
four columns on cbt_exams so an exam can draw a balanced subset from the bank
per sitting instead of using only its own authored questions.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cbt_bank_questions",
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("term_id", sa.String(length=36), nullable=True),
        sa.Column("topic", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("difficulty", sa.String(length=8), nullable=False, server_default="medium"),
        sa.Column("type", sa.String(length=12), nullable=False, server_default="single"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct", sa.JSON(), nullable=False),
        sa.Column("marks", sa.Float(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"]),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cbt_bank_questions", schema=None) as b:
        b.create_index(b.f("ix_cbt_bank_questions_school_id"), ["school_id"], unique=False)
        b.create_index(b.f("ix_cbt_bank_questions_subject_id"), ["subject_id"], unique=False)
        b.create_index(b.f("ix_cbt_bank_questions_difficulty"), ["difficulty"], unique=False)
        b.create_index("ix_cbt_bank_school_subject_diff",
                       ["school_id", "subject_id", "difficulty"], unique=False)

    with op.batch_alter_table("cbt_exams", schema=None) as b:
        b.add_column(sa.Column("shuffle_options", sa.Boolean(), nullable=False,
                               server_default=sa.true()))
        b.add_column(sa.Column("source", sa.String(length=10), nullable=False,
                               server_default="manual"))
        b.add_column(sa.Column("pool_size", sa.Integer(), nullable=False,
                               server_default="0"))
        b.add_column(sa.Column("difficulty_ratio", sa.JSON(), nullable=False,
                               server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("cbt_exams", schema=None) as b:
        b.drop_column("difficulty_ratio")
        b.drop_column("pool_size")
        b.drop_column("source")
        b.drop_column("shuffle_options")
    op.drop_table("cbt_bank_questions")
