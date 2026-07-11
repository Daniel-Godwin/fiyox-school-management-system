"""Student endpoints (tenant-scoped, audited, soft-delete aware)."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.student import Student
from app.services.audit import record_audit
from app.schemas import StudentCreate, StudentOut

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
