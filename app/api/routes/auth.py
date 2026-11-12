"""Authentication endpoints: login (with lockout), change / reset password."""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.core.deps import DbDep, CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models.school import User, Role, School
from app.models.notifications import MessagePurpose
from app.models.verification import VerificationCode, VerifyChannel, VerifyPurpose
from app.services.notify import send_email_and_log
from app.schemas import Token, UserOut, ChangePasswordIn

router = APIRouter(prefix="/api/auth", tags=["auth"])

# --- password-reset codes --------------------------------------------------
RESET_TTL_MINUTES = 15        # a reset code is valid for this long
RESET_MAX_PER_HOUR = 5        # reset codes per account per hour
RESET_MAX_ATTEMPTS = 5        # wrong code entries before the code is dead


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


# --- login lockout (in-memory, per-process) --------------------------------
# A sliding-window guard against password guessing, keyed by email. In-process
# state suits a single web instance; it resets on restart, which only ever errs
# toward leniency (never toward locking someone out for longer than intended).
_LOGIN_FAILURES: dict[str, list[float]] = {}
LOCKOUT_THRESHOLD = 5             # this many failures...
LOCKOUT_WINDOW_SECONDS = 15 * 60  # ...inside this rolling window locks the email


def _lockout_remaining(email: str) -> int:
    """Seconds left on a lockout for this email, or 0 if not locked."""
    now = time.time()
    fails = [t for t in _LOGIN_FAILURES.get(email, [])
             if now - t < LOCKOUT_WINDOW_SECONDS]
    if fails:
        _LOGIN_FAILURES[email] = fails
    else:
        _LOGIN_FAILURES.pop(email, None)
    if len(fails) >= LOCKOUT_THRESHOLD:
        return max(int(LOCKOUT_WINDOW_SECONDS - (now - min(fails))), 1)
    return 0


def _record_login_failure(email: str) -> None:
    _LOGIN_FAILURES.setdefault(email, []).append(time.time())


def _clear_login_failures(email: str) -> None:
    _LOGIN_FAILURES.pop(email, None)


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

    # brute-force guard: stop repeated guesses before touching the database
    locked = _lockout_remaining(email)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=(f"Too many failed attempts. Try again in about "
                    f"{max(1, locked // 60)} minute(s), or reset your password."))

    rows = (await db.execute(select(User).where(
        func.lower(User.email) == email,
        User.deleted_at.is_(None),
    ))).scalars().all()

    # accounts whose password matches the one supplied
    pw_ok = [u for u in rows if verify_password(form.password, u.hashed_password)]
    if not pw_ok:
        _record_login_failure(email)
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

    _clear_login_failures(email)
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


# --- self-service password reset -------------------------------------------
class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    email: str
    code: str
    new_password: str = Field(min_length=8)


async def _single_live_user(db, email: str) -> User | None:
    """The one active, non-deleted account for an email, or None if none/many."""
    rows = (await db.execute(select(User).where(
        func.lower(User.email) == email,
        User.deleted_at.is_(None),
        User.is_active.is_(True),
    ))).scalars().all()
    return rows[0] if len(rows) == 1 else None


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, db: DbDep):
    """Email a reset code to a staff member who is locked out. The response is
    identical whether or not the email exists, so it cannot be used to discover
    which emails have accounts."""
    email = payload.email.strip().lower()
    generic = {"sent": True,
               "note": ("If an account exists for that email, a reset code has "
                        "been sent. Check your inbox and spam folder.")}

    user = await _single_live_user(db, email)
    # self-service reset is for school staff (codes are tenant-scoped); the
    # platform owner has no school and resets through the admin tooling
    if not user or not user.email or user.school_id is None:
        return generic

    # rate-limit reset requests per account per hour
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = (await db.execute(select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.purpose == VerifyPurpose.RESET_PASSWORD,
        VerificationCode.created_at >= hour_ago))).scalars().all()
    if len(recent) >= RESET_MAX_PER_HOUR:
        return generic  # silently capped — do not reveal anything

    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(VerificationCode(
        school_id=user.school_id, user_id=user.id, channel=VerifyChannel.EMAIL,
        purpose=VerifyPurpose.RESET_PASSWORD, contact=user.email,
        code_hash=_hash(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TTL_MINUTES),
        created_by=user.id))
    await send_email_and_log(
        db, school_id=user.school_id, to=user.email,
        subject="Reset your Fiyox password",
        body=(f"Your Fiyox password reset code is {code}.\n\n"
              f"It expires in {RESET_TTL_MINUTES} minutes. If you did not request "
              f"a password reset, you can ignore this email — your password has "
              f"not changed."),
        purpose=MessagePurpose.ANNOUNCEMENT,
        recipient_user_id=user.id, created_by=user.id)
    await db.commit()
    return generic


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn, db: DbDep):
    """Set a new password using a code from the forgot-password email."""
    email = payload.email.strip().lower()
    invalid = HTTPException(status_code=400,
                            detail="Invalid or expired reset code")

    user = await _single_live_user(db, email)
    if not user:
        raise invalid

    vc = (await db.execute(select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.purpose == VerifyPurpose.RESET_PASSWORD,
        VerificationCode.used == False)  # noqa: E712
        .order_by(VerificationCode.created_at.desc()))).scalars().first()
    if not vc:
        raise invalid

    now = datetime.now(timezone.utc)
    expires = vc.expires_at if vc.expires_at.tzinfo else vc.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise invalid
    if vc.attempts >= RESET_MAX_ATTEMPTS:
        raise HTTPException(status_code=429,
                            detail="Too many attempts — request a new reset code")
    if _hash(payload.code.strip()) != vc.code_hash:
        vc.attempts += 1
        await db.commit()
        raise invalid

    vc.used = True
    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    user.updated_by = user.id
    await db.commit()
    _clear_login_failures(email)  # a successful reset lifts any login lockout
    return {"reset": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
