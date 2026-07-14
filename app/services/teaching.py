"""Teaching assignments — who may touch whose scores.

The rule Fiyox enforces:

    A **teacher** may read and write scores only for the (subject, arm) pairs
    they are actually assigned to teach. The Maths teacher of JSS1 A cannot
    open — let alone alter — the English marks of JSS1 A, or the Maths marks
    of JSS2 B.

    A **school admin** is not restricted: they must be able to correct any
    sheet, cover for an absent teacher, and audit the whole school. Their
    edits are audited like everyone else's, so the trail still names them.

This is deliberately *deny by default*: a teacher with no assignments can do
nothing until the admin assigns them, rather than quietly having access to
everything (which was the old behaviour).
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.school import Role, User
from app.models.student import TeachingAssignment


async def teaches(db: AsyncSession, school_id: str, teacher_id: str,
                  subject_id: str, arm_id: str) -> bool:
    row = (await db.execute(select(TeachingAssignment).where(
        TeachingAssignment.school_id == school_id,
        TeachingAssignment.teacher_id == teacher_id,
        TeachingAssignment.subject_id == subject_id,
        TeachingAssignment.arm_id == arm_id,
        TeachingAssignment.deleted_at.is_(None)))).scalars().first()
    return row is not None


async def assert_may_touch_scores(db: AsyncSession, user: User, school_id: str,
                                  subject_id: str, arm_id: str) -> None:
    """Raise 403 unless this user may enter/see scores for this subject+arm.

    Admins pass through; teachers must hold the assignment.
    """
    if user.role in (Role.SCHOOL_ADMIN, Role.SUPER_ADMIN):
        return

    if user.role != Role.TEACHER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not allowed to enter scores")

    if not await teaches(db, school_id, user.id, subject_id, arm_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("You are not assigned to teach this subject in this class. "
                    "Ask the school admin if this is a mistake."))


async def assignments_for(db: AsyncSession, school_id: str,
                          teacher_id: str) -> list[TeachingAssignment]:
    return list((await db.execute(select(TeachingAssignment).where(
        TeachingAssignment.school_id == school_id,
        TeachingAssignment.teacher_id == teacher_id,
        TeachingAssignment.deleted_at.is_(None)))).scalars().all())
