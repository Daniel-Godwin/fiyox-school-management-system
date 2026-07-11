"""Family portal reads — what a parent (or student) may see about their own wards.

These endpoints are scoped by the Guardian link (or the student's own account),
never by free-form student ids, so a parent can only ever read their own family.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.student import Student, Guardian
from app.models.academics import ClassArm, SchoolClass
from app.models.fees import Invoice
from app.services.fees import invoice_view

router = APIRouter(prefix="/api/my", tags=["portal"])

PortalRoles = Depends(require_roles(Role.PARENT, Role.STUDENT))


async def _my_students(db, user: User, school_id: str) -> list[Student]:
    if user.role == Role.STUDENT:
        rows = (await db.execute(select(Student).where(
            Student.school_id == school_id, Student.user_id == user.id,
            Student.deleted_at.is_(None)))).scalars().all()
        return list(rows)
    links = (await db.execute(select(Guardian).where(
        Guardian.school_id == school_id,
        Guardian.parent_user_id == user.id))).scalars().all()
    students = []
    for link in links:
        st = await db.get(Student, link.student_id)
        if st and st.deleted_at is None:
            students.append(st)
    return students


@router.get("/wards")
async def my_wards(db: DbDep, user: Annotated[User, PortalRoles]):
    school_id = tenant_scope(user)
    students = await _my_students(db, user, school_id)

    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id))).scalars().all()}

    out = []
    for st in students:
        arm = arms.get(st.current_arm_id) if st.current_arm_id else None
        label = f"{classes.get(arm.class_id, '')} {arm.name}".strip() if arm else ""
        out.append({
            "student_id": st.id,
            "name": f"{st.first_name} {st.last_name}",
            "admission_number": st.admission_number,
            "class_label": label,
        })
    return out


@router.get("/fees")
async def my_fees(db: DbDep, user: Annotated[User, PortalRoles],
                  term_id: str = Query(...)):
    """Read-only invoice position for each of the caller's wards this term."""
    school_id = tenant_scope(user)
    students = await _my_students(db, user, school_id)
    out = []
    for st in students:
        inv = (await db.execute(select(Invoice).where(
            Invoice.school_id == school_id,
            Invoice.student_id == st.id,
            Invoice.term_id == term_id,
            Invoice.deleted_at.is_(None)))).scalars().first()
        if inv:
            view = await invoice_view(db, inv)
            view["student_id"] = st.id
            out.append(view)
    return out
