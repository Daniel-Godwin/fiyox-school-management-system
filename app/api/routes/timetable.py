"""Timetable endpoints.

The value of a timetable is that it is *consistent*. Two rules are enforced on
every write, and they are the whole point:

  1. **An arm cannot be in two lessons at once** — JSS1 A cannot have Maths and
     English in Period 2 on Monday.
  2. **A teacher cannot be in two classrooms at once** — Mr Bello cannot teach
     JSS1 A and JSS2 B in the same slot. This is the clash a paper timetable
     always hides until the first week of term.

A slot may be timetabled before a teacher is assigned to it (teacher_id is
optional), so a school can lay out the grid first and staff it afterwards.
"""
from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep, require_roles, tenant_scope
from app.models.academics import ClassArm, SchoolClass, Subject
from app.models.school import Role, User
from app.models.timetable import WEEKDAY_ORDER, Lesson, Period, Weekday
from app.services.audit import record_audit

router = APIRouter(prefix="/api/timetable", tags=["timetable"])

AdminOnly = Depends(require_roles(Role.SCHOOL_ADMIN))


# ---------------------------------------------------------------- schemas

class PeriodIn(BaseModel):
    name: str = Field(examples=["Period 1"])
    sequence: int = 0
    start_time: str | None = None      # "08:00"
    end_time: str | None = None        # "08:40"
    is_break: bool = False


class LessonIn(BaseModel):
    arm_id: str
    day: Weekday
    period_id: str
    subject_id: str
    teacher_id: str | None = None
    room: str | None = None


def _parse(t: str | None) -> time | None:
    if not t:
        return None
    try:
        hh, mm = t.split(":")[:2]
        return time(int(hh), int(mm))
    except Exception:
        raise HTTPException(status_code=400,
                            detail="Times must look like 08:00")


def _fmt(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


# ---------------------------------------------------------------- periods

@router.post("/periods", status_code=status.HTTP_201_CREATED)
async def create_period(payload: PeriodIn, db: DbDep,
                        user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    clash = (await db.execute(select(Period).where(
        Period.school_id == school_id,
        Period.sequence == payload.sequence,
        Period.deleted_at.is_(None)))).scalars().first()
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"'{clash.name}' already occupies row {payload.sequence}")

    p = Period(school_id=school_id, name=payload.name, sequence=payload.sequence,
               start_time=_parse(payload.start_time),
               end_time=_parse(payload.end_time),
               is_break=payload.is_break, created_by=user.id)
    db.add(p)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409,
                            detail=f"Row {payload.sequence} was just taken — refresh and try again")
    await db.refresh(p)
    return {"id": p.id, "name": p.name, "sequence": p.sequence,
            "start_time": _fmt(p.start_time), "end_time": _fmt(p.end_time),
            "is_break": p.is_break}


