"""School onboarding endpoints (platform super admin)."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from app.core.deps import DbDep, require_roles
from app.core.security import hash_password
from app.models.school import School, User, Role
from app.schemas import SchoolCreate, SchoolOut

router = APIRouter(prefix="/api/schools", tags=["schools"])


@router.post("", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
async def create_school(
    payload: SchoolCreate,
    db: DbDep,
    _: Annotated[User, Depends(require_roles(Role.SUPER_ADMIN))],
):
    exists = await db.execute(select(School).where(School.slug == payload.slug))
    if exists.scalars().first():
        raise HTTPException(status_code=409, detail="School slug already taken")

    school = School(name=payload.name, slug=payload.slug, state=payload.state,
                    phone=payload.phone)
    db.add(school)
    await db.flush()  # get school.id

    admin = User(
        school_id=school.id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        role=Role.SCHOOL_ADMIN,
        first_name=payload.admin_first_name,
        last_name=payload.admin_last_name,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(school)
    return school
