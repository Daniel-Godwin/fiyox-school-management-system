"""School finance — accounting (expenses, income) and payroll.

Adds six tenant-scoped tables: expense_categories, expenses, income_entries,
salary_structures, payroll_runs, payslips.

Revision ID: c3d4e5f6a9b0
Revises: b2c3d4e5f6a8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a9b0"
down_revision: Union[str, None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MIX = [
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_by", sa.String(length=36), nullable=True),
    sa.Column("updated_by", sa.String(length=36), nullable=True),
    sa.Column("school_id", sa.String(length=36), nullable=False),
]


def _school_fk():
    return sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("name", sa.String(length=100), nullable=False),
        *_MIX, _school_fk(), sa.PrimaryKeyConstraint("id"))
    with op.batch_alter_table("expense_categories") as b:
        b.create_index(b.f("ix_expense_categories_school_id"), ["school_id"])

    op.create_table(
        "expenses",
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payee", sa.String(length=160), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False, server_default="cash"),
        sa.Column("note", sa.Text(), nullable=True),
        *_MIX,
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"]),
        _school_fk(), sa.PrimaryKeyConstraint("id"))
    with op.batch_alter_table("expenses") as b:
        b.create_index(b.f("ix_expenses_school_id"), ["school_id"])

    op.create_table(
        "income_entries",
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("method", sa.String(length=16), nullable=False, server_default="cash"),
        *_MIX, _school_fk(), sa.PrimaryKeyConstraint("id"))
    with op.batch_alter_table("income_entries") as b:
        b.create_index(b.f("ix_income_entries_school_id"), ["school_id"])

    op.create_table(
        "salary_structures",
        sa.Column("staff_user_id", sa.String(length=36), nullable=False),
        sa.Column("gross", sa.Float(), nullable=False, server_default="0"),
        sa.Column("deduction", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_MIX,
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"]),
        _school_fk(), sa.PrimaryKeyConstraint("id"))
    with op.batch_alter_table("salary_structures") as b:
        b.create_index(b.f("ix_salary_structures_school_id"), ["school_id"])
        b.create_index(b.f("ix_salary_structures_staff_user_id"), ["staff_user_id"])

    op.create_table(
        "payroll_runs",
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
        sa.Column("note", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("total_net", sa.Float(), nullable=False, server_default="0"),
        *_MIX, _school_fk(), sa.PrimaryKeyConstraint("id"))
    with op.batch_alter_table("payroll_runs") as b:
        b.create_index(b.f("ix_payroll_runs_school_id"), ["school_id"])

    op.create_table(
        "payslips",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("staff_user_id", sa.String(length=36), nullable=False),
        sa.Column("gross", sa.Float(), nullable=False, server_default="0"),
        sa.Column("deduction", sa.Float(), nullable=False, server_default="0"),
        sa.Column("net", sa.Float(), nullable=False, server_default="0"),
        sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paid_on", sa.Date(), nullable=True),
        *_MIX,
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"]),
        _school_fk(), sa.PrimaryKeyConstraint("id"))
    with op.batch_alter_table("payslips") as b:
        b.create_index(b.f("ix_payslips_school_id"), ["school_id"])
        b.create_index(b.f("ix_payslips_run_id"), ["run_id"])
        b.create_index(b.f("ix_payslips_staff_user_id"), ["staff_user_id"])


def downgrade() -> None:
    op.drop_table("payslips")
    op.drop_table("payroll_runs")
    op.drop_table("salary_structures")
    op.drop_table("income_entries")
    op.drop_table("expenses")
    op.drop_table("expense_categories")
