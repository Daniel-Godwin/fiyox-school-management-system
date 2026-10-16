"""Result approval workflow — results must be approved before publishing.

Adds an approval lifecycle to term_results: draft -> submitted -> approved,
after which a result may be published to parents. Existing published results
are treated as already approved so nothing that parents can currently see
disappears.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # per-school switch: when off (default), publishing works as before
    op.add_column("schools", sa.Column(
        "result_approval_required", sa.Boolean(),
        nullable=False, server_default=sa.false()))

    op.add_column("term_results", sa.Column(
        "approval_status", sa.String(length=12),
        nullable=False, server_default="draft"))
    op.add_column("term_results", sa.Column(
        "approved_by", sa.String(length=36), nullable=True))
    op.add_column("term_results", sa.Column(
        "approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("term_results", sa.Column(
        "approval_note", sa.String(length=300),
        nullable=False, server_default=""))

    # anything already published was, in effect, already approved — keep it so
    op.execute(
        "UPDATE term_results SET approval_status = 'approved' "
        "WHERE is_published = true")


def downgrade() -> None:
    op.drop_column("term_results", "approval_note")
    op.drop_column("term_results", "approved_at")
    op.drop_column("term_results", "approved_by")
    op.drop_column("term_results", "approval_status")
    op.drop_column("schools", "result_approval_required")
