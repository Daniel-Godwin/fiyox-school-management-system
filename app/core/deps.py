"""Request dependencies: resolve the current user, their tenant, and enforce roles.

Every protected endpoint depends on get_current_user, which reads the JWT and
pins the request to exactly one school_id. Role guards layer on top of that.
"""
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.school import User, Role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbDep
) -> User:
    cred_err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise cred_err
    except Exception:
        raise cred_err

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise cred_err
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: Role):
    """Dependency factory: allow only the given roles."""
    async def _guard(user: CurrentUser) -> User:
        if user.role not in allowed and user.role != Role.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission for this action",
            )
        return user
    return _guard


def tenant_scope(user: CurrentUser) -> str:
    """Return the school_id the request is confined to. Super admin must scope
    explicitly (handled per-endpoint); everyone else is auto-pinned."""
    if user.school_id is None and user.role != Role.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="User is not attached to a school")
    return user.school_id
