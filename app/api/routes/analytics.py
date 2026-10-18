"""Analytics overview — one aggregated read for the dashboard.

Admin and principal see their own school; the platform owner (super admin) sees
every school rolled up together. Read-only; it never changes data.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import User, Role, School
from app.models.academics import Term
from app.services.analytics import build_overview

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

AnalyticsRoles = Depends(require_roles(Role.SCHOOL_ADMIN, Role.PRINCIPAL))


@router.get("/overview")
async def overview(db: DbDep, user: Annotated[User, AnalyticsRoles],
                   term_id: str | None = Query(None)):
    """Enrolment, academics, finance and CBT figures for a term.

    `term_id` optional: enrolment and CBT totals still return without it, while
    the term-bound sections (results, fees) stay empty until a term is chosen.
    """
    if user.role == Role.SUPER_ADMIN:
        school_ids = [s.id for s in (await db.execute(select(School).where(
            School.is_active == True))).scalars().all()]  # noqa: E712
        scope = "platform"
        schools_count = len(school_ids)
    else:
        school_ids = [tenant_scope(user)]
        scope = "school"
        schools_count = 1

    data = await build_overview(db, school_ids, term_id)

    term = await db.get(Term, term_id) if term_id else None
    data["scope"] = scope
    data["schools"] = schools_count
    data["term"] = ({"id": term.id, "name": str(term.name).split(".")[-1]}
                    if term else None)
    return data
