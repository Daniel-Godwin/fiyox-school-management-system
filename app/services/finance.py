"""Finance aggregation and payroll generation."""
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fees import Payment
from app.models.finance import (
    ExpenseCategory, Expense, IncomeEntry,
    SalaryStructure, PayrollRun, Payslip, RUN_PAID,
)
from app.models.school import User, Role


async def fee_income(db: AsyncSession, school_id: str,
                     start: date, end: date) -> float:
    total = (await db.execute(select(func.sum(Payment.amount)).where(
        Payment.school_id == school_id,
        Payment.deleted_at.is_(None),
        Payment.paid_at >= start, Payment.paid_at <= end))).scalar()
    return float(total or 0)


async def build_overview(db: AsyncSession, school_id: str,
                         start: date, end: date) -> dict:
    """fee income + other income − expenses − payroll = net, for a date range."""
    fees = await fee_income(db, school_id, start, end)

    other = float((await db.execute(select(func.sum(IncomeEntry.amount)).where(
        IncomeEntry.school_id == school_id, IncomeEntry.deleted_at.is_(None),
        IncomeEntry.received_on >= start, IncomeEntry.received_on <= end))).scalar() or 0)

    # expenses, with a breakdown by category
    exp_rows = (await db.execute(select(Expense).where(
        Expense.school_id == school_id, Expense.deleted_at.is_(None),
        Expense.spent_on >= start, Expense.spent_on <= end))).scalars().all()
    expenses_total = sum(e.amount for e in exp_rows)
    cat_names = {c.id: c.name for c in (await db.execute(select(ExpenseCategory).where(
        ExpenseCategory.school_id == school_id))).scalars().all()}
    by_cat: dict[str, float] = {}
    for e in exp_rows:
        name = cat_names.get(e.category_id, "Uncategorised") if e.category_id else "Uncategorised"
        by_cat[name] = by_cat.get(name, 0.0) + e.amount

    # payroll actually paid out in the range (paid payslips)
    payroll = float((await db.execute(select(func.sum(Payslip.net)).where(
        Payslip.school_id == school_id, Payslip.deleted_at.is_(None),
        Payslip.paid == True,                                   # noqa: E712
        Payslip.paid_on >= start, Payslip.paid_on <= end))).scalar() or 0)

    income_total = round(fees + other, 2)
    outflow = round(expenses_total + payroll, 2)
    return {
        "start": str(start), "end": str(end),
        "fee_income": round(fees, 2),
        "other_income": round(other, 2),
        "income_total": income_total,
        "expenses": round(expenses_total, 2),
        "payroll": round(payroll, 2),
        "outflow": outflow,
        "net": round(income_total - outflow, 2),
        "expenses_by_category": [{"category": k, "amount": round(v, 2)}
                                 for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
    }


def _staff_roles():
    return (Role.SCHOOL_ADMIN, Role.PRINCIPAL, Role.BURSAR, Role.TEACHER)


async def generate_payslips(db: AsyncSession, school_id: str, run: PayrollRun,
                            actor_id: str) -> float:
    """Create a payslip for every active salary structure. Returns total net."""
    structures = (await db.execute(select(SalaryStructure).where(
        SalaryStructure.school_id == school_id,
        SalaryStructure.is_active == True,                      # noqa: E712
        SalaryStructure.deleted_at.is_(None)))).scalars().all()
    total = 0.0
    for s in structures:
        net = round(s.gross - s.deduction, 2)
        db.add(Payslip(school_id=school_id, run_id=run.id, staff_user_id=s.staff_user_id,
                       gross=s.gross, deduction=s.deduction, net=net, paid=False,
                       created_by=actor_id))
        total += net
    run.total_net = round(total, 2)
    return run.total_net
