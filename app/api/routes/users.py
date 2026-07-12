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
