"""Attendance endpoints.

- Staff mark a whole arm for a day in one call (upsert; corrections audited).
- The daily register and per-student summary are staff-readable; a parent can
  read the summary of their own ward only.
"""
from datetime import date as date_type
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.student import Student, Guardian
from app.models.attendance import Attendance, AttendanceStatus
from app.schemas import MarkAttendanceIn, AttendanceRow, AttendanceSummary
from app.services.audit import record_audit

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


@router.post("/mark")
async def mark_attendance(
    payload: MarkAttendanceIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None
    created = updated = unchanged = 0

    for rec in payload.records:
        existing = (await db.execute(select(Attendance).where(
            Attendance.school_id == school_id,
            Attendance.student_id == rec.student_id,
            Attendance.date == payload.date))).scalars().first()
        if existing:
            if existing.status != rec.status:
                await record_audit(
                    db, school_id=school_id, user_id=user.id, action="update",
                    table_name="attendance", record_id=existing.id,
                    changes={"status": {"old": existing.status, "new": rec.status}},
                    ip_address=ip)
                existing.status = rec.status
                existing.remark = rec.remark
                existing.updated_by = user.id
                updated += 1
            else:
                unchanged += 1
        else:
            db.add(Attendance(
                school_id=school_id, student_id=rec.student_id,
                arm_id=payload.arm_id, date=payload.date, status=rec.status,
                remark=rec.remark, recorded_by=user.id, created_by=user.id))
            created += 1

    await db.commit()
    return {"date": str(payload.date), "created": created,
            "updated": updated, "unchanged": unchanged}


@router.get("/register", response_model=list[AttendanceRow])
async def daily_register(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
    arm_id: str = Query(...),
    date: date_type = Query(...),
):
    school_id = tenant_scope(user)
    rows = (await db.execute(select(Attendance).where(
        Attendance.school_id == school_id,
        Attendance.arm_id == arm_id,
        Attendance.date == date))).scalars().all()
    return [AttendanceRow(student_id=r.student_id, date=r.date,
                          status=r.status, remark=r.remark) for r in rows]


@router.get("/summary", response_model=AttendanceSummary)
async def student_summary(
    db: DbDep, user: CurrentUser,
    student_id: str = Query(...),
    date_from: date_type | None = Query(None),
    date_to: date_type | None = Query(None),
):
    school_id = tenant_scope(user)
    student = await db.get(Student, student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(status_code=404, detail="Student not found")

    # access: staff always; parent only for their own ward; student only for self
    if user.role == Role.PARENT:
        link = (await db.execute(select(Guardian).where(
            Guardian.parent_user_id == user.id,
            Guardian.student_id == student_id))).scalars().first()
        if not link:
            raise HTTPException(status_code=403, detail="Not your ward")
    elif user.role == Role.STUDENT and student.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    stmt = select(Attendance).where(Attendance.school_id == school_id,
                                    Attendance.student_id == student_id)
    if date_from:
        stmt = stmt.where(Attendance.date >= date_from)
    if date_to:
        stmt = stmt.where(Attendance.date <= date_to)
    rows = (await db.execute(stmt)).scalars().all()

    counts = {s: 0 for s in AttendanceStatus}
    for r in rows:
        counts[AttendanceStatus(r.status)] += 1
    return AttendanceSummary(
        student_id=student_id, days_recorded=len(rows),
        present=counts[AttendanceStatus.PRESENT],
        absent=counts[AttendanceStatus.ABSENT],
        late=counts[AttendanceStatus.LATE],
        excused=counts[AttendanceStatus.EXCUSED])
