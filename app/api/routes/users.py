"""User administration — how a school gets its people into Fiyox.

The school admin creates accounts for teachers, bursars, parents and students.
Passwords can be auto-generated (returned once, then the person changes it via
/api/auth/change-password). Parents can be linked to wards at creation or later.
Everything is tenant-scoped and audited.
"""
import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from pydantic import BaseModel
from app.core.deps import DbDep, require_roles, tenant_scope
from app.core.security import hash_password
from app.models.school import User, Role
from app.models.student import Student, Guardian
from app.schemas import (
    UserCreate, UserAdminOut, UserCreatedOut, UserStatusIn, WardLinkIn,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/api/users", tags=["users"])

AdminOnly = Depends(require_roles(Role.SCHOOL_ADMIN))


@router.post("", response_model=UserCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    school_id = tenant_scope(admin)
    ip = request.client.host if request.client else None

    if payload.role == Role.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot create platform admins")

    exists = (await db.execute(select(User).where(
        User.school_id == school_id, User.email == payload.email))).scalars().first()
    if exists:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    temp_password = None
    raw_password = payload.password
    if not raw_password:
        temp_password = secrets.token_urlsafe(8)
        raw_password = temp_password

    user = User(
        school_id=school_id, email=payload.email,
        hashed_password=hash_password(raw_password),
        role=payload.role, first_name=payload.first_name,
        last_name=payload.last_name, phone=payload.phone)
    db.add(user)
    await db.flush()

    # role=student: attach the account to its student record
    if payload.role == Role.STUDENT and payload.student_id:
        student = await db.get(Student, payload.student_id)
        if not student or student.school_id != school_id:
            raise HTTPException(status_code=404, detail="Student record not found")
        student.user_id = user.id
        student.updated_by = admin.id

    # role=parent: link wards
    if payload.role == Role.PARENT:
        for sid in payload.ward_student_ids:
            student = await db.get(Student, sid)
            if not student or student.school_id != school_id:
                raise HTTPException(status_code=404, detail=f"Student {sid} not found")
            db.add(Guardian(school_id=school_id, parent_user_id=user.id,
                            student_id=sid, created_by=admin.id))

    await record_audit(db, school_id=school_id, user_id=admin.id, action="create",
                       table_name="users", record_id=user.id,
                       changes={"email": {"old": None, "new": payload.email},
                                "role": {"old": None, "new": payload.role}},
                       ip_address=ip)
    await db.commit()
    await db.refresh(user)
    return UserCreatedOut(user=UserAdminOut.model_validate(user),
                          temporary_password=temp_password)


@router.get("", response_model=list[UserAdminOut])
async def list_users(
    db: DbDep, admin: Annotated[User, AdminOnly],
    role: Role | None = Query(None),
):
    school_id = tenant_scope(admin)
    stmt = select(User).where(User.school_id == school_id,
                              User.deleted_at.is_(None))
    if role:
        stmt = stmt.where(User.role == role)
    rows = (await db.execute(stmt.order_by(User.last_name))).scalars().all()
    return list(rows)


class UserEditIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None


@router.patch("/{user_id}")
async def edit_user(
    user_id: str, payload: UserEditIn, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    """Correct a mistake in an account — a misspelt name, a wrong email or phone.

    Deliberately NOT editable here: the role. A "teacher" who should have been
    a "parent" has the wrong relationship to everything (assignments, wards),
    so the honest fix is to deactivate the mistake and create the right
    account — not to mutate one kind of user into another.
    """
    school_id = tenant_scope(admin)
    user = await db.get(User, user_id)
    if not user or user.school_id != school_id:
        raise HTTPException(status_code=404, detail="User not found")

    changes = {}
    if payload.email and payload.email.lower() != user.email:
        new_email = payload.email.strip().lower()
        dup = (await db.execute(select(User).where(
            User.school_id == school_id, User.email == new_email,
            User.id != user.id))).scalars().first()
        if dup:
            raise HTTPException(status_code=409,
                                detail="Another account already uses that email")
        changes["email"] = {"old": user.email, "new": new_email}
        user.email = new_email
        # a changed email is a changed contact — it must be re-verified
        if user.email_verified:
            changes["email_verified"] = {"old": True, "new": False}
            user.email_verified = False

    if payload.phone is not None and payload.phone.strip() != (user.phone or ""):
        new_phone = payload.phone.strip() or None
        changes["phone"] = {"old": user.phone, "new": new_phone}
        user.phone = new_phone
        if user.phone_verified:
            # the tick belongs to the OLD number, not this one
            changes["phone_verified"] = {"old": True, "new": False}
            user.phone_verified = False

    for field in ("first_name", "last_name"):
        value = getattr(payload, field)
        if value and value.strip() and value.strip() != getattr(user, field):
            changes[field] = {"old": getattr(user, field), "new": value.strip()}
            setattr(user, field, value.strip())

    if not changes:
        return {"id": user.id, "updated": False}

    user.updated_by = admin.id
    await record_audit(db, school_id=school_id, user_id=admin.id, action="update",
                       table_name="users", record_id=user.id, changes=changes,
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"id": user.id, "updated": True,
            "changed": sorted(changes.keys())}


@router.delete("/{user_id}")
async def offboard_user(
    user_id: str, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    """Offboard someone who has left the school — staff who resigned, a parent
    whose last ward has gone.

    What happens, deliberately:
    * The account is closed and sign-in stops working immediately.
    * A teacher's subject assignments are ended; the marks they entered remain,
      with their name on the audit trail — history is never rewritten.
    * A parent's ward links are removed; the students themselves are untouched.
    * The email address is released, so a corrected or returning account can be
      created with it later. The original email is preserved in the audit log.
    * An admin cannot offboard themselves, and the LAST active admin cannot be
      offboarded at all — a school must never be able to lock itself out.
    """
    from datetime import datetime, timezone

    school_id = tenant_scope(admin)
    user = await db.get(User, user_id)
    if not user or user.school_id != school_id or user.deleted_at:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400,
                            detail="You cannot offboard your own account")

    if user.role == Role.SCHOOL_ADMIN:
        other_admins = (await db.execute(select(User).where(
            User.school_id == school_id,
            User.role == Role.SCHOOL_ADMIN,
            User.id != user.id,
            User.is_active == True,  # noqa: E712
            User.deleted_at.is_(None)))).scalars().all()
        if not other_admins:
            raise HTTPException(
                status_code=400,
                detail="This is the school's only active admin. Create another "
                       "admin first — a school must never lock itself out.")

    now = datetime.now(timezone.utc)
    detail = {"role": str(getattr(user.role, "value", user.role)),
              "email": {"old": user.email, "new": None}}

    # a teacher's sheets are released for reassignment; their entered marks stay
    if user.role == Role.TEACHER:
        from app.models.student import TeachingAssignment
        assignments = (await db.execute(select(TeachingAssignment).where(
            TeachingAssignment.school_id == school_id,
            TeachingAssignment.teacher_id == user.id,
            TeachingAssignment.deleted_at.is_(None)))).scalars().all()
        for a in assignments:
            a.deleted_at = now
        detail["assignments_closed"] = {"old": len(assignments), "new": 0}

        # their timetable slots stay on the grid — the class still has that
        # lesson to attend — but the teacher becomes vacant for reassignment
        from app.models.timetable import Lesson
        lessons = (await db.execute(select(Lesson).where(
            Lesson.school_id == school_id,
            Lesson.teacher_id == user.id,
            Lesson.deleted_at.is_(None)))).scalars().all()
        for lsn in lessons:
            lsn.teacher_id = None
            lsn.updated_by = admin.id
        detail["timetable_slots_vacated"] = {"old": len(lessons), "new": 0}

    # a parent's view of their wards ends; the students are untouched
    if user.role == Role.PARENT:
        links = (await db.execute(select(Guardian).where(
            Guardian.school_id == school_id,
            Guardian.parent_user_id == user.id))).scalars().all()
        for link in links:
            await db.delete(link)
        detail["ward_links_removed"] = {"old": len(links), "new": 0}

    # close the account and free the email for future reuse; the audit log
    # keeps the original address
    user.is_active = False
    user.deleted_at = now
    user.email = f"offboarded-{now.strftime('%Y%m%d%H%M%S')}-{user.email}"
    user.updated_by = admin.id

    await record_audit(db, school_id=school_id, user_id=admin.id, action="delete",
                       table_name="users", record_id=user.id, changes=detail,
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"offboarded": True,
            "note": "The account is closed. Records they created remain on the "
                    "audit trail under their name."}


@router.patch("/{user_id}/status")
async def set_status(
    user_id: str, payload: UserStatusIn, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    school_id = tenant_scope(admin)
    user = await db.get(User, user_id)
    if not user or user.school_id != school_id:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")
    old = user.is_active
    user.is_active = payload.is_active
    user.updated_by = admin.id
    await record_audit(db, school_id=school_id, user_id=admin.id, action="update",
                       table_name="users", record_id=user.id,
                       changes={"is_active": {"old": old, "new": payload.is_active}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    """Admin issues a fresh temporary password (shown once)."""
    school_id = tenant_scope(admin)
    user = await db.get(User, user_id)
    if not user or user.school_id != school_id:
        raise HTTPException(status_code=404, detail="User not found")
    temp = secrets.token_urlsafe(8)
    user.hashed_password = hash_password(temp)
    user.updated_by = admin.id
    await record_audit(db, school_id=school_id, user_id=admin.id, action="update",
                       table_name="users", record_id=user.id,
                       changes={"password": {"old": "***", "new": "*** (reset)"}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"id": user.id, "temporary_password": temp}


@router.post("/{user_id}/wards", status_code=status.HTTP_201_CREATED)
async def link_ward(
    user_id: str, payload: WardLinkIn, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    school_id = tenant_scope(admin)
    parent = await db.get(User, user_id)
    if not parent or parent.school_id != school_id or parent.role != Role.PARENT:
        raise HTTPException(status_code=404, detail="Parent user not found")
    student = await db.get(Student, payload.student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(status_code=404, detail="Student not found")
    dup = (await db.execute(select(Guardian).where(
        Guardian.parent_user_id == user_id,
        Guardian.student_id == payload.student_id))).scalars().first()
    if dup:
        raise HTTPException(status_code=409, detail="Already linked to this ward")
    db.add(Guardian(school_id=school_id, parent_user_id=user_id,
                    student_id=payload.student_id,
                    relationship=payload.relationship, created_by=admin.id))
    await record_audit(db, school_id=school_id, user_id=admin.id, action="create",
                       table_name="guardians", record_id=None,
                       changes={"parent": {"old": None, "new": user_id},
                                "student": {"old": None, "new": payload.student_id}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"linked": True}


@router.get("/{user_id}/wards")
async def list_wards(
    user_id: str, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    """Which children is this parent linked to?

    This is what makes it possible to reconcile an already-existing parent
    account with a sibling admitted later: the admin opens the parent, sees who
    is currently linked, and adds the new ward — no duplicate account.
    """
    from app.models.academics import ClassArm, SchoolClass

    school_id = tenant_scope(admin)
    parent = await db.get(User, user_id)
    if not parent or parent.school_id != school_id or parent.role != Role.PARENT:
        raise HTTPException(status_code=404, detail="Parent user not found")

    links = (await db.execute(select(Guardian).where(
        Guardian.school_id == school_id,
        Guardian.parent_user_id == user_id))).scalars().all()

    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id))).scalars().all()}

    out = []
    for link in links:
        st = await db.get(Student, link.student_id)
        if not st or st.deleted_at:
            continue
        arm = arms.get(st.current_arm_id) if st.current_arm_id else None
        out.append({
            "student_id": st.id,
            "name": f"{st.first_name} {st.last_name}",
            "admission_number": st.admission_number,
            "class_label": (f"{classes.get(arm.class_id, '')} {arm.name}".strip()
                            if arm else "—"),
            "relationship": link.relationship,
        })
    return sorted(out, key=lambda w: w["admission_number"])


@router.delete("/{user_id}/wards/{student_id}")
async def unlink_ward(
    user_id: str, student_id: str, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    """Remove a ward link — a child was linked to the wrong parent, or has left.

    This detaches the parent's view of that child; it never deletes the student
    or any of their records.
    """
    school_id = tenant_scope(admin)
    link = (await db.execute(select(Guardian).where(
        Guardian.school_id == school_id,
        Guardian.parent_user_id == user_id,
        Guardian.student_id == student_id))).scalars().first()
    if not link:
        raise HTTPException(status_code=404,
                            detail="This ward is not linked to that parent")

    await db.delete(link)
    await record_audit(db, school_id=school_id, user_id=admin.id, action="delete",
                       table_name="guardians", record_id=link.id,
                       changes={"parent": {"old": user_id, "new": None},
                                "student": {"old": student_id, "new": None}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"unlinked": True,
            "note": "This parent can no longer see that child's results, "
                    "fees or timetable."}


# ---------- Teaching assignments: who teaches what, to whom ----------
"""The school admin decides which teacher owns which (subject, arm) score sheet.

This is what stops the Maths teacher from altering the English teacher's marks:
score entry is denied unless the teacher holds the matching assignment.
"""
from datetime import datetime, timezone
from pydantic import BaseModel
from app.models.academics import ClassArm, SchoolClass, Subject
from app.models.student import TeachingAssignment


class AssignmentIn(BaseModel):
    teacher_id: str
    subject_id: str
    arm_id: str
    # A subject in a class normally has exactly one owner — that is what makes
    # "who entered this mark?" answerable. A second assignment is therefore
    # refused (409) unless the admin deliberately says yes, which covers real
    # cases like co-teaching or a stand-in during leave.
    allow_co_teacher: bool = False


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
async def assign_teacher(
    payload: AssignmentIn, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    school_id = tenant_scope(admin)

    teacher = await db.get(User, payload.teacher_id)
    if not teacher or teacher.school_id != school_id or teacher.role != Role.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    subject = await db.get(Subject, payload.subject_id)
    if not subject or subject.school_id != school_id:
        raise HTTPException(status_code=404, detail="Subject not found")
    arm = await db.get(ClassArm, payload.arm_id)
    if not arm or arm.school_id != school_id:
        raise HTTPException(status_code=404, detail="Class not found")

    # everyone who currently owns this (subject, arm) score sheet
    holders = (await db.execute(select(TeachingAssignment).where(
        TeachingAssignment.school_id == school_id,
        TeachingAssignment.subject_id == payload.subject_id,
        TeachingAssignment.arm_id == payload.arm_id,
        TeachingAssignment.deleted_at.is_(None)))).scalars().all()

    if any(h.teacher_id == payload.teacher_id for h in holders):
        raise HTTPException(
            status_code=409,
            detail="This teacher already has that subject in that class")

    if holders and not payload.allow_co_teacher:
        others = []
        for h in holders:
            u = await db.get(User, h.teacher_id)
            if u:
                others.append(f"{u.first_name} {u.last_name}")
        who = " and ".join(others) or "another teacher"
        raise HTTPException(
            status_code=409,
            detail=(f"{subject.name} in this class is already assigned to {who}. "
                    "Remove that assignment first, or confirm to add a co-teacher."))

    ta = TeachingAssignment(school_id=school_id, teacher_id=payload.teacher_id,
                            subject_id=payload.subject_id, arm_id=payload.arm_id,
                            created_by=admin.id)
    db.add(ta)
    await db.flush()
    await record_audit(db, school_id=school_id, user_id=admin.id, action="create",
                       table_name="teaching_assignments", record_id=ta.id,
                       changes={"teacher": {"old": None, "new": teacher.email},
                                "subject": {"old": None, "new": subject.name},
                                "arm": {"old": None, "new": arm.id}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"id": ta.id, "teacher_id": ta.teacher_id,
            "subject_id": ta.subject_id, "arm_id": ta.arm_id,
            "co_teachers": len(holders)}


@router.get("/assignments")
async def list_assignments(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER))],
    teacher_id: str | None = Query(None),
):
    """Admins see everything; a teacher sees only their own assignments."""
    school_id = tenant_scope(user)
    stmt = select(TeachingAssignment).where(
        TeachingAssignment.school_id == school_id,
        TeachingAssignment.deleted_at.is_(None))
    if user.role == Role.TEACHER:
        stmt = stmt.where(TeachingAssignment.teacher_id == user.id)
    elif teacher_id:
        stmt = stmt.where(TeachingAssignment.teacher_id == teacher_id)

    rows = (await db.execute(stmt)).scalars().all()

    subjects = {s.id: s.name for s in (await db.execute(select(Subject).where(
        Subject.school_id == school_id))).scalars().all()}
    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id))).scalars().all()}
    teachers = {u.id: f"{u.first_name} {u.last_name}"
                for u in (await db.execute(select(User).where(
                    User.school_id == school_id))).scalars().all()}

    out = []
    for ta in rows:
        arm = arms.get(ta.arm_id)
        out.append({
            "id": ta.id,
            "teacher_id": ta.teacher_id,
            "teacher_name": teachers.get(ta.teacher_id, "?"),
            "subject_id": ta.subject_id,
            "subject_name": subjects.get(ta.subject_id, "?"),
            "arm_id": ta.arm_id,
            "class_label": (f"{classes.get(arm.class_id, '')} {arm.name}".strip()
                            if arm else "?"),
        })
    return sorted(out, key=lambda x: (x["teacher_name"], x["class_label"]))


@router.delete("/assignments/{assignment_id}")
async def unassign_teacher(
    assignment_id: str, request: Request, db: DbDep,
    admin: Annotated[User, AdminOnly],
):
    school_id = tenant_scope(admin)
    ta = await db.get(TeachingAssignment, assignment_id)
    if not ta or ta.school_id != school_id or ta.deleted_at:
        raise HTTPException(status_code=404, detail="Assignment not found")
    ta.deleted_at = datetime.now(timezone.utc)
    ta.updated_by = admin.id
    await record_audit(db, school_id=school_id, user_id=admin.id, action="delete",
                       table_name="teaching_assignments", record_id=ta.id,
                       changes={"teacher_id": {"old": ta.teacher_id, "new": None}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"removed": True,
            "note": "This teacher can no longer enter scores for that subject and class."}
