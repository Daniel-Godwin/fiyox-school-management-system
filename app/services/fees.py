"""Finance business logic.

Balance is always derived (amount - discount - payments); status follows from
balance. Payments are idempotent by (school_id, reference).
"""
from datetime import date
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.academics import ClassArm
from app.models.student import Student
from app.models.fees import (
    FeeStructure, Invoice, Payment, InvoiceStatus,
)
from app.services.audit import record_audit


async def paid_total(db: AsyncSession, invoice_id: str) -> float:
    total = (await db.execute(select(func.coalesce(func.sum(Payment.amount), 0.0))
                              .where(Payment.invoice_id == invoice_id))).scalar()
    return float(total or 0.0)


def status_for(amount: float, discount: float, paid: float) -> InvoiceStatus:
    due = round(amount - discount, 2)
    if paid <= 0:
        return InvoiceStatus.UNPAID
    if paid >= due:
        return InvoiceStatus.PAID
    return InvoiceStatus.PART_PAID


async def invoice_breakdown(db: AsyncSession, inv: Invoice) -> list[dict]:
    """What an invoice's total is made up of, shown by default.

    Order of trust:

    1. **Stored lines** (`invoice_items`) — snapshotted when the invoice was
       issued. Authoritative: exactly what the parent was billed.
    2. **Derived from the class's fee categories** — for invoices issued before
       Fiyox stored lines. The categories and amounts set up for the student's
       class and term ARE the breakdown.

    A parent should always see what the fees are for. So when the categories do
    not add up to the exact invoice total — because of a discount, a rounding,
    or a fee edited after billing — we do not throw the whole breakdown away.
    We show the categories AND reconcile the gap as one honest line
    ("Discount applied" when the bill is lower, "Other / adjustment" when it is
    higher), so the lines always sum to the amount actually billed.
    """
    from app.models.fees import FeeCategory, FeeStructure, InvoiceItem

    stored = (await db.execute(select(InvoiceItem).where(
        InvoiceItem.invoice_id == inv.id,
        InvoiceItem.deleted_at.is_(None)))).scalars().all()
    if stored:
        return [{"name": r.category_name, "amount": r.amount}
                for r in sorted(stored, key=lambda x: (-x.amount, x.category_name))]

    student = await db.get(Student, inv.student_id)
    arm = (await db.get(ClassArm, student.current_arm_id)
           if student and student.current_arm_id else None)
    if not arm:
        return []

    structures = (await db.execute(select(FeeStructure).where(
        FeeStructure.school_id == inv.school_id,
        FeeStructure.class_id == arm.class_id,
        FeeStructure.term_id == inv.term_id))).scalars().all()
    if not structures:
        return []

    names = {c.id: c.name for c in (await db.execute(select(FeeCategory).where(
        FeeCategory.school_id == inv.school_id))).scalars().all()}
    lines = [{"name": names.get(s.category_id, "Fee"), "amount": float(s.amount)}
             for s in structures if float(s.amount) != 0]
    lines.sort(key=lambda x: (-x["amount"], x["name"]))

    # reconcile the categories to the amount actually billed, so the breakdown
    # always adds up — a discount or a later fee tweak becomes its own line
    billed = round(float(inv.amount), 2)
    cat_total = round(sum(l["amount"] for l in lines), 2)
    diff = round(billed - cat_total, 2)
    if diff < 0:
        lines.append({"name": "Discount applied", "amount": diff})
    elif diff > 0:
        lines.append({"name": "Other / adjustment", "amount": diff})

    return lines


async def invoice_view(db: AsyncSession, inv: Invoice) -> dict:
    paid = await paid_total(db, inv.id)

    # what the total is made up of — stored lines, or safely derived
    lines = await invoice_breakdown(db, inv)

    return {
        "id": inv.id, "student_id": inv.student_id, "term_id": inv.term_id,
        "invoice_number": inv.invoice_number, "amount": inv.amount,
        "discount": inv.discount, "paid": round(paid, 2),
        "balance": round(inv.amount - inv.discount - paid, 2),
        "status": inv.status, "due_date": inv.due_date,
        "items": lines,
    }


