"""Automatic parent notifications flag.

Adds schools.parent_notifications_enabled (default true). When set, publishing a
term result or recording a fee payment sends the student's parent an SMS/email.
On by default so a school is notified of the new behaviour by seeing messages,
and can switch it off from settings.
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schools",
        sa.Column("parent_notifications_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("schools", "parent_notifications_enabled")
