"""Student endpoints (tenant-scoped, audited, soft-delete aware)."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser, require_roles, tenant_scope
from app.models.school import User, Role, School
from app.models.student import Student
from app.services.audit import record_audit
from app.services.admissions import admission_prefix
from app.schemas import StudentCreate, StudentOut, RenumberIn

router = APIRouter(prefix="/api/students", tags=["students"])


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
async def create_student(
    payload: StudentCreate,
    request: Request,
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER))],
):
    school_id = tenant_scope(user)
    student = Student(school_id=school_id, created_by=user.id, **payload.model_dump())
    db.add(student)
    await db.flush()
    await record_audit(db, school_id=school_id, user_id=user.id, action="create",
                       table_name="students", record_id=student.id,
                       changes={"admission_number": {"old": None, "new": student.admission_number}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(student)
    return student


@router.get("", response_model=list[StudentOut])
async def list_students(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    # tenant isolation + soft-delete: only this school's non-deleted students
    result = await db.execute(select(Student).where(
        Student.school_id == school_id, Student.deleted_at.is_(None)))
    return list(result.scalars().all())


@router.post("/renumber")
async def renumber_class(
    payload: RenumberIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN, Role.SUPER_ADMIN))],
):
    """Re-sequence a class's admission numbers into the school's format.

    Preview first (apply=false): returns each student's old -> new number and
    flags any new number that would clash with a student outside this class.
    Nothing changes until apply=true, and then only if there are no clashes.
    """
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)

    # the class roster, in a stable order (surname, then first name)
    students = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id == payload.arm_id,
        Student.deleted_at.is_(None)))).scalars().all()
    students = sorted(students, key=lambda s: (s.last_name.lower(), s.first_name.lower()))
    if not students:
        raise HTTPException(404, "No students in that class")

    prefix = payload.prefix or admission_prefix(school)
    pad = payload.pad or school.admission_pad or 3
    batch_ids = {s.id for s in students}

    # every admission number already used by a student NOT in this batch
    others = (await db.execute(select(Student.admission_number).where(
        Student.school_id == school_id,
        Student.deleted_at.is_(None),
        Student.id.notin_(batch_ids)))).scalars().all()
    taken = set(others)

    rows, conflicts = [], 0
    for i, s in enumerate(students):
        new_no = f"{prefix}/{payload.year}/{payload.start + i:0{pad}d}"
        clash = new_no in taken
        if clash:
            conflicts += 1
        rows.append({
            "student_id": s.id, "name": f"{s.first_name} {s.last_name}",
            "old": s.admission_number, "new": new_no, "conflict": clash,
        })

    if not payload.apply:
        return {"preview": rows, "count": len(rows), "conflicts": conflicts, "applied": False}

    if conflicts:
        raise HTTPException(409, "Some new numbers clash with students in other classes — resolve them first")

    by_id = {s.id: s for s in students}
    for r in rows:
        by_id[r["student_id"]].admission_number = r["new"]
        by_id[r["student_id"]].updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="students", record_id="renumber",
                       changes={"arm_id": {"new": payload.arm_id},
                                "count": {"new": len(rows)}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"preview": rows, "count": len(rows), "conflicts": 0, "applied": True}
