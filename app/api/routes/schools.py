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


# ---------- School settings (school admin manages their own school) ----------
from fastapi import Request
from pydantic import BaseModel
from app.core.deps import tenant_scope
from app.services.audit import record_audit


class SchoolSettingsIn(BaseModel):
    name: str | None = None
    principal_name: str | None = None
    address: str | None = None
    state: str | None = None
    phone: str | None = None
    primary_color: str | None = None      # hex, brands the report card & receipt
    withhold_results_on_debt: bool | None = None


@router.get("/me", tags=["schools"])
async def my_school(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(
        Role.SCHOOL_ADMIN, Role.BURSAR, Role.TEACHER))],
):
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return {
        "id": school.id, "name": school.name, "slug": school.slug,
        "address": school.address, "state": school.state, "phone": school.phone,
        "primary_color": school.primary_color,
        "principal_name": school.principal_name,
        "withhold_results_on_debt": school.withhold_results_on_debt,
        "has_logo": bool(school.logo_url),
        "has_signature": bool(school.signature_url),
        "has_stamp": bool(school.stamp_url),
        "logo_url": school.logo_url,
    }


@router.patch("/me", tags=["schools"])
async def update_my_school(
    payload: SchoolSettingsIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    changes = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        old = getattr(school, field)
        if value is not None and value != old:
            changes[field] = {"old": old, "new": value}
            setattr(school, field, value)

    if changes:
        await record_audit(db, school_id=school_id, user_id=user.id,
                           action="update", table_name="schools",
                           record_id=school.id, changes=changes,
                           ip_address=request.client.host if request.client else None)
        await db.commit()
        await db.refresh(school)

    return {
        "id": school.id, "name": school.name, "address": school.address,
        "state": school.state, "phone": school.phone,
        "primary_color": school.primary_color,
        "principal_name": school.principal_name,
        "withhold_results_on_debt": school.withhold_results_on_debt,
        "updated": list(changes.keys()),
    }


# ---------- Branding assets (logo, signature, stamp) ----------
from fastapi import File, UploadFile
from app.services.branding import to_data_uri

_ASSET_FIELDS = {"logo": "logo_url", "signature": "signature_url",
                 "stamp": "stamp_url"}


@router.post("/me/branding/{asset}", tags=["schools"])
async def upload_branding(
    asset: str, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
    file: UploadFile = File(...),
):
    """Upload the school logo, the principal's signature, or the school stamp.
    PNG/JPEG, under 300 KB. These appear on every report card."""
    field = _ASSET_FIELDS.get(asset)
    if not field:
        raise HTTPException(status_code=404,
                            detail="Unknown asset — use logo, signature or stamp")
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    uri = await to_data_uri(file)
    setattr(school, field, uri)
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="schools", record_id=school.id,
                       changes={field: {"old": "***", "new": f"{asset} uploaded"}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"asset": asset, "saved": True}


@router.delete("/me/branding/{asset}", tags=["schools"])
async def delete_branding(
    asset: str, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    field = _ASSET_FIELDS.get(asset)
    if not field:
        raise HTTPException(status_code=404, detail="Unknown asset")
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    setattr(school, field, None)
    await db.commit()
    return {"asset": asset, "removed": True}


@router.get("", tags=["schools"])
async def list_schools(
    db: DbDep,
    _: Annotated[User, Depends(require_roles(Role.SUPER_ADMIN))],
):
    """The platform owner's view: every school, with enough numbers to see at a
    glance which pilots are alive and which never started."""
    from app.models.student import Student

    schools = (await db.execute(select(School).where(
        School.deleted_at.is_(None)).order_by(School.created_at))).scalars().all()

    out = []
    for s in schools:
        students = (await db.execute(select(Student.id).where(
            Student.school_id == s.id,
            Student.deleted_at.is_(None)))).scalars().all()
        users = (await db.execute(select(User.id).where(
            User.school_id == s.id,
            User.deleted_at.is_(None)))).scalars().all()
        out.append({
            "id": s.id, "name": s.name, "slug": s.slug,
            "state": s.state, "phone": s.phone,
            "students": len(students), "users": len(users),
            "created_at": str(s.created_at)[:10] if s.created_at else None,
        })
    return out
