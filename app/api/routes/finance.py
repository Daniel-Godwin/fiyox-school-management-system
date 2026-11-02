"""School finance — expenses, other income, payroll, and the proprietor's
overview (fee income + other income − expenses − payroll = net).

Finance is for the bursar and the school admin; the principal may read the
overview for oversight.
"""
import calendar
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.academics import Term
from app.models.finance import (
    ExpenseCategory, Expense, IncomeEntry,
    SalaryStructure, PayrollRun, Payslip, RUN_DRAFT, RUN_PAID,
)
from app.schemas import (
    ExpenseCategoryIn, ExpenseIn, IncomeIn, SalaryIn, PayrollRunIn, PayslipAdjustIn,
)
from app.services.finance import build_overview, generate_payslips
from app.services.audit import record_audit

router = APIRouter(prefix="/api/finance", tags=["finance"])

FinanceRoles = Depends(require_roles(Role.BURSAR, Role.SCHOOL_ADMIN))
OverviewRoles = Depends(require_roles(Role.BURSAR, Role.SCHOOL_ADMIN, Role.PRINCIPAL))

_STAFF_ROLES = ("school_admin", "principal", "bursar", "teacher")
_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


# ==================================================================
# Expense categories
# ==================================================================
@router.get("/expense-categories")
async def list_categories(db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    rows = (await db.execute(select(ExpenseCategory).where(
        ExpenseCategory.school_id == school_id,
        ExpenseCategory.deleted_at.is_(None)).order_by(ExpenseCategory.name))).scalars().all()
    return [{"id": c.id, "name": c.name} for c in rows]


@router.post("/expense-categories", status_code=201)
async def add_category(payload: ExpenseCategoryIn, db: DbDep,
                       user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    c = ExpenseCategory(school_id=school_id, name=payload.name.strip(), created_by=user.id)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {"id": c.id, "name": c.name}


@router.delete("/expense-categories/{cat_id}", status_code=204)
async def del_category(cat_id: str, db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    c = await db.get(ExpenseCategory, cat_id)
    if c is None or c.school_id != school_id or c.deleted_at:
        raise HTTPException(404, "Category not found")
    from datetime import datetime, timezone
    c.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ==================================================================
# Expenses
# ==================================================================
async def _cat_names(db, school_id):
    return {c.id: c.name for c in (await db.execute(select(ExpenseCategory).where(
        ExpenseCategory.school_id == school_id))).scalars().all()}


@router.get("/expenses")
async def list_expenses(db: DbDep, user: Annotated[User, FinanceRoles],
                        start: date | None = Query(None), end: date | None = Query(None),
                        category_id: str | None = Query(None)):
    school_id = tenant_scope(user)
    stmt = select(Expense).where(Expense.school_id == school_id, Expense.deleted_at.is_(None))
    if start:
        stmt = stmt.where(Expense.spent_on >= start)
    if end:
        stmt = stmt.where(Expense.spent_on <= end)
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    rows = (await db.execute(stmt)).scalars().all()
    rows = sorted(rows, key=lambda e: str(e.spent_on), reverse=True)
    names = await _cat_names(db, school_id)
    total = sum(e.amount for e in rows)
    return {"total": round(total, 2), "expenses": [{
        "id": e.id, "spent_on": str(e.spent_on), "category": names.get(e.category_id),
        "category_id": e.category_id, "description": e.description, "amount": e.amount,
        "payee": e.payee, "method": e.method, "note": e.note,
    } for e in rows]}


@router.post("/expenses", status_code=201)
async def add_expense(payload: ExpenseIn, request: Request, db: DbDep,
                      user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    if payload.category_id:
        c = await db.get(ExpenseCategory, payload.category_id)
        if c is None or c.school_id != school_id:
            raise HTTPException(422, "Unknown category")
    e = Expense(school_id=school_id, created_by=user.id,
                spent_on=payload.spent_on, category_id=payload.category_id,
                description=payload.description.strip(), amount=payload.amount,
                payee=(payload.payee or "").strip() or None, method=payload.method,
                note=(payload.note or "").strip() or None)
    db.add(e)
    await record_audit(db, school_id=school_id, user_id=user.id, action="create",
                       table_name="expenses", record_id=None,
                       changes={"amount": payload.amount, "description": payload.description},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(e)
    return {"id": e.id}


@router.delete("/expenses/{expense_id}", status_code=204)
async def del_expense(expense_id: str, db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    e = await db.get(Expense, expense_id)
    if e is None or e.school_id != school_id or e.deleted_at:
        raise HTTPException(404, "Expense not found")
    from datetime import datetime, timezone
    e.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ==================================================================
# Other income
# ==================================================================
@router.get("/income")
async def list_income(db: DbDep, user: Annotated[User, FinanceRoles],
                      start: date | None = Query(None), end: date | None = Query(None)):
    school_id = tenant_scope(user)
    stmt = select(IncomeEntry).where(IncomeEntry.school_id == school_id,
                                     IncomeEntry.deleted_at.is_(None))
    if start:
        stmt = stmt.where(IncomeEntry.received_on >= start)
    if end:
        stmt = stmt.where(IncomeEntry.received_on <= end)
    rows = (await db.execute(stmt)).scalars().all()
    rows = sorted(rows, key=lambda i: str(i.received_on), reverse=True)
    total = sum(i.amount for i in rows)
    return {"total": round(total, 2), "income": [{
        "id": i.id, "received_on": str(i.received_on), "source": i.source,
        "description": i.description, "amount": i.amount, "method": i.method,
    } for i in rows]}


@router.post("/income", status_code=201)
async def add_income(payload: IncomeIn, db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    i = IncomeEntry(school_id=school_id, created_by=user.id,
                    received_on=payload.received_on, source=payload.source.strip(),
                    description=(payload.description or "").strip() or None,
                    amount=payload.amount, method=payload.method)
    db.add(i)
    await db.commit()
    await db.refresh(i)
    return {"id": i.id}


@router.delete("/income/{income_id}", status_code=204)
async def del_income(income_id: str, db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    i = await db.get(IncomeEntry, income_id)
    if i is None or i.school_id != school_id or i.deleted_at:
        raise HTTPException(404, "Income not found")
    from datetime import datetime, timezone
    i.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ==================================================================
# Salaries
# ==================================================================
@router.get("/salaries")
async def list_salaries(db: DbDep, user: Annotated[User, FinanceRoles]):
    """Every staff member with their standing salary (zero if unset)."""
    school_id = tenant_scope(user)
    staff = (await db.execute(select(User).where(
        User.school_id == school_id, User.is_active == True))).scalars().all()  # noqa: E712
    staff = [u for u in staff if str(getattr(u.role, "value", u.role)) in _STAFF_ROLES]
    structs = {s.staff_user_id: s for s in (await db.execute(select(SalaryStructure).where(
        SalaryStructure.school_id == school_id,
        SalaryStructure.deleted_at.is_(None)))).scalars().all()}
    out = []
    for u in sorted(staff, key=lambda x: (x.first_name, x.last_name)):
        s = structs.get(u.id)
        out.append({
            "staff_user_id": u.id, "name": f"{u.first_name} {u.last_name}",
            "role": str(getattr(u.role, "value", u.role)),
            "gross": s.gross if s else 0, "deduction": s.deduction if s else 0,
            "net": round((s.gross - s.deduction), 2) if s else 0,
            "is_active": s.is_active if s else False, "has_salary": s is not None,
        })
    return out


@router.put("/salaries")
async def set_salary(payload: SalaryIn, db: DbDep, user: Annotated[User, FinanceRoles]):
    """Create or update a staff member's standing salary."""
    school_id = tenant_scope(user)
    staff = await db.get(User, payload.staff_user_id)
    if staff is None or staff.school_id != school_id:
        raise HTTPException(404, "Staff member not found")
    s = (await db.execute(select(SalaryStructure).where(
        SalaryStructure.school_id == school_id,
        SalaryStructure.staff_user_id == payload.staff_user_id,
        SalaryStructure.deleted_at.is_(None)))).scalars().first()
    if s is None:
        s = SalaryStructure(school_id=school_id, staff_user_id=payload.staff_user_id,
                            created_by=user.id)
        db.add(s)
    s.gross = payload.gross
    s.deduction = payload.deduction
    s.is_active = payload.is_active
    s.updated_by = user.id
    await db.commit()
    return {"staff_user_id": payload.staff_user_id, "gross": s.gross,
            "deduction": s.deduction, "net": round(s.gross - s.deduction, 2)}


# ==================================================================
# Payroll
# ==================================================================
def _run_out(r: PayrollRun) -> dict:
    return {"id": r.id, "month": r.month, "label": r.label, "status": r.status,
            "total_net": r.total_net, "note": r.note}


@router.get("/payroll")
async def list_runs(db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    rows = (await db.execute(select(PayrollRun).where(
        PayrollRun.school_id == school_id,
        PayrollRun.deleted_at.is_(None)).order_by(PayrollRun.month.desc()))).scalars().all()
    return [_run_out(r) for r in rows]


@router.post("/payroll", status_code=201)
async def create_run(payload: PayrollRunIn, db: DbDep,
                     user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    existing = (await db.execute(select(PayrollRun).where(
        PayrollRun.school_id == school_id, PayrollRun.month == payload.month,
        PayrollRun.deleted_at.is_(None)))).scalars().first()
    if existing is not None:
        raise HTTPException(409, "A payroll run already exists for that month")
    yy, mm = payload.month.split("-")
    label = f"{_MONTHS[int(mm)]} {yy}"
    run = PayrollRun(school_id=school_id, month=payload.month, label=label,
                     status=RUN_DRAFT, note=(payload.note or "").strip(),
                     created_by=user.id)
    db.add(run)
    await db.flush()
    total = await generate_payslips(db, school_id, run, user.id)
    if total == 0 and run.total_net == 0:
        # no active salaries configured
        count = len((await db.execute(select(Payslip).where(Payslip.run_id == run.id))).scalars().all())
        if count == 0:
            raise HTTPException(409, "No active staff salaries are set up yet")
    await db.commit()
    await db.refresh(run)
    return _run_out(run)


@router.get("/payroll/{run_id}")
async def run_detail(run_id: str, db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    run = await db.get(PayrollRun, run_id)
    if run is None or run.school_id != school_id or run.deleted_at:
        raise HTTPException(404, "Payroll run not found")
    slips = (await db.execute(select(Payslip).where(
        Payslip.run_id == run_id, Payslip.deleted_at.is_(None)))).scalars().all()
    names = {u.id: f"{u.first_name} {u.last_name}" for u in (await db.execute(
        select(User).where(User.school_id == school_id))).scalars().all()}
    rows = [{
        "id": p.id, "staff_user_id": p.staff_user_id,
        "name": names.get(p.staff_user_id, "—"),
        "gross": p.gross, "deduction": p.deduction, "net": p.net,
        "paid": p.paid, "paid_on": str(p.paid_on) if p.paid_on else None,
    } for p in slips]
    rows.sort(key=lambda r: r["name"])
    paid = sum(1 for r in rows if r["paid"])
    return {**_run_out(run), "payslips": rows,
            "staff_count": len(rows), "paid_count": paid}


@router.patch("/payroll/{run_id}/payslips/{slip_id}")
async def adjust_payslip(run_id: str, slip_id: str, payload: PayslipAdjustIn, db: DbDep,
                         user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    run = await db.get(PayrollRun, run_id)
    if run is None or run.school_id != school_id or run.deleted_at:
        raise HTTPException(404, "Payroll run not found")
    p = await db.get(Payslip, slip_id)
    if p is None or p.run_id != run_id or p.school_id != school_id or p.deleted_at:
        raise HTTPException(404, "Payslip not found")
    if p.paid:
        raise HTTPException(409, "This payslip is already paid")
    if payload.gross is not None:
        p.gross = payload.gross
    if payload.deduction is not None:
        p.deduction = payload.deduction
    p.net = round(p.gross - p.deduction, 2)
    await _recount_run(db, run)
    await db.commit()
    return {"id": p.id, "net": p.net, "run_total": run.total_net}


async def _recount_run(db, run: PayrollRun):
    slips = (await db.execute(select(Payslip).where(
        Payslip.run_id == run.id, Payslip.deleted_at.is_(None)))).scalars().all()
    run.total_net = round(sum(s.net for s in slips), 2)


@router.post("/payroll/{run_id}/payslips/{slip_id}/pay")
async def pay_slip(run_id: str, slip_id: str, db: DbDep,
                   user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    p = await db.get(Payslip, slip_id)
    if p is None or p.run_id != run_id or p.school_id != school_id or p.deleted_at:
        raise HTTPException(404, "Payslip not found")
    p.paid = True
    p.paid_on = date.today()
    p.updated_by = user.id
    await _settle_run(db, run_id, school_id)
    await db.commit()
    return {"id": p.id, "paid": True}


@router.post("/payroll/{run_id}/pay-all")
async def pay_all(run_id: str, request: Request, db: DbDep,
                  user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    run = await db.get(PayrollRun, run_id)
    if run is None or run.school_id != school_id or run.deleted_at:
        raise HTTPException(404, "Payroll run not found")
    slips = (await db.execute(select(Payslip).where(
        Payslip.run_id == run_id, Payslip.deleted_at.is_(None)))).scalars().all()
    today = date.today()
    n = 0
    for p in slips:
        if not p.paid:
            p.paid = True
            p.paid_on = today
            n += 1
    run.status = RUN_PAID
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="payroll_runs", record_id=run.id,
                       changes={"paid_slips": n, "total_net": run.total_net},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"id": run.id, "status": run.status, "paid": n}


async def _settle_run(db, run_id: str, school_id: str):
    """Mark the run paid once every payslip in it is paid."""
    run = await db.get(PayrollRun, run_id)
    slips = (await db.execute(select(Payslip).where(
        Payslip.run_id == run_id, Payslip.deleted_at.is_(None)))).scalars().all()
    if slips and all(s.paid for s in slips):
        run.status = RUN_PAID


@router.delete("/payroll/{run_id}", status_code=204)
async def delete_run(run_id: str, db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    run = await db.get(PayrollRun, run_id)
    if run is None or run.school_id != school_id or run.deleted_at:
        raise HTTPException(404, "Payroll run not found")
    if run.status == RUN_PAID:
        raise HTTPException(409, "A paid payroll run cannot be deleted")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    run.deleted_at = now
    for p in (await db.execute(select(Payslip).where(Payslip.run_id == run_id))).scalars().all():
        p.deleted_at = now
    await db.commit()


# ==================================================================
# Overview
# ==================================================================
@router.get("/overview")
async def overview(db: DbDep, user: Annotated[User, OverviewRoles],
                   start: date | None = Query(None), end: date | None = Query(None),
                   term_id: str | None = Query(None)):
    """Net position for a period. Give start/end, a term_id, or neither
    (defaults to the current month)."""
    school_id = tenant_scope(user)
    if term_id:
        t = await db.get(Term, term_id)
        if t is None or t.school_id != school_id:
            raise HTTPException(404, "Term not found")
        if t.start_date and t.end_date:
            start, end = t.start_date, t.end_date
    if not start or not end:
        today = date.today()
        start = start or today.replace(day=1)
        end = end or today.replace(day=calendar.monthrange(today.year, today.month)[1])
    data = await build_overview(db, school_id, start, end)
    return data
