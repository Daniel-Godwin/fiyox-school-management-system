"""Per-school admission number pattern.

Adds to `schools` the two fields that shape generated admission numbers:

  admission_prefix — e.g. "FAD"; null falls back to the school name's initials
  admission_pad    — serial width (3 -> 001, 4 -> 0001), default 3

Admission numbers are then generated as <prefix>/<2-digit year>/<serial>.
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schools", sa.Column("admission_prefix", sa.String(length=12), nullable=True))
    op.add_column("schools", sa.Column("admission_pad", sa.Integer(), nullable=False, server_default="3"))


def downgrade() -> None:
    op.drop_column("schools", "admission_pad")
    op.drop_column("schools", "admission_prefix")