@router.get("/periods")
async def list_periods(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    rows = (await db.execute(select(Period).where(
        Period.school_id == school_id,
        Period.deleted_at.is_(None)).order_by(Period.sequence))).scalars().all()
    return [{"id": p.id, "name": p.name, "sequence": p.sequence,
             "start_time": _fmt(p.start_time), "end_time": _fmt(p.end_time),
             "is_break": p.is_break} for p in rows]


@router.delete("/periods/{period_id}")
async def delete_period(period_id: str, db: DbDep,
                        user: Annotated[User, AdminOnly]):
    from datetime import datetime, timezone
    school_id = tenant_scope(user)
    p = await db.get(Period, period_id)
    if not p or p.school_id != school_id or p.deleted_at:
        raise HTTPException(status_code=404, detail="Period not found")

    lessons = (await db.execute(select(Lesson).where(
        Lesson.school_id == school_id, Lesson.period_id == period_id,
        Lesson.deleted_at.is_(None)))).scalars().all()
    now = datetime.now(timezone.utc)
    for lsn in lessons:
        lsn.deleted_at = now
    p.deleted_at = now
    await db.commit()
    return {"removed": True, "lessons_removed": len(lessons)}


# ---------------------------------------------------------------- lessons

@router.post("/lessons", status_code=status.HTTP_201_CREATED)
async def schedule_lesson(payload: LessonIn, request: Request, db: DbDep,
                          user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)

    period = await db.get(Period, payload.period_id)
    if not period or period.school_id != school_id:
        raise HTTPException(status_code=404, detail="Period not found")
    if period.is_break:
        raise HTTPException(status_code=400,
                            detail=f"'{period.name}' is a break — no lesson can be scheduled in it")

    arm = await db.get(ClassArm, payload.arm_id)
    if not arm or arm.school_id != school_id:
        raise HTTPException(status_code=404, detail="Class not found")
    subject = await db.get(Subject, payload.subject_id)
    if not subject or subject.school_id != school_id:
        raise HTTPException(status_code=404, detail="Subject not found")

    # RULE 1: the arm is already busy in this slot?
    busy_arm = (await db.execute(select(Lesson).where(
        Lesson.school_id == school_id, Lesson.arm_id == payload.arm_id,
        Lesson.day == payload.day, Lesson.period_id == payload.period_id,
        Lesson.deleted_at.is_(None)))).scalars().first()
    if busy_arm:
        existing_subject = await db.get(Subject, busy_arm.subject_id)
        raise HTTPException(
            status_code=409,
            detail=(f"This class already has "
                    f"{existing_subject.name if existing_subject else 'a lesson'} "
                    f"in {period.name} on {payload.day.value.title()}."))

    # RULE 2: the teacher is already teaching elsewhere in this slot?
    if payload.teacher_id:
        teacher = await db.get(User, payload.teacher_id)
        if not teacher or teacher.school_id != school_id or teacher.role != Role.TEACHER:
            raise HTTPException(status_code=404, detail="Teacher not found")

        busy_teacher = (await db.execute(select(Lesson).where(
            Lesson.school_id == school_id,
            Lesson.teacher_id == payload.teacher_id,
            Lesson.day == payload.day, Lesson.period_id == payload.period_id,
            Lesson.deleted_at.is_(None)))).scalars().first()
        if busy_teacher:
            other_arm = await db.get(ClassArm, busy_teacher.arm_id)
            other_class = (await db.get(SchoolClass, other_arm.class_id)
                           if other_arm else None)
            label = (f"{other_class.name} {other_arm.name}"
                     if other_arm and other_class else "another class")
            raise HTTPException(
                status_code=409,
                detail=(f"{teacher.first_name} {teacher.last_name} is already "
                        f"teaching {label} in {period.name} on "
                        f"{payload.day.value.title()}."))

    lsn = Lesson(school_id=school_id, arm_id=payload.arm_id, day=payload.day,
                 period_id=payload.period_id, subject_id=payload.subject_id,
                 teacher_id=payload.teacher_id, room=payload.room,
                 created_by=user.id)
    db.add(lsn)
    await db.flush()
    await record_audit(db, school_id=school_id, user_id=user.id, action="create",
                       table_name="lessons", record_id=lsn.id,
                       changes={"subject": {"old": None, "new": subject.name},
                                "slot": {"old": None,
                                         "new": f"{payload.day.value} {period.name}"}},
                       ip_address=request.client.host if request.client else None)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409,
                            detail="That slot was just filled by someone else — refresh the grid")
    return {"id": lsn.id}


@router.delete("/lessons/{lesson_id}")
async def remove_lesson(lesson_id: str, db: DbDep,
                        user: Annotated[User, AdminOnly]):
    from datetime import datetime, timezone
    school_id = tenant_scope(user)
    lsn = await db.get(Lesson, lesson_id)
    if not lsn or lsn.school_id != school_id or lsn.deleted_at:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lsn.deleted_at = datetime.now(timezone.utc)
    lsn.updated_by = user.id
    await db.commit()
    return {"removed": True}


