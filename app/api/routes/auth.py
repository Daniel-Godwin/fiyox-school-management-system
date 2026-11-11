"""Authentication endpoints."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from app.core.deps import DbDep, CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models.school import User, Role, School
from app.schemas import Token, UserOut, ChangePasswordIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep):
    # OAuth2 form uses 'username'; we treat it as email. Emails are globally
    # unique, but historic/offboarded data could still leave more than one row
    # for an address, so login must resolve to exactly ONE account that can
    # actually sign in — it must never silently pick one of several.
    #
    # email is matched case-insensitively and trimmed: phone keyboards capitalise
    # the first letter and may add a trailing space, which must not block login.
    email = form.username.strip().lower()
    rows = (await db.execute(select(User).where(
        func.lower(User.email) == email,
        User.deleted_at.is_(None),
    ))).scalars().all()

    # accounts whose password matches the one supplied
    pw_ok = [u for u in rows if verify_password(form.password, u.hashed_password)]
    if not pw_ok:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # of those, the ones that can genuinely sign in: active, and — for staff —
    # belonging to a school that still exists and is open. An offboarded school's
    # accounts therefore never shadow a live account that shares the email.
    eligible: list[User] = []
    for u in pw_ok:
        if not u.is_active:
            continue
        if u.school_id is not None:
            school = await db.get(School, u.school_id)
            if not school or school.deleted_at is not None or not school.is_active:
                continue
        eligible.append(u)

    if len(eligible) == 1:
        user = eligible[0]
    elif not eligible:
        # the password matched only a deactivated or offboarded account
        raise HTTPException(status_code=403,
                            detail="This account has been deactivated — contact your school admin")
    else:
        # more than one live account shares this email+password — refuse to guess
        raise HTTPException(status_code=409,
                            detail="This email is linked to more than one active account — contact support")

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
    fresh.must_change_password = False
    fresh.updated_by = user.id
    await db.commit()
    return {"changed": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
