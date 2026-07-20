"""Finance endpoints — managed by bursar or school admin, tenant-scoped, audited."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy import func, select
from app.core.config import settings
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
async def _invoice_items(db, school_id: str, invoice_id: str) -> list[dict]:
    """The billed breakdown for an invoice, as frozen when it was issued."""
    from app.models.fees import InvoiceItem
    rows = (await db.execute(select(InvoiceItem).where(
        InvoiceItem.school_id == school_id,
        InvoiceItem.invoice_id == invoice_id,
        InvoiceItem.deleted_at.is_(None)))).scalars().all()
    return [{"name": r.category_name, "amount": r.amount}
            for r in sorted(rows, key=lambda x: (-x.amount, x.category_name))]


@router.get("/payments/{payment_id}/receipt")
async def payment_receipt(
    payment_id: str, db: DbDep, user: Annotated[User, FinanceRoles],
    download: bool = Query(False, description="save the file instead of opening it"),
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
                   "state": school.state, "color": school.primary_color,
                   "logo_url": school.logo_url,
                   "signature_url": school.signature_url,
                   "stamp_url": school.stamp_url,
                   "principal_name": school.principal_name},
        "receipt_number": f"RCP-{pay.reference}",
        "student_name": f"{student.first_name} {student.last_name}",
        "admission_number": student.admission_number,
        "invoice_number": inv.invoice_number,
        "method": pay.method, "reference": pay.reference,
        "amount": pay.amount, "paid_at": pay.paid_at,
        "invoice": inv_view,
        "items": await _invoice_items(db, school_id, inv.id) if inv else [],
        "received_by": f"{receiver.first_name} {receiver.last_name}" if receiver else None,
    })
    fname = f"receipt_{pay.reference}.pdf"
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{fname}"'})


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


# ---------- Online payment (Paystack) ----------
import json as _json
import uuid as _uuid
from app.core.deps import CurrentUser
from app.models.student import Guardian
from app.models.fees import PaymentMethod
from app.services.paystack import (
    gateway_configured, initialize_payment, verify_signature,
)
from app.services.fees import record_payment, paid_total as _paid_total


@router.post("/invoices/{invoice_id}/pay/init")
async def init_online_payment(invoice_id: str, db: DbDep, user: CurrentUser):
    """Start a Paystack checkout for an invoice's outstanding balance.
    Parents may pay for their own wards; bursar/admin may initiate for anyone."""
    school_id = tenant_scope(user)
    inv = await db.get(Invoice, invoice_id)
    if not inv or inv.school_id != school_id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if user.role == Role.PARENT:
        link = (await db.execute(select(Guardian).where(
            Guardian.parent_user_id == user.id,
            Guardian.student_id == inv.student_id))).scalars().first()
        if not link:
            raise HTTPException(status_code=403, detail="Not your ward's invoice")
    elif user.role not in (Role.SCHOOL_ADMIN, Role.BURSAR, Role.SUPER_ADMIN, Role.STUDENT):
        raise HTTPException(status_code=403, detail="Not allowed")

    paid = await _paid_total(db, inv.id)
    balance = round(inv.amount - inv.discount - paid, 2)
    if balance <= 0:
        raise HTTPException(status_code=400, detail="This invoice is fully paid")

    # the school's own decision comes first: if online payment is switched off
    # for this school, that is the answer regardless of platform configuration
    from app.models.school import School as _School
    school = await db.get(_School, school_id)
    if not school or not school.online_payments_enabled:
        raise HTTPException(
            status_code=400,
            detail="Online payment is not enabled for this school — please pay "
                   "at the school bursary")

    if not gateway_configured():
        raise HTTPException(
            status_code=503,
            detail="Online payments are not enabled yet — please pay at the school bursary")

    reference = f"PSK-{inv.invoice_number}-{_uuid.uuid4().hex[:8]}"
    # bring the parent back to their wards page after paying; the money itself
    # is recorded by the signed webhook, not by this redirect
    origin = (settings.FRONTEND_ORIGIN or "").split(",")[0].strip().rstrip("/")
    callback = f"{origin}/dashboard/wards?paid=1" if origin and origin != "*" else None

    url, err = await initialize_payment(
        email=user.email, amount_kobo=int(round(balance * 100)),
        reference=reference,
        metadata={"invoice_id": inv.id, "school_id": school_id},
        callback_url=callback)
    if err:
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {err}")
    return {"authorization_url": url, "reference": reference, "amount": balance}


@router.post("/paystack/webhook")
async def paystack_webhook(request: Request, db: DbDep):
    """Paystack calls this after a charge. Trust nothing until the HMAC-SHA512
    signature of the raw body verifies; then record the payment idempotently."""
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not verify_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event = _json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    if event.get("event") != "charge.success":
        return {"received": True, "ignored": event.get("event")}

    data = event.get("data") or {}
    meta = data.get("metadata") or {}
    invoice_id = meta.get("invoice_id")
    school_id = meta.get("school_id")
    reference = data.get("reference")
    amount_naira = round((data.get("amount") or 0) / 100, 2)
    if not (invoice_id and school_id and reference and amount_naira > 0):
        raise HTTPException(status_code=400, detail="Missing payment details")

    res, err = await record_payment(
        db, school_id, None,
        invoice_id=invoice_id, method=PaymentMethod.PAYSTACK,
        reference=reference, amount=amount_naira,
        ip=request.client.host if request.client else None)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"received": True, "duplicate": res["duplicate"]}


# ---------- Fee maintenance: schools change their minds ----------
"""A school raises its fees, drops a category, or corrects a mistake.

