"""Automatic parent notifications — result published and payment received.

When a school publishes a term's results or records a fee payment, the student's
parent/guardian is told right away over whatever channels they have on file: an
SMS if a phone number is set, an email if an address is set. Every message is
written to the delivery log (same as announcements and fee reminders), so a
school can see exactly what went out.

Both entry points are best-effort: the send/log helpers never raise (a provider
failure is recorded as a FAILED message, not an exception), and the caller only
reaches here after its own action has committed, so a notification can never
undo a publish or a payment. Notifications are skipped entirely when the school
has switched `parent_notifications_enabled` off.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.school import School, User
from app.models.student import Student, Guardian
from app.models.notifications import MessagePurpose
from app.services.notify import send_sms_and_log, send_email_and_log, normalize_msisdn


async def _guardians_for(db: AsyncSession, school_id: str,
                         student_ids: list[str]) -> dict[str, User]:
    """The primary guardian (preferring one with a phone) for each student."""
    if not student_ids:
        return {}
    links = (await db.execute(select(Guardian).where(
        Guardian.school_id == school_id,
        Guardian.student_id.in_(student_ids)))).scalars().all()
    parent_ids = {g.parent_user_id for g in links}
    parents = {u.id: u for u in (await db.execute(select(User).where(
        User.id.in_(parent_ids)))).scalars().all()} if parent_ids else {}
    chosen: dict[str, User] = {}
    for g in links:
        p = parents.get(g.parent_user_id)
        if not p:
            continue
        cur = chosen.get(g.student_id)
        if cur is None or (not cur.phone and p.phone):
            chosen[g.student_id] = p
    return chosen


async def _send_to_guardian(db: AsyncSession, *, school_id: str, guardian: User,
                            sms_body: str, email_subject: str, email_body: str,
                            purpose: MessagePurpose, related_id: str | None,
                            created_by: str | None) -> int:
    """Send over every channel the guardian has. Returns messages sent."""
    sent = 0
    if guardian.phone:
        await send_sms_and_log(
            db, school_id=school_id, to=normalize_msisdn(guardian.phone),
            body=sms_body, purpose=purpose, recipient_user_id=guardian.id,
            related_id=related_id, created_by=created_by)
        sent += 1
    if guardian.email:
        await send_email_and_log(
            db, school_id=school_id, to=guardian.email,
            subject=email_subject, body=email_body, purpose=purpose,
            recipient_user_id=guardian.id, related_id=related_id,
            created_by=created_by)
        sent += 1
    return sent


async def notify_result_published(db: AsyncSession, *, school_id: str,
                                  students: dict[str, str], term_label: str,
                                  created_by: str | None = None) -> dict:
    """Tell each student's parent their term result is out.

    `students` maps student_id -> student display name. Caller passes only the
    students whose results were newly published.
    """
    school = await db.get(School, school_id)
    if not school or not school.parent_notifications_enabled:
        return {"notified": 0, "messages": 0, "skipped_no_contact": 0, "enabled": False}

    guardians = await _guardians_for(db, school_id, list(students))
    name = school.name if school else "the school"
    notified = messages = skipped = 0
    for sid, student_name in students.items():
        g = guardians.get(sid)
        if not g or (not g.phone and not g.email):
            skipped += 1
            continue
        who = f"{g.first_name} {g.last_name}".strip() or "Parent/Guardian"
        term = f"{term_label} " if term_label else ""
        sms = (f"Dear {who}, the {term}result for {student_name} at {name} has "
               f"been published. Log in to the parent portal to view it.")
        email_body = (
            f"Dear {who},\n\n"
            f"The {term}result for {student_name} at {name} has been published. "
            f"You can now log in to the parent portal to view and download the "
            f"report card.\n\nThank you.")
        sent = await _send_to_guardian(
            db, school_id=school_id, guardian=g, sms_body=sms,
            email_subject=f"Result published — {student_name}",
            email_body=email_body, purpose=MessagePurpose.RESULT_PUBLISHED,
            related_id=sid, created_by=created_by)
        if sent:
            notified += 1
            messages += sent
        else:
            skipped += 1
    return {"notified": notified, "messages": messages,
            "skipped_no_contact": skipped, "enabled": True}


async def notify_payment_received(db: AsyncSession, *, school_id: str,
                                  student_id: str, amount: float, balance: float,
                                  invoice_number: str, payment_id: str | None,
                                  created_by: str | None = None) -> dict:
    """Confirm a recorded fee payment to the student's parent."""
    school = await db.get(School, school_id)
    if not school or not school.parent_notifications_enabled:
        return {"notified": 0, "messages": 0, "enabled": False}

    student = await db.get(Student, student_id)
    if not student:
        return {"notified": 0, "messages": 0, "enabled": True}
    guardians = await _guardians_for(db, school_id, [student_id])
    g = guardians.get(student_id)
    if not g or (not g.phone and not g.email):
        return {"notified": 0, "messages": 0, "enabled": True}

    name = school.name if school else "the school"
    who = f"{g.first_name} {g.last_name}".strip() or "Parent/Guardian"
    student_name = f"{student.first_name} {student.last_name}"
    bal_txt = ("Your balance is fully paid." if balance <= 0
               else f"Outstanding balance: NGN {balance:,.2f}.")
    sms = (f"Dear {who}, {name} confirms payment of NGN {amount:,.2f} for "
           f"{student_name} (Invoice {invoice_number}). {bal_txt} Thank you.")
    email_body = (
        f"Dear {who},\n\n"
        f"{name} confirms receipt of a payment of NGN {amount:,.2f} towards the "
        f"school fees for {student_name} (Invoice {invoice_number}).\n\n{bal_txt}\n\n"
        f"Thank you.")
    sent = await _send_to_guardian(
        db, school_id=school_id, guardian=g, sms_body=sms,
        email_subject=f"Payment received — {student_name}",
        email_body=email_body, purpose=MessagePurpose.PAYMENT_RECEIVED,
        related_id=payment_id, created_by=created_by)
    return {"notified": 1 if sent else 0, "messages": sent, "enabled": True}
