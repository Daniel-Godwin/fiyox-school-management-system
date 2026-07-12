"""Authentication endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models.school import User, Role
from app.schemas import Token, UserOut, ChangePasswordIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep):
    # OAuth2 form uses 'username'; we treat it as email. School is resolved from
    # the user record itself for MVP (subdomain routing comes with the frontend).
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalars().first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403,
                            detail="This account has been deactivated — contact your school admin")
    role_val = user.role.value if isinstance(user.role, Role) else user.role
    token = create_access_token(user.id, user.school_id, role_val)
    return Token(access_token=token)


@router.post("/change-password")
async def change_password(payload: ChangePasswordIn, db: DbDep, user: CurrentUser):
    """Self-service: any signed-in user rotates their own password (e.g. after
    receiving a temporary one from the admin)."""
    fresh = await db.get(User, user.id)
    if not verify_password(payload.current_password, fresh.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    fresh.hashed_password = hash_password(payload.new_password)
    fresh.updated_by = user.id
    await db.commit()
    return {"changed": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
