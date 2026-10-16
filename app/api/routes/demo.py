"""Public demo requests from the landing page, plus the owner's view of them."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.core.deps import DbDep, require_roles
from app.models.demo import DemoRequest
from app.models.school import Role, User

router = APIRouter(prefix="/api/demo-requests", tags=["demo"])

OwnerOnly = Depends(require_roles(Role.SUPER_ADMIN))


class DemoRequestIn(BaseModel):
    school_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=2000)


@router.post("", status_code=201)
async def create_demo_request(payload: DemoRequestIn, db: DbDep):
    """Public — anyone on the landing page can ask for a demo."""
    req = DemoRequest(
        school_name=payload.school_name.strip(),
        contact_name=payload.contact_name.strip(),
        email=str(payload.email).strip().lower(),
        phone=(payload.phone or "").strip() or None,
        message=(payload.message or "").strip() or None)
    db.add(req)
    await db.commit()
    return {"received": True,
            "note": "Thank you — we will be in touch shortly."}


@router.get("")
async def list_demo_requests(db: DbDep, owner: Annotated[User, OwnerOnly]):
    """Platform owner sees every demo request, newest first."""
    rows = (await db.execute(select(DemoRequest).where(
        DemoRequest.deleted_at.is_(None)))).scalars().all()
    rows.sort(key=lambda r: str(r.created_at), reverse=True)
    return [{
        "id": r.id, "school_name": r.school_name, "contact_name": r.contact_name,
        "email": r.email, "phone": r.phone, "message": r.message,
        "handled": r.handled, "created_at": str(r.created_at)[:16],
    } for r in rows]


@router.patch("/{request_id}")
async def mark_handled(request_id: str, db: DbDep,
                       owner: Annotated[User, OwnerOnly], handled: bool = True):
    req = await db.get(DemoRequest, request_id)
    if not req or req.deleted_at:
        raise HTTPException(status_code=404, detail="Request not found")
    req.handled = handled
    await db.commit()
    return {"id": req.id, "handled": req.handled}
