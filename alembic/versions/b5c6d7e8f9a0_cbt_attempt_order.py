"""Per-attempt question + option order (randomization snapshot).

Adds cbt_attempts.question_order and option_orders so each sitting freezes its
own unique, shuffled question set and option display order — stable across a
refresh or device switch, and the source of truth for grading.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cbt_attempts", schema=None) as b:
        b.add_column(sa.Column("question_order", sa.JSON(), nullable=False,
                               server_default="[]"))
        b.add_column(sa.Column("option_orders", sa.JSON(), nullable=False,
                               server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("cbt_attempts", schema=None) as b:
        b.drop_column("option_orders")
        b.drop_column("question_order")
