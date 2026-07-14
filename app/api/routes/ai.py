"""AI endpoints — assistive, never authoritative.

Both of these produce *suggestions for a human*. The teacher can overwrite any
comment (and their edit survives recompute); the at-risk register is a list for
a head teacher to act on, not a verdict on a child.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.academics import ClassArm, SchoolClass, Subject, Term
from app.models.fees import Invoice
from app.models.results import SubjectResult, TermResult
from app.models.school import Role, User
from app.models.student import Student
from app.services.ai import assess_risk, llm_comments, llm_configured
from app.services.audit import record_audit
from app.services.fees import paid_total

router = APIRouter(prefix="/api/ai", tags=["ai"])

StaffOnly = Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER))
AdminOnly = Depends(require_roles(Role.SCHOOL_ADMIN))


class RegenerateIn(BaseModel):
    arm_id: str
    term_id: str
    # only rewrite comments a human has not already edited
    keep_edited: bool = True


@router.get("/status")
async def ai_status(user: Annotated[User, StaffOnly]):
    return {
        "llm_configured": llm_configured(),
        "message": ("AI comments are available."
                    if llm_configured() else
                    "AI comments are off. Fiyox writes comments with its built-in "
                    "engine instead — set ANTHROPIC_API_KEY to enable richer, "
                    "subject-aware comments."),
    }


@router.post("/comments/regenerate")
async def regenerate_comments(
    payload: RegenerateIn, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    """Rewrite the report-card comments for a class using the AI, reasoning over
    each student's subject-by-subject profile. Falls back to the built-in engine
    per student if the API is unavailable — printing report cards never fails."""
    school_id = tenant_scope(admin)

    results = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == payload.arm_id,
        TermResult.term_id == payload.term_id))).scalars().all()
    if not results:
        raise HTTPException(status_code=404,
                            detail="No computed results for this class and term")

    subjects = {s.id: s.name for s in (await db.execute(select(Subject).where(
        Subject.school_id == school_id))).scalars().all()}

    ai_count = rules_count = skipped = 0
    for tr in results:
        if payload.keep_edited and tr.comments_edited:
            skipped += 1
            continue

        student = await db.get(Student, tr.student_id)
        if not student:
            continue

        rows = (await db.execute(select(SubjectResult).where(
            SubjectResult.school_id == school_id,
            SubjectResult.student_id == tr.student_id,
            SubjectResult.term_id == payload.term_id))).scalars().all()
        profile = [{"subject": subjects.get(r.subject_id, "?"),
                    "total": r.total, "grade": r.grade,
                    "class_average": r.class_average} for r in rows]

        teacher, principal, source = await llm_comments(
            first_name=student.first_name, subjects=profile,
            average=tr.average, position=tr.overall_position,
            class_size=tr.class_size, class_average=tr.class_average)

        tr.form_teacher_comment = teacher
        tr.principal_comment = principal
        tr.updated_by = admin.id
        # AI text is a suggestion, not a human edit: a later recompute may
        # refresh it, and a teacher's own words still take precedence
        if source == "ai":
            ai_count += 1
        else:
            rules_count += 1

    await record_audit(db, school_id=school_id, user_id=admin.id, action="update",
                       table_name="term_results", record_id=None,
                       changes={"comments": {"old": None,
                                             "new": f"regenerated ({ai_count} ai, "
                                                    f"{rules_count} rules)"}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"ai_written": ai_count, "rules_written": rules_count,
            "kept_human_edits": skipped,
            "note": ("AI is not configured — the built-in engine was used."
                     if not llm_configured() else None)}


@router.get("/at-risk")
async def at_risk_register(
    db: DbDep, user: Annotated[User, StaffOnly],
    term_id: str = Query(...),
    arm_id: str | None = Query(None),
):
    """Students who need attention, with the reasons spelled out.

    Signals: weak or falling average, failing several subjects, poor attendance,
    outstanding fees. No black box — a head teacher can challenge every flag.
    """
    school_id = tenant_scope(user)

    stmt = select(TermResult).where(TermResult.school_id == school_id,
                                    TermResult.term_id == term_id)
    if arm_id:
        stmt = stmt.where(TermResult.arm_id == arm_id)
    results = (await db.execute(stmt)).scalars().all()

    # previous term (by start date) for trend detection
    this_term = await db.get(Term, term_id)
    prev_term = None
    if this_term and this_term.start_date:
        prev_term = (await db.execute(select(Term).where(
            Term.school_id == school_id,
            Term.start_date < this_term.start_date,
            Term.deleted_at.is_(None)).order_by(
                Term.start_date.desc()))).scalars().first()

    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id))).scalars().all()}

    from app.models.attendance import Attendance, AttendanceStatus

    register = []
    for tr in results:
        student = await db.get(Student, tr.student_id)
        if not student or not student.is_active:
            continue

        subject_rows = (await db.execute(select(SubjectResult).where(
            SubjectResult.school_id == school_id,
            SubjectResult.student_id == tr.student_id,
            SubjectResult.term_id == term_id))).scalars().all()
        failing = sum(1 for r in subject_rows if r.total < 40)

        # attendance
        att_rows = (await db.execute(select(Attendance).where(
            Attendance.school_id == school_id,
            Attendance.student_id == tr.student_id))).scalars().all()
        att_pct = None
        if att_rows:
            present = sum(1 for r in att_rows
                          if str(getattr(r.status, "value", r.status))
                          in ("present", "late"))
            att_pct = round(present / len(att_rows) * 100, 1)

        # fees
        inv = (await db.execute(select(Invoice).where(
            Invoice.school_id == school_id,
            Invoice.student_id == tr.student_id,
            Invoice.term_id == term_id,
            Invoice.deleted_at.is_(None)))).scalars().first()
        owes = False
        if inv:
            paid = await paid_total(db, inv.id)
            owes = round(inv.amount - inv.discount - paid, 2) > 0

        # trend
        prev_avg = None
        if prev_term:
            prev = (await db.execute(select(TermResult).where(
                TermResult.school_id == school_id,
                TermResult.student_id == tr.student_id,
                TermResult.term_id == prev_term.id))).scalars().first()
            prev_avg = prev.average if prev else None

        risk = assess_risk(
            average=tr.average, class_average=tr.class_average,
            failing_subjects=failing, subjects_count=len(subject_rows),
            attendance_pct=att_pct, previous_average=prev_avg, owes_fees=owes)

        if risk["level"] == "none":
            continue    # doing fine: not on a list of children needing help

        arm = arms.get(tr.arm_id)
        register.append({
            "student_id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "admission_number": student.admission_number,
            "class_label": (f"{classes.get(arm.class_id, '')} {arm.name}".strip()
                            if arm else "?"),
            "average": tr.average,
            "position": tr.overall_position,
            "class_size": tr.class_size,
            "attendance_pct": att_pct,
            "owes_fees": owes,
            **risk,
        })

    order = {"high": 0, "moderate": 1, "watch": 2}
    return sorted(register, key=lambda r: (order[r["level"]], -r["score"]))
