"""School data export endpoint.

Admin-only, tenant-scoped, audited. The download is generated fresh on each
request, so it is always current — there is no stale snapshot to manage.
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import Role, User
from app.services.audit import record_audit
from app.services.export import build_school_export

router = APIRouter(prefix="/api/export", tags=["export"])

AdminOnly = Depends(require_roles(Role.SCHOOL_ADMIN))


@router.get("/school.xlsx")
async def export_school_data(request: Request, db: DbDep,
                             admin: Annotated[User, AdminOnly]):
    """Everything the school would need to walk away, in one Excel workbook."""
    school_id = tenant_scope(admin)
    data = await build_school_export(db, school_id)

    # exports are sensitive (every child, every payment) — leave a trace
    await record_audit(db, school_id=school_id, user_id=admin.id, action="export",
                       table_name="school", record_id=school_id,
                       changes={"export": {"old": None, "new": "full_workbook"}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="fiyox-school-export-{stamp}.xlsx"'})
