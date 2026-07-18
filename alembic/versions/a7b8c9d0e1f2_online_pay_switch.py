"""Per-school online payments switch, default off.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
"""
import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schools", sa.Column(
        "online_payments_enabled", sa.Boolean(),
        nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("schools", "online_payments_enabled")
