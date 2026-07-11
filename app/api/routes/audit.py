"""Audit-trail endpoints (school admin)."""
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.audit import AuditLog

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
    limit: int = Query(50, le=200),
    table_name: str | None = Query(None),
):
    school_id = tenant_scope(user)
    stmt = select(AuditLog).where(AuditLog.school_id == school_id)
    if table_name:
        stmt = stmt.where(AuditLog.table_name == table_name)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"action": r.action, "table": r.table_name, "record_id": r.record_id,
             "changes": r.changes, "user_id": r.user_id, "ip": r.ip_address,
             "at": r.created_at.isoformat()} for r in rows]
