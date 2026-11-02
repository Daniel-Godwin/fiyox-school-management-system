"""Admissions helpers — application numbers, access codes, and the one action
that turns an accepted applicant into a full student."""
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admissions import Applicant, ADMITTED
from app.models.student import Student

_CODE_ALPHABET = string.ascii_uppercase + string.digits  # no lowercase: easy to read/type


def new_access_code(n: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


async def next_application_number(db: AsyncSession, school_id: str) -> str:
    """APP/<2-digit year>/<4-digit serial>, serial unique within the school+year."""
    yy = datetime.now(timezone.utc).strftime("%y")
    prefix = f"APP/{yy}/"
    count = (await db.execute(select(func.count()).select_from(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.application_number.like(f"{prefix}%")))).scalar() or 0
    return f"{prefix}{count + 1:04d}"


async def admit_applicant(db: AsyncSession, applicant: Applicant, *,
                          admission_number: str, arm_id: str | None,
                          actor_id: str) -> Student:
    """Create a Student from an accepted applicant and mark it admitted.

    Idempotent-ish: if the applicant already points at a student, that student
    is returned rather than a duplicate being created.
    """
    if applicant.admitted_student_id:
        existing = await db.get(Student, applicant.admitted_student_id)
        if existing is not None:
            return existing

    student = Student(
        school_id=applicant.school_id,
        admission_number=admission_number,
        first_name=applicant.first_name,
        last_name=applicant.last_name,
        other_names=applicant.other_names,
        gender=applicant.gender,
        date_of_birth=applicant.date_of_birth,
        current_arm_id=arm_id,
        is_active=True,
        created_by=actor_id,
    )
    db.add(student)
    await db.flush()

    applicant.status = ADMITTED
    applicant.admitted_student_id = student.id
    applicant.updated_by = actor_id
    return student
