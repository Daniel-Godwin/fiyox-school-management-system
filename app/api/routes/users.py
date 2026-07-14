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
    stmt = select(User).where(User.school_id == school_id)
    if role:
        stmt = stmt.where(User.role == role)
    rows = (await db.execute(stmt.order_by(User.last_name))).scalars().all()
    return list(rows)


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

    dup = (await db.execute(select(TeachingAssignment).where(
        TeachingAssignment.school_id == school_id,
        TeachingAssignment.teacher_id == payload.teacher_id,
        TeachingAssignment.subject_id == payload.subject_id,
        TeachingAssignment.arm_id == payload.arm_id,
        TeachingAssignment.deleted_at.is_(None)))).scalars().first()
    if dup:
        raise HTTPException(status_code=409,
                            detail="This teacher already has that subject in that class")

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
            "subject_id": ta.subject_id, "arm_id": ta.arm_id}


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
