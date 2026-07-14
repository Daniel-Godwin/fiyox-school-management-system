"""End-of-session promotion — moving a class up.

What a Nigerian school actually does at the end of the session:
  - most students are **promoted** to the next class;
  - a few **repeat**;
  - the final year **graduates** (leaves the school).

Design decisions worth stating:

* Promotion is driven by `level_order` on SchoolClass (JSS1=1, JSS2=2 …), so the
  "next class" is unambiguous. A class with no successor is a graduating class.
* It is a **preview-then-commit** operation. The admin sees exactly who will be
  promoted, who repeats and who graduates *before* anything moves — a bulk move
  of every child in the school is not something to fire blindly.
* History is preserved: results, invoices and attendance all belong to the term
  they were recorded in, so a promoted student's past reports remain intact.
* Graduating students are deactivated, not deleted — their records stay
  auditable, which matters for transcripts years later.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.academics import ClassArm, SchoolClass
from app.models.school import Role, User
from app.models.student import Student
from app.services.audit import record_audit

router = APIRouter(prefix="/api/promotion", tags=["promotion"])

AdminOnly = Depends(require_roles(Role.SCHOOL_ADMIN))


class PromotionIn(BaseModel):
    from_arm_id: str
    # students who should NOT go up (they repeat the class)
    repeat_student_ids: list[str] = []
    # where the promoted students land; if omitted, an arm of the same name in
    # the next class is used (JSS1 A -> JSS2 A)
    to_arm_id: str | None = None
    commit: bool = False       # False = preview only


async def _next_class(db, school_id: str, klass: SchoolClass) -> SchoolClass | None:
    candidates = (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id,
        SchoolClass.level_order > klass.level_order,
        SchoolClass.deleted_at.is_(None)).order_by(
            SchoolClass.level_order))).scalars().all()
    return candidates[0] if candidates else None


@router.post("/preview")
@router.post("/run")
async def promote(payload: PromotionIn, request: Request, db: DbDep,
                  admin: Annotated[User, AdminOnly]):
    """Preview (commit=false) or perform (commit=true) an end-of-session promotion."""
    school_id = tenant_scope(admin)

    arm = await db.get(ClassArm, payload.from_arm_id)
    if not arm or arm.school_id != school_id or arm.deleted_at:
        raise HTTPException(status_code=404, detail="Class not found")
    klass = await db.get(SchoolClass, arm.class_id)
    if not klass:
        raise HTTPException(status_code=404, detail="Class not found")

    students = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id == payload.from_arm_id,
        Student.deleted_at.is_(None),
        Student.is_active == True))).scalars().all()  # noqa: E712

    next_class = await _next_class(db, school_id, klass)
    graduating = next_class is None

    target_arm = None
    if not graduating:
        if payload.to_arm_id:
            target_arm = await db.get(ClassArm, payload.to_arm_id)
            if (not target_arm or target_arm.school_id != school_id
                    or target_arm.class_id != next_class.id):
                raise HTTPException(
                    status_code=400,
                    detail=f"The destination must be an arm of {next_class.name}")
        else:
            # same arm name in the next class (JSS1 A -> JSS2 A), else its first arm
            arms_next = (await db.execute(select(ClassArm).where(
                ClassArm.school_id == school_id,
                ClassArm.class_id == next_class.id,
                ClassArm.deleted_at.is_(None)))).scalars().all()
            target_arm = next((a for a in arms_next if a.name == arm.name), None) \
                or (arms_next[0] if arms_next else None)
            if not target_arm:
                raise HTTPException(
                    status_code=400,
                    detail=(f"{next_class.name} has no arms yet. "
                            "Create one before promoting into it."))

    repeats = set(payload.repeat_student_ids)
    promoted, repeated, graduated = [], [], []
    for s in students:
        entry = {"student_id": s.id, "admission_number": s.admission_number,
                 "name": f"{s.first_name} {s.last_name}"}
        if s.id in repeats:
            repeated.append(entry)
        elif graduating:
            graduated.append(entry)
        else:
            promoted.append(entry)

    target_label = None
    if target_arm:
        target_label = f"{next_class.name} {target_arm.name}"

    result = {
        "from": f"{klass.name} {arm.name}",
        "to": target_label,
        "graduating_class": graduating,
        "promoted": promoted,
        "repeated": repeated,
        "graduated": graduated,
        "committed": False,
    }

    if not payload.commit:
        return result   # preview: nothing has moved

    ip = request.client.host if request.client else None
    for s in students:
        if s.id in repeats:
            continue      # stays exactly where they are
        if graduating:
            s.is_active = False        # left the school; record kept for transcripts
            s.updated_by = admin.id
            await record_audit(db, school_id=school_id, user_id=admin.id,
                               action="update", table_name="students",
                               record_id=s.id,
                               changes={"is_active": {"old": True, "new": False},
                                        "reason": {"old": None, "new": "graduated"}},
                               ip_address=ip)
        else:
            old = s.current_arm_id
            s.current_arm_id = target_arm.id
            s.updated_by = admin.id
            await record_audit(db, school_id=school_id, user_id=admin.id,
                               action="update", table_name="students",
                               record_id=s.id,
                               changes={"current_arm_id": {"old": old,
                                                           "new": target_arm.id},
                                        "reason": {"old": None, "new": "promoted"}},
                               ip_address=ip)

    await db.commit()
    result["committed"] = True
    return result
