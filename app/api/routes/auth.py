"""Authentication endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser
from app.core.security import create_access_token, verify_password
from app.models.school import User, Role
from app.schemas import Token, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep):
    # OAuth2 form uses 'username'; we treat it as email. School is resolved from
    # the user record itself for MVP (subdomain routing comes with the frontend).
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalars().first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    role_val = user.role.value if isinstance(user.role, Role) else user.role
    token = create_access_token(user.id, user.school_id, role_val)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
