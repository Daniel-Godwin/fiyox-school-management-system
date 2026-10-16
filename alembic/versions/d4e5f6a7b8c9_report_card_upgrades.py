"""Report-card upgrades.

Adds:
* subject_results.class_highest / class_lowest — the class spread per subject,
  shown on the report card (0 on older rows until a class is recomputed).
* schools.affective_traits — the behaviour traits a school rates 1-5.
* comment_bank — reusable, average-banded report-card comments.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subject_results", sa.Column(
        "class_highest", sa.Float(), nullable=False, server_default="0"))
    op.add_column("subject_results", sa.Column(
        "class_lowest", sa.Float(), nullable=False, server_default="0"))

    op.add_column("schools", sa.Column(
        "affective_traits", sa.JSON(), nullable=True))

    op.create_table(
        "comment_bank",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("min_average", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_average", sa.Float(), nullable=False, server_default="100"),
        sa.Column("audience", sa.String(length=16), nullable=False,
                  server_default="form_teacher"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comment_bank_school_id", "comment_bank", ["school_id"])


def downgrade() -> None:
    op.drop_index("ix_comment_bank_school_id", table_name="comment_bank")
    op.drop_table("comment_bank")
    op.drop_column("schools", "affective_traits")
    op.drop_column("subject_results", "class_lowest")
    op.drop_column("subject_results", "class_highest")
