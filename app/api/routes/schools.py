"""School onboarding endpoints (platform super admin)."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from app.core.deps import DbDep, require_roles
from app.core.security import hash_password
from app.models.school import School, User, Role, DEFAULT_GRADING
from app.schemas import SchoolCreate, SchoolOut
import secrets as _secrets
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/schools", tags=["schools"])


class SchoolAccountIn(BaseModel):
    role: Role
    email: EmailStr
    first_name: str
    last_name: str
    password: str | None = None


@router.post("", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
async def create_school(
    payload: SchoolCreate,
    db: DbDep,
    _: Annotated[User, Depends(require_roles(Role.SUPER_ADMIN))],
):
    exists = await db.execute(select(School).where(School.slug == payload.slug))
    if exists.scalars().first():
        raise HTTPException(status_code=409, detail="School slug already taken")

    # emails are globally unique (one email = one account); normalise and check
    # across every school before standing up the new admin
    admin_email = str(payload.admin_email).strip().lower()
    dup = (await db.execute(select(User).where(
        func.lower(User.email) == admin_email, User.deleted_at.is_(None)))).scalars().first()
    if dup:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    school = School(name=payload.name, slug=payload.slug, state=payload.state,
                    phone=payload.phone)
    db.add(school)
    await db.flush()  # get school.id

    admin = User(
        school_id=school.id,
        email=admin_email,
        hashed_password=hash_password(payload.admin_password),
        role=Role.SCHOOL_ADMIN,
        first_name=payload.admin_first_name,
        last_name=payload.admin_last_name,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(school)
    return school


@router.post("/{school_id}/accounts", tags=["schools"], status_code=status.HTTP_201_CREATED)
async def create_school_account(
    school_id: str, payload: SchoolAccountIn, db: DbDep,
    owner: Annotated[User, Depends(require_roles(Role.SUPER_ADMIN))],
):
    """Platform owner creates a Principal / Admin / Bursar for a school, and
    receives one-time sign-in credentials to hand over."""
    if payload.role not in (Role.PRINCIPAL, Role.SCHOOL_ADMIN, Role.BURSAR):
        raise HTTPException(status_code=400,
                            detail="Role must be principal, school_admin or bursar")
    school = await db.get(School, school_id)
    if not school or school.deleted_at:
        raise HTTPException(status_code=404, detail="School not found")

    # emails are globally unique (one email = one account), so the duplicate
    # check spans every school; a soft-deleted account frees its email for reuse
    email = str(payload.email).strip().lower()
    dup = (await db.execute(select(User).where(
        func.lower(User.email) == email, User.deleted_at.is_(None)))).scalars().first()
    if dup:
        raise HTTPException(status_code=409,
                            detail="A user with this email already exists")

    pwd = payload.password or _secrets.token_urlsafe(8)
    user = User(school_id=school_id, email=email,
                hashed_password=hash_password(pwd), role=payload.role,
                first_name=payload.first_name.strip(),
                last_name=payload.last_name.strip())
    db.add(user)
    await db.commit()
    return {"id": user.id, "email": email,
            "role": getattr(payload.role, "value", payload.role), "password": pwd}


# ---------- School settings (school admin manages their own school) ----------
from fastapi import Request
from pydantic import BaseModel, Field, field_validator
from app.core.deps import tenant_scope
from app.services.audit import record_audit
from app.services.admissions import admission_preview


class SchoolSettingsIn(BaseModel):
    name: str | None = None
    principal_name: str | None = None
    address: str | None = None
    state: str | None = None
    phone: str | None = None
    primary_color: str | None = None      # hex, brands the report card & receipt
    withhold_results_on_debt: bool | None = None
    result_approval_required: bool | None = None
    affective_traits: list[str] | None = None
    psychomotor_traits: list[str] | None = None
    online_payments_enabled: bool | None = None
    admission_prefix: str | None = Field(None, max_length=12)
    admission_pad: int | None = Field(None, ge=2, le=6)

    @field_validator("admission_prefix")
    @classmethod
    def _clean_prefix(cls, v: str | None) -> str | None:
        if v is None:
            return None
        # letters/digits only, upper-cased; blank clears it (falls back to initials)
        v = "".join(c for c in v if c.isalnum()).upper()
        return v or None


@router.get("/me", tags=["schools"])
async def my_school(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(
        Role.SCHOOL_ADMIN, Role.BURSAR, Role.TEACHER, Role.PRINCIPAL))],
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
        "result_approval_required": school.result_approval_required,
        "affective_traits": school.affective_traits or [],
        "psychomotor_traits": school.psychomotor_traits or [],
        "online_payments_enabled": school.online_payments_enabled,
        "admission_prefix": school.admission_prefix,
        "admission_pad": school.admission_pad,
        "admission_number_preview": admission_preview(school),
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
        "result_approval_required": school.result_approval_required,
        "affective_traits": school.affective_traits or [],
        "psychomotor_traits": school.psychomotor_traits or [],
        "online_payments_enabled": school.online_payments_enabled,
        "updated": list(changes.keys()),
    }


# ==================================================================
# Grading system — a school keeps the WAEC bands or defines its own
# ==================================================================
import copy as _copy


class GradingBand(BaseModel):
    grade: str = Field(..., min_length=1, max_length=6)
    min: int = Field(..., ge=0, le=100)
    remark: str = Field("", max_length=40)


class GradingBandsIn(BaseModel):
    bands: list[GradingBand] = Field(..., min_length=1, max_length=20)


def _bands_with_ranges(bands: list[dict]) -> list[dict]:
    """Attach each band's upper bound, highest first (A1 75-100, ...)."""
    hi_low = sorted(bands, key=lambda b: b["min"], reverse=True)
    out = []
    for i, b in enumerate(hi_low):
        upper = 100 if i == 0 else hi_low[i - 1]["min"] - 1
        out.append({"grade": b["grade"], "min": b["min"], "max": upper,
                    "remark": b.get("remark", "")})
    return out


