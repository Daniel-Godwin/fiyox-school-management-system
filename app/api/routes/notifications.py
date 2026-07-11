"""Notification endpoints.

- POST /api/notifications/announcements/{id}/send — SMS an announcement to its
  target group (recipients = active users of that role with a phone number).
- POST /api/notifications/fee-reminders — SMS the guardians of every student
  with an outstanding balance for a term.
- GET  /api/notifications/logs — the delivery trail.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import School, User, Role
from app.models.communication import Announcement
from app.models.fees import Invoice
from app.models.notifications import MessageLog, MessagePurpose
from app.schemas import FeeReminderIn, MessageLogOut
from app.services.fees import paid_total
from app.services.notify import (
    send_sms_and_log, recipients_for_target, guardians_of, student_name,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.post("/announcements/{announcement_id}/send")
async def send_announcement(
    announcement_id: str, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    ann = await db.get(Announcement, announcement_id)
    if not ann or ann.school_id != school_id:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if ann.published_at is None:
        raise HTTPException(status_code=400, detail="Publish the announcement before sending")

    school = await db.get(School, school_id)
    recipients = await recipients_for_target(db, school_id, ann.target)
    body = f"{school.name}: {ann.title} — {ann.message}"

    sent = 0
    for r in recipients:
        await send_sms_and_log(
            db, school_id=school_id, to=r.phone, body=body,
            purpose=MessagePurpose.ANNOUNCEMENT, recipient_user_id=r.id,
            related_id=ann.id, created_by=user.id)
        sent += 1
    await db.commit()
    return {"announcement_id": ann.id, "target": ann.target, "recipients": sent}


@router.post("/fee-reminders")
async def send_fee_reminders(
    payload: FeeReminderIn, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.BURSAR, Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)

    invoices = (await db.execute(select(Invoice).where(
        Invoice.school_id == school_id,
        Invoice.term_id == payload.term_id,
        Invoice.deleted_at.is_(None)))).scalars().all()

    reminded_students = 0
    messages = 0
    for inv in invoices:
        paid = await paid_total(db, inv.id)
        balance = round(inv.amount - inv.discount - paid, 2)
        if balance <= 0:
            continue
        parents = await guardians_of(db, school_id, inv.student_id)
        if not parents:
            continue
        name = await student_name(db, inv.student_id)
        body = (f"{school.name}: Fee reminder for {name} "
                f"(invoice {inv.invoice_number}). Outstanding balance: "
                f"NGN {balance:,.2f}. Kindly complete payment.")
        for p in parents:
            await send_sms_and_log(
                db, school_id=school_id, to=p.phone, body=body,
                purpose=MessagePurpose.FEE_REMINDER, recipient_user_id=p.id,
                related_id=inv.id, created_by=user.id)
            messages += 1
        reminded_students += 1

    await db.commit()
    return {"students_with_debt_reminded": reminded_students, "messages": messages}


@router.get("/logs", response_model=list[MessageLogOut])
async def delivery_logs(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.BURSAR, Role.SCHOOL_ADMIN))],
    purpose: MessagePurpose | None = Query(None),
    limit: int = Query(50, le=200),
):
    school_id = tenant_scope(user)
    stmt = select(MessageLog).where(MessageLog.school_id == school_id)
    if purpose:
        stmt = stmt.where(MessageLog.purpose == purpose)
    stmt = stmt.order_by(MessageLog.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
