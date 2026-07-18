"""Timetable uniqueness applies to live rows only.

The original UNIQUE constraints on lessons (arm+day+period) and periods
(sequence) counted soft-deleted rows, so a removed lesson blocked its slot
forever and a deleted period's row number could never be reused. Replaced with
partial unique indexes over rows WHERE deleted_at IS NULL — the clash rules
stay absolute for the living timetable, and the dead stop haunting it.

Revision ID: f1a2b3c4d5e6
Revises: ead0ba9e1b49
"""
import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "ead0ba9e1b49"
branch_labels = None
depends_on = None

WHERE_LIVE = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    with op.batch_alter_table("lessons") as b:
        b.drop_constraint("uq_lesson_arm_slot", type_="unique")
    with op.batch_alter_table("periods") as b:
        b.drop_constraint("uq_period_sequence", type_="unique")

    op.create_index("uq_lesson_arm_slot_active", "lessons",
                    ["school_id", "arm_id", "day", "period_id"], unique=True,
                    sqlite_where=WHERE_LIVE, postgresql_where=WHERE_LIVE)
    op.create_index("uq_period_sequence_active", "periods",
                    ["school_id", "sequence"], unique=True,
                    sqlite_where=WHERE_LIVE, postgresql_where=WHERE_LIVE)


def downgrade() -> None:
    op.drop_index("uq_lesson_arm_slot_active", table_name="lessons")
    op.drop_index("uq_period_sequence_active", table_name="periods")
    with op.batch_alter_table("lessons") as b:
        b.create_unique_constraint("uq_lesson_arm_slot",
                                   ["school_id", "arm_id", "day", "period_id"])
    with op.batch_alter_table("periods") as b:
        b.create_unique_constraint("uq_period_sequence", ["school_id", "sequence"])
