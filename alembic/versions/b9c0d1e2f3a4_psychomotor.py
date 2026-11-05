"""Psychomotor skills on the report card.

Adds the school's configurable psychomotor trait list and the per-student
psychomotor ratings, parallel to the existing affective (character) ones:

  schools.psychomotor_traits  — JSON list of skill names
  term_results.psychomotor    — JSON {skill: rating 1-5}
"""
from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schools", sa.Column("psychomotor_traits", sa.JSON(), nullable=True))
    op.add_column("term_results", sa.Column("psychomotor", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("term_results", "psychomotor")
    op.drop_column("schools", "psychomotor_traits")
