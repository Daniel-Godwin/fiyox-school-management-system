"""Force a password change off the admin-issued temporary one.

Adds users.must_change_password. New accounts and admin password resets set it
True; the user's own change-password clears it. Existing non-super-admin users
are flagged True so current pilot staff are prompted to replace the temporary
password they were issued.
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    # flag everyone currently on a temporary password (everyone but the platform
    # owner) so the dashboard prompts them on next sign-in
    users = sa.table(
        "users",
        sa.column("must_change_password", sa.Boolean),
        sa.column("role", sa.String),
    )
    op.execute(
        users.update()
        .where(users.c.role != "super_admin")
        .values(must_change_password=True)
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
