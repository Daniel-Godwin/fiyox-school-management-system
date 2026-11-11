"""Retire the user accounts of already-offboarded schools.

Offboarding historically only deactivated a school's users (is_active=False)
while leaving their rows live (deleted_at NULL). Those lingering rows still
matched by email at login and still reserved their email address. This one-off
data migration finishes the job for schools that were offboarded before the fix:
every still-live user of a soft-deleted school is itself soft-deleted, so its
email no longer shadows a live account and is freed for reuse. Rows are kept
(soft delete) for audit and possible reactivation.
"""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    users = sa.table(
        "users",
        sa.column("deleted_at", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean),
        sa.column("school_id", sa.String),
    )
    schools = sa.table(
        "schools",
        sa.column("id", sa.String),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    offboarded = sa.select(schools.c.id).where(schools.c.deleted_at.isnot(None))
    op.execute(
        users.update()
        .where(users.c.deleted_at.is_(None))
        .where(users.c.school_id.in_(offboarded))
        .values(deleted_at=datetime.now(timezone.utc), is_active=False)
    )


def downgrade() -> None:
    # data-only cleanup; there is no safe way to tell which rows this set, so the
    # downgrade is intentionally a no-op (the schema is unchanged either way)
    pass
