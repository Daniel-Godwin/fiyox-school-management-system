"""Finance endpoints — managed by bursar or school admin, tenant-scoped, audited."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy import func, select
from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import School, User, Role
from app.models.student import Student
from app.models.fees import (
    FeeCategory, FeeStructure, Invoice, Payment, InvoiceStatus,
)
from app.schemas import (
    CategoryIn, CategoryOut, StructureIn, StructureOut,
    GenerateInvoicesIn, InvoiceOut, PaymentIn,
)
from app.services.fees import (
    generate_invoices, record_payment, invoice_view, paid_total,
)
from app.services.receipt_pdf import build_receipt_pdf

router = APIRouter(prefix="/api/fees", tags=["fees"])

FinanceRoles = Depends(require_roles(Role.BURSAR, Role.SCHOOL_ADMIN))


# ---------- Categories ----------
@router.post("/categories", response_model=CategoryOut,
             status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryIn, db: DbDep, user: Annotated[User, FinanceRoles],
):
    school_id = tenant_scope(user)
    cat = FeeCategory(school_id=school_id, name=payload.name, created_by=user.id)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: DbDep, user: Annotated[User, FinanceRoles]):
    school_id = tenant_scope(user)
    rows = await db.execute(select(FeeCategory).where(
        FeeCategory.school_id == school_id, FeeCategory.deleted_at.is_(None)))
    return list(rows.scalars().all())


# ---------- Fee structures ----------
@router.post("/structures", response_model=StructureOut,
             status_code=status.HTTP_201_CREATED)
async def create_structure(
    payload: StructureIn, db: DbDep, user: Annotated[User, FinanceRoles],
):
    school_id = tenant_scope(user)
    exists = (await db.execute(select(FeeStructure).where(
        FeeStructure.school_id == school_id,
        FeeStructure.class_id == payload.class_id,
        FeeStructure.term_id == payload.term_id,
        FeeStructure.category_id == payload.category_id))).scalars().first()
    if exists:
        raise HTTPException(status_code=409,
                            detail="Structure already exists for this class/term/category")
    fs = FeeStructure(school_id=school_id, created_by=user.id, **payload.model_dump())
    db.add(fs)
    await db.commit()
    await db.refresh(fs)
    return fs


@router.get("/structures", response_model=list[StructureOut])
async def list_structures(
    db: DbDep, user: Annotated[User, FinanceRoles],
    term_id: str | None = Query(None), class_id: str | None = Query(None),
):
    school_id = tenant_scope(user)
    stmt = select(FeeStructure).where(FeeStructure.school_id == school_id,
                                      FeeStructure.deleted_at.is_(None))
    if term_id:
        stmt = stmt.where(FeeStructure.term_id == term_id)
    if class_id:
        stmt = stmt.where(FeeStructure.class_id == class_id)
    return list((await db.execute(stmt)).scalars().all())


# ---------- Invoices ----------
@router.post("/invoices/generate")
async def generate(
    payload: GenerateInvoicesIn, request: Request, db: DbDep,
    user: Annotated[User, FinanceRoles],
):
    school_id = tenant_scope(user)
    res = await generate_invoices(
        db, school_id, user.id, payload.arm_id, payload.term_id,
        due_date=payload.due_date,
        ip=request.client.host if request.client else None)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    db: DbDep, user: Annotated[User, FinanceRoles],
    term_id: str | None = Query(None),
    student_id: str | None = Query(None),
    status_filter: InvoiceStatus | None = Query(None, alias="status"),
):
    school_id = tenant_scope(user)
    stmt = select(Invoice).where(Invoice.school_id == school_id,
                                 Invoice.deleted_at.is_(None))
    if term_id:
        stmt = stmt.where(Invoice.term_id == term_id)
    if student_id:
        stmt = stmt.where(Invoice.student_id == student_id)
    if status_filter:
        stmt = stmt.where(Invoice.status == status_filter)
    invoices = (await db.execute(stmt)).scalars().all()
    return [await invoice_view(db, inv) for inv in invoices]


# ---------- Payments ----------
@router.post("/payments")
async def pay(
    payload: PaymentIn, request: Request, db: DbDep,
    user: Annotated[User, FinanceRoles],
):
    school_id = tenant_scope(user)
    res, err = await record_payment(
        db, school_id, user.id,
        invoice_id=payload.invoice_id, method=payload.method,
        reference=payload.reference, amount=payload.amount,
        paid_at=payload.paid_at,
        ip=request.client.host if request.client else None)
    if err:
        raise HTTPException(status_code=404, detail=err)
    return res


# ---------- Receipt PDF ----------
@router.get("/payments/{payment_id}/receipt")
async def payment_receipt(
    payment_id: str, db: DbDep, user: Annotated[User, FinanceRoles],
):
    school_id = tenant_scope(user)
    pay = await db.get(Payment, payment_id)
    if not pay or pay.school_id != school_id:
        raise HTTPException(status_code=404, detail="Payment not found")
    inv = await db.get(Invoice, pay.invoice_id)
    student = await db.get(Student, inv.student_id)
    school = await db.get(School, school_id)
    receiver = await db.get(User, pay.received_by) if pay.received_by else None

    inv_view = await invoice_view(db, inv)
    pdf = build_receipt_pdf({
        "school": {"name": school.name, "address": school.address,
                   "state": school.state, "color": school.primary_color},
        "receipt_number": f"RCP-{pay.reference}",
        "student_name": f"{student.first_name} {student.last_name}",
        "admission_number": student.admission_number,
        "invoice_number": inv.invoice_number,
        "method": pay.method, "reference": pay.reference,
        "amount": pay.amount, "paid_at": pay.paid_at,
        "invoice": inv_view,
        "received_by": f"{receiver.first_name} {receiver.last_name}" if receiver else None,
    })
    fname = f"receipt_{pay.reference}.pdf"
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{fname}"'})


# ---------- Bursar summary ----------
@router.get("/summary")
async def fees_summary(
    db: DbDep, user: Annotated[User, FinanceRoles],
    term_id: str = Query(...),
):
    """One-look dashboard numbers for a term: expected vs collected vs outstanding,
    plus invoice counts by status."""
    school_id = tenant_scope(user)
    invoices = (await db.execute(select(Invoice).where(
        Invoice.school_id == school_id, Invoice.term_id == term_id,
        Invoice.deleted_at.is_(None)))).scalars().all()

    expected = collected = 0.0
    counts = {s.value: 0 for s in InvoiceStatus}
    debtors = []
    for inv in invoices:
        due = inv.amount - inv.discount
        paid = await paid_total(db, inv.id)
        expected += due
        collected += min(paid, due) if due > 0 else paid
        counts[str(inv.status)] = counts.get(str(inv.status), 0) + 1
        balance = round(due - paid, 2)
        if balance > 0:
            debtors.append({"student_id": inv.student_id,
                            "invoice_number": inv.invoice_number,
                            "balance": balance})

    return {
        "term_id": term_id,
        "invoices": len(invoices),
        "expected": round(expected, 2),
        "collected": round(collected, 2),
        "outstanding": round(expected - collected, 2),
        "collection_rate": round(collected / expected * 100, 1) if expected else 0.0,
        "by_status": counts,
        "debtors": sorted(debtors, key=lambda d: -d["balance"]),
    }