The rule throughout: **money already collected is never rewritten.** An invoice
snapshots its amount when generated, so editing a fee structure changes what
*future* invoices will say, not what a parent already owes or paid. To push a
change onto existing bills the admin must ask for it explicitly (re-issue), and
even then an invoice can never be reduced below what has already been paid.
"""
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.models.academics import ClassArm
from app.models.fees import FeeCategory, FeeStructure, Invoice, InvoiceStatus
from app.services.fees import paid_total, status_for
from app.services.audit import record_audit


class CategoryUpdate(BaseModel):
    name: str


class StructureUpdate(BaseModel):
    amount: float = Field(gt=0)


class ReissueIn(BaseModel):
    term_id: str
    class_id: str


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def rename_category(
    category_id: str, payload: CategoryUpdate, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN, Role.BURSAR))],
):
    school_id = tenant_scope(user)
    cat = await db.get(FeeCategory, category_id)
    if not cat or cat.school_id != school_id or cat.deleted_at:
        raise HTTPException(status_code=404, detail="Category not found")
    old = cat.name
    cat.name = payload.name
    cat.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="fee_categories", record_id=cat.id,
                       changes={"name": {"old": old, "new": payload.name}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}")
async def retire_category(
    category_id: str, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Retire a category (soft delete). Fees already charged under it stay on
    the invoices that carry them — history is not rewritten."""
    school_id = tenant_scope(user)
    cat = await db.get(FeeCategory, category_id)
    if not cat or cat.school_id != school_id or cat.deleted_at:
        raise HTTPException(status_code=404, detail="Category not found")

    # soft-delete the category and any live fee structures using it
    live = (await db.execute(select(FeeStructure).where(
        FeeStructure.school_id == school_id,
        FeeStructure.category_id == category_id,
        FeeStructure.deleted_at.is_(None)))).scalars().all()
    now = datetime.now(timezone.utc)
    for s in live:
        s.deleted_at = now
        s.updated_by = user.id
    cat.deleted_at = now
    cat.updated_by = user.id

    await record_audit(db, school_id=school_id, user_id=user.id, action="delete",
                       table_name="fee_categories", record_id=cat.id,
                       changes={"name": {"old": cat.name, "new": None},
                                "structures_removed": {"old": len(live), "new": 0}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"retired": True, "structures_removed": len(live),
            "note": "Existing invoices are unchanged. Re-issue to apply the new total."}


@router.patch("/structures/{structure_id}", response_model=StructureOut)
async def change_fee_amount(
    structure_id: str, payload: StructureUpdate, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Change what a class pays for a category this term (e.g. a fee increment).
    Existing invoices keep their snapshotted amount until you re-issue."""
    school_id = tenant_scope(user)
    st = await db.get(FeeStructure, structure_id)
    if not st or st.school_id != school_id or st.deleted_at:
        raise HTTPException(status_code=404, detail="Fee not found")
    old = st.amount
    st.amount = payload.amount
    st.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="fee_structures", record_id=st.id,
                       changes={"amount": {"old": old, "new": payload.amount}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(st)
    return st


@router.delete("/structures/{structure_id}")
async def remove_fee(
    structure_id: str, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Remove a fee from a class for this term (soft delete)."""
    school_id = tenant_scope(user)
    st = await db.get(FeeStructure, structure_id)
    if not st or st.school_id != school_id or st.deleted_at:
        raise HTTPException(status_code=404, detail="Fee not found")
    st.deleted_at = datetime.now(timezone.utc)
    st.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="delete",
                       table_name="fee_structures", record_id=st.id,
                       changes={"amount": {"old": st.amount, "new": None}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"removed": True,
            "note": "Existing invoices are unchanged. Re-issue to apply the new total."}


@router.post("/invoices/reissue")
async def reissue_invoices(
    payload: ReissueIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Apply the *current* fee structure to invoices already issued for a class.

    Safety rules, in order:
      - fully paid invoices are left alone (a settled bill stays settled);
      - an invoice is never reduced below what has already been paid;
      - every change is audited old -> new.
    """
    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None

    new_total = (await db.execute(
        select(func.coalesce(func.sum(FeeStructure.amount), 0.0)).where(
            FeeStructure.school_id == school_id,
            FeeStructure.class_id == payload.class_id,
            FeeStructure.term_id == payload.term_id,
            FeeStructure.deleted_at.is_(None)))).scalar() or 0.0

    arms = (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id,
        ClassArm.class_id == payload.class_id,
        ClassArm.deleted_at.is_(None)))).scalars().all()
    arm_ids = [a.id for a in arms]
    if not arm_ids:
        raise HTTPException(status_code=404, detail="No arms in this class")

    students = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id.in_(arm_ids),
        Student.deleted_at.is_(None)))).scalars().all()
    student_ids = [s.id for s in students]
    if not student_ids:
        return {"updated": 0, "skipped_paid": 0, "clamped": 0, "new_total": new_total}

    invoices = (await db.execute(select(Invoice).where(
        Invoice.school_id == school_id,
        Invoice.term_id == payload.term_id,
        Invoice.student_id.in_(student_ids),
        Invoice.deleted_at.is_(None)))).scalars().all()

    updated = skipped_paid = clamped = unchanged = 0
    for inv in invoices:
        paid = await paid_total(db, inv.id)
        if inv.status == InvoiceStatus.PAID and paid >= inv.amount - inv.discount:
            skipped_paid += 1
            continue

        target = new_total
        # never bill a parent for less than they have already handed over
        floor = round(paid + inv.discount, 2)
        if target < floor:
            target = floor
            clamped += 1

        if round(target, 2) == round(inv.amount, 2):
            unchanged += 1
            continue

        old_amount = inv.amount
        inv.amount = round(target, 2)
        inv.updated_by = user.id
        inv.status = status_for(inv.amount, inv.discount, paid)
        await record_audit(db, school_id=school_id, user_id=user.id,
                           action="update", table_name="invoices",
                           record_id=inv.id,
                           changes={"amount": {"old": old_amount, "new": inv.amount}},
                           ip_address=ip)
        updated += 1

    await db.commit()
    return {"new_total": new_total, "updated": updated, "unchanged": unchanged,
            "skipped_paid": skipped_paid, "clamped_to_amount_paid": clamped}


# ---------- Daily reconciliation: paper vs system ----------
@router.get("/reconciliation")
async def reconciliation(
    db: DbDep, user: Annotated[User, FinanceRoles],
    date: str = Query(..., description="YYYY-MM-DD"),
):
    """The end-of-day count: every payment recorded on a date, grouped by
    method and by who recorded it.

    Both the admin and the bursar can record payments, which is exactly how
    cash goes missing between two honest people. This view makes the paper
    ledger and the system agree: each cash payment carries its teller/receipt
    reference and the name of whoever recorded it, so the money in the drawer
    can be counted against a named, referenced list — not a vague total.
    """
    from datetime import date as _date
    try:
        day = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must look like 2026-07-17")

    school_id = tenant_scope(user)
    pays = (await db.execute(select(Payment).where(
        Payment.school_id == school_id,
        Payment.paid_at == day,
        Payment.deleted_at.is_(None)))).scalars().all()

    students = {}
    rows = []
    by_method: dict[str, dict] = {}
    by_recorder: dict[str, dict] = {}
    for p in pays:
        inv = await db.get(Invoice, p.invoice_id)
        st = students.get(inv.student_id) if inv else None
        if inv and not st:
            st = await db.get(Student, inv.student_id)
            students[inv.student_id] = st
        rec = await db.get(User, p.received_by) if p.received_by else None
        method = str(getattr(p.method, "value", p.method))
        rec_name = f"{rec.first_name} {rec.last_name}" if rec else "system (webhook)"

        rows.append({
            "reference": p.reference,
            "student": f"{st.first_name} {st.last_name}" if st else "?",
            "admission_number": st.admission_number if st else "",
            "invoice_number": inv.invoice_number if inv else "",
            "amount": p.amount,
            "method": method,
            "recorded_by": rec_name,
            "payment_id": p.id,
        })
        m = by_method.setdefault(method, {"method": method, "count": 0, "total": 0.0})
        m["count"] += 1
        m["total"] = round(m["total"] + p.amount, 2)
        key = f"{rec_name}|{method}"
        r = by_recorder.setdefault(key, {"recorded_by": rec_name, "method": method,
                                         "count": 0, "total": 0.0})
        r["count"] += 1
        r["total"] = round(r["total"] + p.amount, 2)

    rows.sort(key=lambda r: (r["method"], r["recorded_by"], r["reference"]))
    return {
        "date": date,
        "payments": rows,
        "by_method": sorted(by_method.values(), key=lambda m: -m["total"]),
        "by_recorder": sorted(by_recorder.values(),
                              key=lambda r: (r["recorded_by"], r["method"])),
        "grand_total": round(sum(p.amount for p in pays), 2),
        "count": len(pays),
    }


# ---------- Daily cash reconciliation ----------


@router.get("/invoices/{invoice_id}/payments")
async def invoice_payments(
    invoice_id: str, db: DbDep, user: Annotated[User, FinanceRoles],
):
    """Every payment recorded against one invoice, newest first.

    This is what makes a receipt reprintable at any time: a parent who paid in
    three instalments can be handed evidence for any one of them, long after
    the session in which it was recorded. Part payments and full payments are
    treated identically — each is a real transaction deserving its own receipt.
    """
    school_id = tenant_scope(user)
    inv = await db.get(Invoice, invoice_id)
    if not inv or inv.school_id != school_id or inv.deleted_at:
        raise HTTPException(status_code=404, detail="Invoice not found")

    rows = (await db.execute(select(Payment).where(
        Payment.school_id == school_id,
        Payment.invoice_id == invoice_id,
        Payment.deleted_at.is_(None)))).scalars().all()

    users = {u.id: f"{u.first_name} {u.last_name}"
             for u in (await db.execute(select(User).where(
                 User.school_id == school_id))).scalars().all()}

    out = [{
        "payment_id": p.id,
        "reference": p.reference,
        "receipt_number": f"RCP-{p.reference}",
        "amount": p.amount,
        "method": str(getattr(p.method, "value", p.method)),
        "paid_at": str(p.paid_at) if p.paid_at else None,
        "recorded_by": (users.get(p.received_by) if p.received_by
                        else "system (online payment)"),
    } for p in rows]
    out.sort(key=lambda r: (r["paid_at"] or "", r["reference"]), reverse=True)
    return out


async def _receipt_bytes_for(db, school_id: str, pay: Payment) -> tuple[str, bytes]:
    """Render one payment's receipt, returning (filename, pdf bytes)."""
    inv = await db.get(Invoice, pay.invoice_id)
    student = await db.get(Student, inv.student_id) if inv else None
    school = await db.get(School, school_id)
    receiver = await db.get(User, pay.received_by) if pay.received_by else None
    inv_view = await invoice_view(db, inv) if inv else {
        "amount": 0, "discount": 0, "paid": 0, "balance": 0, "status": ""}

    pdf = build_receipt_pdf({
        "school": {"name": school.name, "address": school.address,
                   "state": school.state, "color": school.primary_color,
                   "logo_url": school.logo_url,
                   "signature_url": school.signature_url,
                   "stamp_url": school.stamp_url,
                   "principal_name": school.principal_name},
        "receipt_number": f"RCP-{pay.reference}",
        "student_name": (f"{student.first_name} {student.last_name}"
                         if student else "?"),
        "admission_number": student.admission_number if student else "",
        "invoice_number": inv.invoice_number if inv else "",
        "method": pay.method, "reference": pay.reference,
        "amount": pay.amount, "paid_at": pay.paid_at,
        "invoice": inv_view,
        "items": await _invoice_items(db, school_id, inv.id) if inv else [],
        "received_by": (f"{receiver.first_name} {receiver.last_name}"
                        if receiver else None),
    })
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                       for ch in str(pay.reference))
    adm = (student.admission_number if student else "unknown").replace("/", "-")
    return f"{adm}_{safe_ref}.pdf", pdf


@router.get("/receipts.zip")
async def bulk_receipts(
    db: DbDep, user: Annotated[User, FinanceRoles],
    date: str | None = Query(None, description="all receipts for one day, YYYY-MM-DD"),
    invoice_id: str | None = Query(None, description="all receipts on one invoice"),
    term_id: str | None = Query(None, description="all receipts for a whole term"),
):
    """Download many receipts at once as a single ZIP.

    Opening a dozen browser tabs is not a filing system. One zip, named per
    student and teller reference, is what a bursar can actually keep: it prints
    in order, files in a folder, and survives an audit.

    Pick exactly one scope: a day (the end-of-day pack), an invoice (one
    family's instalments), or a term.
    """
    import zipfile
    from datetime import date as _date

    school_id = tenant_scope(user)
    scopes = [s for s in (date, invoice_id, term_id) if s]
    if len(scopes) != 1:
        raise HTTPException(
            status_code=400,
            detail="Choose one of: date, invoice_id or term_id")

    stmt = select(Payment).where(Payment.school_id == school_id,
                                 Payment.deleted_at.is_(None))
    label = "receipts"

    if date:
        try:
            day = _date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail="date must look like 2026-07-17")
        stmt = stmt.where(Payment.paid_at == day)
        label = f"receipts-{date}"
    elif invoice_id:
        inv = await db.get(Invoice, invoice_id)
        if not inv or inv.school_id != school_id or inv.deleted_at:
            raise HTTPException(status_code=404, detail="Invoice not found")
        stmt = stmt.where(Payment.invoice_id == invoice_id)
        label = f"receipts-{inv.invoice_number}"
    else:
        invoice_ids = (await db.execute(select(Invoice.id).where(
            Invoice.school_id == school_id,
            Invoice.term_id == term_id,
            Invoice.deleted_at.is_(None)))).scalars().all()
        if not invoice_ids:
            raise HTTPException(status_code=404,
                                detail="No invoices for that term")
        stmt = stmt.where(Payment.invoice_id.in_(invoice_ids))
        label = "receipts-term"

    payments = (await db.execute(stmt)).scalars().all()
    if not payments:
        raise HTTPException(status_code=404,
                            detail="No payments found for that selection")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        seen: set[str] = set()
        for pay in sorted(payments, key=lambda p: str(p.reference)):
            fname, pdf = await _receipt_bytes_for(db, school_id, pay)
            # two payments could share an admission+reference shape; keep both
            base, n = fname, 2
            while fname in seen:
                fname = base.replace(".pdf", f"_{n}.pdf")
                n += 1
            seen.add(fname)
            z.writestr(fname, pdf)

    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{label}.zip"'})
