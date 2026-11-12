"""CBT anti-cheating: proctoring config, violation count, and violation log.

Adds cbt_exams.proctored + max_violations, cbt_attempts.violation_count, and the
cbt_violations table (one row per tab-switch / visibility event during a sitting).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cbt_exams", schema=None) as b:
        b.add_column(sa.Column("proctored", sa.Boolean(), nullable=False,
                               server_default=sa.false()))
        b.add_column(sa.Column("max_violations", sa.Integer(), nullable=False,
                               server_default="3"))
    with op.batch_alter_table("cbt_attempts", schema=None) as b:
        b.add_column(sa.Column("violation_count", sa.Integer(), nullable=False,
                               server_default="0"))

    op.create_table(
        "cbt_violations",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default="tab_switch"),
        sa.Column("detail", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("school_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["cbt_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cbt_violations", schema=None) as b:
        b.create_index(b.f("ix_cbt_violations_school_id"), ["school_id"], unique=False)
        b.create_index(b.f("ix_cbt_violations_attempt_id"), ["attempt_id"], unique=False)


def downgrade() -> None:
    op.drop_table("cbt_violations")
    with op.batch_alter_table("cbt_attempts", schema=None) as b:
        b.drop_column("violation_count")
    with op.batch_alter_table("cbt_exams", schema=None) as b:
        b.drop_column("max_violations")
        b.drop_column("proctored")
