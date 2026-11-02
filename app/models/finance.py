"""School finance — accounting (expenses, other income) and payroll.

The school already records fee income through invoices and payments. This adds
the other side of the books:

  * Expense / ExpenseCategory — money out (salaries, utilities, supplies…).
  * IncomeEntry — non-fee money in (donations, PTA levies, sales…).
  * SalaryStructure / PayrollRun / Payslip — staff pay, run month by month.

A finance overview then ties it together for the proprietor:
    fee income + other income − expenses − payroll = net position.

Statuses are plain strings (like the rest of the system): new states never need
a migration.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin

# payroll run lifecycle
RUN_DRAFT = "draft"
RUN_PAID = "paid"


class ExpenseCategory(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """e.g. Salaries, Utilities, Rent, Maintenance, Supplies, Transport."""
    __tablename__ = "expense_categories"
    name: Mapped[str] = mapped_column(String(100))


class Expense(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One payment out of the school's purse."""
    __tablename__ = "expenses"

    spent_on: Mapped[date] = mapped_column(Date)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("expense_categories.id"))
    description: Mapped[str] = mapped_column(String(300))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    payee: Mapped[str | None] = mapped_column(String(160))
    method: Mapped[str] = mapped_column(String(16), default="cash")
    note: Mapped[str | None] = mapped_column(Text)


class IncomeEntry(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Non-fee income the school received."""
    __tablename__ = "income_entries"

    received_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(300))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(16), default="cash")


class SalaryStructure(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A staff member's standing monthly pay. One active row per staff user."""
    __tablename__ = "salary_structures"

    staff_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    gross: Mapped[float] = mapped_column(Float, default=0.0)
    # a flat standing deduction (tax, pension…) applied each run; per-run
    # adjustments live on the payslip
    deduction: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PayrollRun(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One month's payroll — a batch of payslips."""
    __tablename__ = "payroll_runs"

    month: Mapped[str] = mapped_column(String(7))   # "YYYY-MM"
    label: Mapped[str] = mapped_column(String(40))  # "November 2026"
    status: Mapped[str] = mapped_column(String(12), default=RUN_DRAFT)
    note: Mapped[str] = mapped_column(String(300), default="")
    total_net: Mapped[float] = mapped_column(Float, default=0.0)


class Payslip(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One staff member's pay for one run."""
    __tablename__ = "payslips"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    staff_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    gross: Mapped[float] = mapped_column(Float, default=0.0)
    deduction: Mapped[float] = mapped_column(Float, default=0.0)
    net: Mapped[float] = mapped_column(Float, default=0.0)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_on: Mapped[date | None] = mapped_column(Date)