@router.get("")
async def get_timetable(
    db: DbDep, user: CurrentUser,
    arm_id: str | None = Query(None),
    teacher_id: str | None = Query(None),
):
    """The week's grid — for a class, or for a teacher (their personal timetable).

    A teacher with no arguments gets their own; a parent or student gets their
    ward's class. Everyone sees a timetable that concerns them.
    """
    school_id = tenant_scope(user)

    # teachers default to their own timetable
    if not arm_id and not teacher_id and user.role == Role.TEACHER:
        teacher_id = user.id

    # ---- families: a parent may have SEVERAL children in the school ----
    # Return every ward's class, and let a parent ask only for a class one of
    # their own children actually sits in. The arm is derived from the family,
    # never taken on trust from the request.
    wards: list[dict] = []
    if user.role in (Role.PARENT, Role.STUDENT):
        from app.models.student import Guardian, Student

        if user.role == Role.STUDENT:
            students = (await db.execute(select(Student).where(
                Student.school_id == school_id,
                Student.user_id == user.id,
                Student.deleted_at.is_(None)))).scalars().all()
        else:
            links = (await db.execute(select(Guardian).where(
                Guardian.school_id == school_id,
                Guardian.parent_user_id == user.id))).scalars().all()
            students = []
            for link in links:
                st = await db.get(Student, link.student_id)
                if st and st.deleted_at is None and st.current_arm_id:
                    students.append(st)

        allowed_arms = {s.current_arm_id for s in students if s.current_arm_id}

        if arm_id and arm_id not in allowed_arms:
            raise HTTPException(
                status_code=403,
                detail="You can only view the timetable of a class your child is in")

        # a parent may not browse teachers' personal timetables
        teacher_id = None

        for s in students:
            wards.append({"student_id": s.id,
                          "name": f"{s.first_name} {s.last_name}",
                          "arm_id": s.current_arm_id})

        if not arm_id:
            # no class chosen: show every ward's lessons, tagged by class
            arm_filter = list(allowed_arms)
        else:
            arm_filter = [arm_id]
    else:
        arm_filter = [arm_id] if arm_id else []

    stmt = select(Lesson).where(Lesson.school_id == school_id,
                                Lesson.deleted_at.is_(None))
    if arm_filter:
        stmt = stmt.where(Lesson.arm_id.in_(arm_filter))
    if teacher_id:
        stmt = stmt.where(Lesson.teacher_id == teacher_id)
    lessons = (await db.execute(stmt)).scalars().all()

    periods = (await db.execute(select(Period).where(
        Period.school_id == school_id,
        Period.deleted_at.is_(None)).order_by(Period.sequence))).scalars().all()
    subjects = {s.id: s.name for s in (await db.execute(select(Subject).where(
        Subject.school_id == school_id))).scalars().all()}
    teachers = {u.id: f"{u.first_name} {u.last_name}"
                for u in (await db.execute(select(User).where(
                    User.school_id == school_id))).scalars().all()}
    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id))).scalars().all()}

    def arm_label(aid: str) -> str:
        a = arms.get(aid)
        return f"{classes.get(a.class_id, '')} {a.name}".strip() if a else "?"

    return {
        "wards": wards,              # every child this caller may view
        "days": WEEKDAY_ORDER[:5],   # Mon-Fri; Saturday only if a school uses it
        "periods": [{"id": p.id, "name": p.name, "sequence": p.sequence,
                     "start_time": _fmt(p.start_time), "end_time": _fmt(p.end_time),
                     "is_break": p.is_break} for p in periods],
        "lessons": [{
            "id": l.id,
            "arm_id": l.arm_id,
            "arm_label": arm_label(l.arm_id),
            "day": l.day.value if hasattr(l.day, "value") else str(l.day),
            "period_id": l.period_id,
            "subject_id": l.subject_id,
            "subject_name": subjects.get(l.subject_id, "?"),
            "teacher_id": l.teacher_id,
            "teacher_name": teachers.get(l.teacher_id) if l.teacher_id else None,
            "room": l.room,
        } for l in lessons],
    }