def _is_waec(bands: list[dict]) -> bool:
    waec = {(b["grade"], b["min"]) for b in DEFAULT_GRADING["bands"]}
    return {(b["grade"], b["min"]) for b in bands} == waec


@router.get("/me/grading", tags=["schools"])
async def get_grading(db: DbDep, user: Annotated[User, Depends(require_roles(
        Role.SCHOOL_ADMIN, Role.PRINCIPAL, Role.TEACHER))]):
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")
    bands = (school.grading_config or {}).get("bands", []) or DEFAULT_GRADING["bands"]
    return {"bands": _bands_with_ranges(bands), "is_waec": _is_waec(bands),
            "waec": _bands_with_ranges(DEFAULT_GRADING["bands"])}


@router.put("/me/grading", tags=["schools"])
async def set_grading(payload: GradingBandsIn, request: Request, db: DbDep,
                      user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))]):
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")

    bands = [{"grade": b.grade.strip(), "min": b.min, "remark": b.remark.strip()}
             for b in payload.bands]
    mins = [b["min"] for b in bands]
    if len(set(mins)) != len(mins):
        raise HTTPException(422, "Two bands cannot start at the same score")
    if min(mins) != 0:
        raise HTTPException(422, "The lowest band must start at 0 so every score has a grade")
    if any(not b["grade"] for b in bands):
        raise HTTPException(422, "Every band needs a grade label")

    cfg = _copy.deepcopy(school.grading_config or DEFAULT_GRADING)
    cfg["bands"] = sorted(bands, key=lambda b: b["min"], reverse=True)
    school.grading_config = cfg
    school.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="schools", record_id=school.id,
                       changes={"grading_bands": {"new": len(bands)}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"bands": _bands_with_ranges(cfg["bands"]), "is_waec": _is_waec(cfg["bands"])}


@router.post("/me/grading/reset", tags=["schools"])
async def reset_grading(request: Request, db: DbDep,
                        user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))]):
    """Restore the WAEC standard bands."""
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")
    cfg = _copy.deepcopy(school.grading_config or DEFAULT_GRADING)
    cfg["bands"] = _copy.deepcopy(DEFAULT_GRADING["bands"])
    school.grading_config = cfg
    school.updated_by = user.id
    await db.commit()
    return {"bands": _bands_with_ranges(cfg["bands"]), "is_waec": True}


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
        users = (await db.execute(select(User).where(
            User.school_id == s.id,
            User.deleted_at.is_(None)))).scalars().all()
        roles = {"school_admin": 0, "principal": 0, "bursar": 0, "teacher": 0,
                 "parent": 0, "student": 0}
        active = 0
        for u in users:
            r = str(getattr(u.role, "value", u.role))
            if r in roles:
                roles[r] += 1
            if u.is_active:
                active += 1
        out.append({
            "id": s.id, "name": s.name, "slug": s.slug,
            "state": s.state, "phone": s.phone,
            "students": len(students),
            "admins": roles["school_admin"], "principals": roles["principal"],
            "bursars": roles["bursar"],
            "teachers": roles["teacher"], "parents": roles["parent"],
            "active_accounts": active,
            "created_at": str(s.created_at)[:10] if s.created_at else None,
        })
    return out


@router.delete("/{school_id}", tags=["schools"])
async def offboard_school(
    school_id: str, db: DbDep,
    owner: Annotated[User, Depends(require_roles(Role.SUPER_ADMIN))],
):
    """A school leaves the platform — after a pilot, or by choice.

    The school is closed and every one of its accounts stops signing in,
    immediately. Nothing is destroyed: the tenant's records stay in the
    database (results, payments, audit trail), so a returning school can be
    reactivated by support, and disputes years later can still be answered.
    The school should download its full export BEFORE this is done.
    """
    from datetime import datetime, timezone
    from app.services.audit import record_audit

    school = await db.get(School, school_id)
    if not school or school.deleted_at:
        raise HTTPException(status_code=404, detail="School not found")

    users = (await db.execute(select(User).where(
        User.school_id == school_id,
        User.deleted_at.is_(None)))).scalars().all()

    now = datetime.now(timezone.utc)
    blocked = 0
    for u in users:
        # fully retire the account: deactivate AND soft-delete, so its email
        # stops shadowing live accounts at login and is freed for reuse. The row
        # itself is kept (soft delete) for audit and possible reactivation.
        u.is_active = False
        u.deleted_at = now
        blocked += 1
    school.deleted_at = now

    await record_audit(db, school_id=school_id, user_id=owner.id,
                       action="offboard", table_name="schools",
                       record_id=school_id,
                       changes={"school": {"old": school.name, "new": None},
                                "accounts_blocked": {"old": blocked, "new": 0}})
    await db.commit()
    return {"offboarded": True, "school": school.name,
            "accounts_blocked": blocked,
            "note": ("All sign-ins for this school are now blocked. Records are "
                     "retained, not destroyed — the school can be restored by "
                     "support if it returns.")}

