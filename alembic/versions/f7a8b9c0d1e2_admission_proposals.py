"""Admission decision proposals and principal approval.

Adds to `applicants` the fields that carry a proposed decision (set by
reconciliation, automatic or manual) and the principal's approval of it:

  proposed_status  — SHORTLISTED / ADMITTED / REJECTED, or null when none pending
  proposal_source  — "auto" | "manual"
  decided_by_id    — the user (principal) who approved the decision
  decided_at       — when it was approved

The applicant-facing `status` only changes on approval, so no decision reaches
the applicant before the principal signs off.
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "c3d4e5f6a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FK columns are added as plain nullable String — SQLite cannot create a
    # standalone foreign key, and the app resolves the reference in code (the
    # pattern used across this project's migrations).
    op.add_column("applicants", sa.Column("proposed_status", sa.String(length=12), nullable=True))
    op.add_column("applicants", sa.Column("proposal_source", sa.String(length=10), nullable=True))
    op.add_column("applicants", sa.Column("decided_by_id", sa.String(length=36), nullable=True))
    op.add_column("applicants", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("applicants", "decided_at")
    op.drop_column("applicants", "decided_by_id")
    op.drop_column("applicants", "proposal_source")
    op.drop_column("applicants", "proposed_status")
