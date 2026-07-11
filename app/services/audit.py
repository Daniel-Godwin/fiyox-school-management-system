"""Reusable audit recorder. Callers add the log then commit with their own work,
so the audit entry lands in the same transaction as the change it describes."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog


async def record_audit(db: AsyncSession, *, school_id: str | None, user_id: str | None,
                       action: str, table_name: str, record_id: str | None,
                       changes: dict | None = None, ip_address: str | None = None) -> None:
    db.add(AuditLog(
        school_id=school_id, user_id=user_id, action=action,
        table_name=table_name, record_id=record_id,
        changes=changes or {}, ip_address=ip_address,
    ))
