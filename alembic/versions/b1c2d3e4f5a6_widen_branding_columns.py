"""widen branding columns to text

The logo/signature/stamp columns hold base64 data URIs (tens of thousands of
characters), not URLs. They were declared String(400): SQLite ignores varchar
limits, so this passed locally, but Postgres enforces them and rejected every
upload with StringDataRightTruncation. Widen to TEXT.

Revision ID: b1c2d3e4f5a6
Revises: 835a4a67659c
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '835a4a67659c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("logo_url", "signature_url", "stamp_url")


def upgrade() -> None:
    # Widening is always safe: every existing value fits in the larger type.
    with op.batch_alter_table('schools', schema=None) as batch_op:
        for col in _COLUMNS:
            batch_op.alter_column(
                col,
                existing_type=sa.String(length=400),
                type_=sa.Text(),
                existing_nullable=True,
            )


def downgrade() -> None:
    # Narrowing could truncate real image data, so refuse rather than destroy it.
    conn = op.get_bind()
    for col in _COLUMNS:
        too_long = conn.execute(sa.text(
            f"SELECT count(*) FROM schools WHERE length({col}) > 400")).scalar()
        if too_long:
            raise RuntimeError(
                f"Cannot downgrade: {too_long} school(s) have a {col} longer than "
                "400 characters. Clear the branding images first.")
    with op.batch_alter_table('schools', schema=None) as batch_op:
        for col in _COLUMNS:
            batch_op.alter_column(
                col,
                existing_type=sa.Text(),
                type_=sa.String(length=400),
                existing_nullable=True,
            )
