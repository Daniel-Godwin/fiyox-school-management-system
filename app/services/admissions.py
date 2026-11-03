"""Admissions helpers — application numbers, access codes, and the one action
that turns an accepted applicant into a full student."""
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admissions import Applicant, ADMITTED
from app.models.student import Student
from app.models.school import School

_CODE_ALPHABET = string.ascii_uppercase + string.digits  # no lowercase: easy to read/type


def _initials(name: str) -> str:
    """A fallback prefix from a school's name, e.g. 'Fiyox Academy Demo' -> 'FAD'."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in name).split() if w]
    letters = "".join(w[0] for w in words if w[0].isalpha())[:4].upper()
    return letters or "ADM"


def admission_prefix(school: School) -> str:
    return (school.admission_prefix or "").strip().upper() or _initials(school.name)


def admission_preview(school: School) -> str:
    """What the next admission number would look like (serial shown as 1)."""
    yy = datetime.now(timezone.utc).strftime("%y")
    pad = school.admission_pad or 3
    return f"{admission_prefix(school)}/{yy}/{1:0{pad}d}"


async def next_admission_number(db: AsyncSession, school: School) -> str:
    """<prefix>/<2-digit year>/<serial>, serial continuing from the highest used
    for this school and year so it never collides with an existing number."""
    yy = datetime.now(timezone.utc).strftime("%y")
    pad = school.admission_pad or 3
    prefix = f"{admission_prefix(school)}/{yy}/"
    rows = (await db.execute(select(Student.admission_number).where(
        Student.school_id == school.id,
        Student.admission_number.like(f"{prefix}%")))).scalars().all()
    highest = 0
    for num in rows:
        tail = num.rsplit("/", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:0{pad}d}"


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
