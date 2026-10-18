"""CBT -> assessment component link.

Lets a CBT be tied to a result-sheet column (Test 1, Exam, ...). When set, each
sitting's score is scaled to that component's max and written into the student's
ScoreEntry on submit, so CBT results feed the report card automatically. Null =
practice only.

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # plain nullable column (matches how other FK columns are added in this
    # project's migrations, e.g. term_results.approved_by); the ORM model
    # carries the ForeignKey for dev create_all, and the route validates the
    # component belongs to the school.
    op.add_column("cbt_exams", sa.Column("component_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("cbt_exams", "component_id")