async def generate_invoices(db: AsyncSession, school_id: str, user_id: str,
                            arm_id: str, term_id: str,
                            due_date: date | None = None,
                            ip: str | None = None) -> dict:
    """Create one invoice per student in the arm, totalling the class's fee
    structures for the term. Students already invoiced for the term are skipped."""
    arm = await db.get(ClassArm, arm_id)
    if not arm or arm.school_id != school_id:
        return {"error": "arm not found"}

    structures = (await db.execute(select(FeeStructure).where(
        FeeStructure.school_id == school_id,
        FeeStructure.class_id == arm.class_id,
        FeeStructure.term_id == term_id))).scalars().all()
    total = float(sum(s.amount for s in structures))
    if total <= 0:
        return {"error": "no fee structure defined for this class and term"}

    # category names are copied onto each invoice line, so a later rename or
    # deletion cannot rewrite what a parent was billed
    from app.models.fees import FeeCategory as _Cat, InvoiceItem as _Item
    cat_names = {c.id: c.name for c in (await db.execute(select(_Cat).where(
        _Cat.school_id == school_id))).scalars().all()}

    students = (await db.execute(select(Student).where(
        Student.school_id == school_id, Student.current_arm_id == arm_id,
        Student.deleted_at.is_(None),
        Student.is_active == True))).scalars().all()  # noqa: E712

    existing = set((await db.execute(select(Invoice.student_id).where(
        Invoice.school_id == school_id, Invoice.term_id == term_id))).scalars().all())

    seq = (await db.execute(select(func.count(Invoice.id)).where(
        Invoice.school_id == school_id))).scalar() or 0

    created = skipped = 0
    for st in students:
        if st.id in existing:
            skipped += 1
            continue
        seq += 1
        inv = Invoice(school_id=school_id, student_id=st.id, term_id=term_id,
                      invoice_number=f"INV-{seq:05d}", amount=float(total),
                      due_date=due_date, created_by=user_id)
        db.add(inv)
        await db.flush()

        for s in structures:
            db.add(_Item(school_id=school_id, invoice_id=inv.id,
                         category_id=s.category_id,
                         category_name=cat_names.get(s.category_id, "Fee"),
                         amount=float(s.amount), created_by=user_id))

        await record_audit(db, school_id=school_id, user_id=user_id, action="create",
                           table_name="invoices", record_id=inv.id,
                           changes={"amount": {"old": None, "new": float(total)},
                                    "student_id": {"old": None, "new": st.id}},
                           ip_address=ip)
        created += 1

    await db.commit()
    return {"created": created, "skipped_already_invoiced": skipped,
            "amount_per_student": float(total)}


async def record_payment(db: AsyncSession, school_id: str, user_id: str,
                         *, invoice_id: str, method, reference: str,
                         amount: float, paid_at: date | None = None,
                         ip: str | None = None) -> tuple[dict | None, str | None]:
    inv = await db.get(Invoice, invoice_id)
    if not inv or inv.school_id != school_id:
        return None, "invoice not found"

    # idempotency: same reference returns the existing payment, records nothing new
    dup = (await db.execute(select(Payment).where(
        Payment.school_id == school_id,
        Payment.reference == reference))).scalars().first()
    if dup:
        return {"payment_id": dup.id, "duplicate": True,
                "invoice": await invoice_view(db, inv)}, None

    pay = Payment(school_id=school_id, invoice_id=invoice_id, method=method,
                  reference=reference, amount=float(amount),
                  paid_at=paid_at or date.today(), received_by=user_id,
                  created_by=user_id)
    db.add(pay)
    await db.flush()

    paid = await paid_total(db, invoice_id)
    old_status = inv.status
    inv.status = status_for(inv.amount, inv.discount, paid)
    inv.updated_by = user_id

    await record_audit(db, school_id=school_id, user_id=user_id, action="create",
                       table_name="payments", record_id=pay.id,
                       changes={"amount": {"old": None, "new": float(amount)},
                                "reference": {"old": None, "new": reference},
                                "invoice_status": {"old": old_status, "new": inv.status}},
                       ip_address=ip)
    await db.commit()
    return {"payment_id": pay.id, "duplicate": False,
            "invoice": await invoice_view(db, inv)}, None


async def has_outstanding_debt(db: AsyncSession, school_id: str,
                               student_id: str, term_id: str) -> bool:
    """True if the student has an invoice for this term with a positive balance.
    No invoice = no debt (school hasn't billed them)."""
    inv = (await db.execute(select(Invoice).where(
        Invoice.school_id == school_id, Invoice.student_id == student_id,
        Invoice.term_id == term_id))).scalars().first()
    if not inv:
        return False
    paid = await paid_total(db, inv.id)
    return (inv.amount - inv.discount - paid) > 0.009
