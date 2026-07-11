"""Announcement endpoints.

Visibility rule: admins see everything (including drafts); everyone else sees
published announcements targeted at 'all' or their own role group.
"""
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import or_, select
from app.core.deps import DbDep, CurrentUser, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.communication import Announcement, AnnouncementTarget
from app.schemas import AnnouncementIn, AnnouncementOut
from app.services.audit import record_audit

router = APIRouter(prefix="/api/announcements", tags=["announcements"])

ROLE_TARGET = {
    Role.TEACHER: AnnouncementTarget.TEACHERS,
    Role.PARENT: AnnouncementTarget.PARENTS,
    Role.STUDENT: AnnouncementTarget.STUDENTS,
}


@router.post("", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    payload: AnnouncementIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    ann = Announcement(
        school_id=school_id, title=payload.title, message=payload.message,
        target=payload.target,
        published_at=datetime.now(timezone.utc) if payload.publish else None,
        created_by=user.id)
    db.add(ann)
    await db.flush()
    await record_audit(db, school_id=school_id, user_id=user.id, action="create",
                       table_name="announcements", record_id=ann.id,
                       changes={"title": {"old": None, "new": payload.title},
                                "target": {"old": None, "new": payload.target}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(ann)
    return ann


@router.get("", response_model=list[AnnouncementOut])
async def list_announcements(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    stmt = select(Announcement).where(Announcement.school_id == school_id,
                                      Announcement.deleted_at.is_(None))

    if user.role in (Role.SCHOOL_ADMIN, Role.SUPER_ADMIN, Role.BURSAR):
        pass  # staff/admin see everything, drafts included
    else:
        group = ROLE_TARGET.get(user.role)
        targets = [AnnouncementTarget.ALL] + ([group] if group else [])
        stmt = stmt.where(Announcement.published_at.is_not(None),
                          or_(*[Announcement.target == t for t in targets]))

    stmt = stmt.order_by(Announcement.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())
