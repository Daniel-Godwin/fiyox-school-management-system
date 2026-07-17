"""Contact verification endpoints.

Two calls: request a code, confirm a code. Verifying is something a user does
for *their own* contact — an admin cannot mark someone verified by hand, which
is what keeps the tick trustworthy.

Rural reality check: if the SMS never arrives (poor coverage, dead SIM),
nothing is lost — the account still works with its password. Verification
changes what the school *knows*, never what the parent can do.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep
from app.models.notifications import MessagePurpose
from app.models.verification import VerificationCode, VerifyChannel, VerifyPurpose
from app.services.audit import record_audit
from app.services.notify import get_provider, send_sms_and_log

router = APIRouter(prefix="/api/verify", tags=["verification"])

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
MAX_CODES_PER_HOUR = 3


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class RequestIn(BaseModel):
    channel: VerifyChannel


class ConfirmIn(BaseModel):
    channel: VerifyChannel
    code: str


@router.post("/request")
async def request_code(payload: RequestIn, request: Request, db: DbDep,
                       user: CurrentUser):
    """Send a 6-digit code to the caller's own phone (or email, when a mail
    provider is configured)."""
    school_id = user.school_id
    contact = user.phone if payload.channel == VerifyChannel.PHONE else user.email
    if not contact:
        raise HTTPException(
            status_code=400,
            detail=f"No {payload.channel.value} is on your account — ask the "
                   "school to add it first")

    already = (user.phone_verified if payload.channel == VerifyChannel.PHONE
               else user.email_verified)
    if already:
        return {"sent": False, "note": f"Your {payload.channel.value} is already verified."}

    # rate limit: max 3 codes per contact per hour — protects the person from
    # SMS bombardment and the school from a drained Termii balance
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = (await db.execute(select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.channel == payload.channel,
        VerificationCode.created_at >= hour_ago))).scalars().all()
    if len(recent) >= MAX_CODES_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many codes requested. Wait an hour and try again.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(VerificationCode(
        school_id=school_id, user_id=user.id, channel=payload.channel,
        purpose=VerifyPurpose.VERIFY_CONTACT, contact=contact,
        code_hash=_hash(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES),
        created_by=user.id))

    if payload.channel == VerifyChannel.PHONE:
        await send_sms_and_log(
            db, school_id=school_id, to=contact,
            body=f"Your Fiyox verification code is {code}. "
                 f"It expires in {CODE_TTL_MINUTES} minutes.",
            purpose=MessagePurpose.ANNOUNCEMENT,
            recipient_user_id=user.id, created_by=user.id)
        await db.commit()
        provider = get_provider()
        return {
            "sent": True,
            "channel": "phone",
            "expires_in_minutes": CODE_TTL_MINUTES,
            "note": ("The code was logged but NOT delivered — SMS is in preview "
                     "mode until the school sets TERMII_API_KEY."
                     if provider.name == "mock" else
                     f"A code was sent to {contact[:4]}…{contact[-3:]}."),
        }

    # email: no mail provider is wired yet, so be honest rather than pretend
    await db.commit()
    return {
        "sent": False,
        "channel": "email",
        "note": ("Email delivery is not configured yet. Phone verification is "
                 "available now; email will follow when the school connects a "
                 "mail provider."),
    }


@router.post("/confirm")
async def confirm_code(payload: ConfirmIn, request: Request, db: DbDep,
                       user: CurrentUser):
    """Check a code and, if right, mark the contact verified."""
    now = datetime.now(timezone.utc)
    vc = (await db.execute(select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.channel == payload.channel,
        VerificationCode.purpose == VerifyPurpose.VERIFY_CONTACT,
        VerificationCode.used == False)  # noqa: E712
        .order_by(VerificationCode.created_at.desc()))).scalars().first()

    if not vc:
        raise HTTPException(status_code=404,
                            detail="No code is waiting — request one first")

    expires = vc.expires_at if vc.expires_at.tzinfo else vc.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise HTTPException(status_code=400,
                            detail="That code has expired — request a new one")
    if vc.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429,
                            detail="Too many wrong attempts — request a new code")

    if _hash(payload.code.strip()) != vc.code_hash:
        vc.attempts += 1
        await db.commit()
        left = MAX_ATTEMPTS - vc.attempts
        raise HTTPException(status_code=400,
                            detail=f"Wrong code — {left} attempt(s) left")

    # the contact must still be the one the code was sent to
    current = user.phone if payload.channel == VerifyChannel.PHONE else user.email
    if current != vc.contact:
        raise HTTPException(status_code=400,
                            detail="Your contact details changed since this code "
                                   "was sent — request a new one")

    vc.used = True
    if payload.channel == VerifyChannel.PHONE:
        user.phone_verified = True
    else:
        user.email_verified = True
    await record_audit(db, school_id=user.school_id, user_id=user.id,
                       action="update", table_name="users", record_id=user.id,
                       changes={f"{payload.channel.value}_verified":
                                {"old": False, "new": True}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"verified": True, "channel": payload.channel.value}


@router.get("/availability")
async def verification_availability(user: CurrentUser):
    """Which verification channels can actually deliver right now?

    The parent-facing UI must not invite anyone to "send a code" that cannot
    arrive. When SMS is in preview mode (no Termii key), phone verification is
    reported unavailable and the banner simply does not render.
    """
    from app.services.notify import get_provider
    return {
        "phone": get_provider().name != "mock",
        "email": False,   # becomes true when a mail provider is wired
    }
