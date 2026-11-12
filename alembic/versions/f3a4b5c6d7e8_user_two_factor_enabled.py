"""Opt-in two-factor authentication flag.

Adds users.two_factor_enabled (default false). When set, login requires a
one-time code emailed to the user as a second step.
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("two_factor_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "two_factor_enabled")
