"""Notification service.

Provider abstraction: with no TERMII_API_KEY configured, the MockProvider is
used — messages are fully logged with status 'mock' but nothing leaves the
server (safe for dev, tests, and demos). Set TERMII_API_KEY (+ optional
TERMII_SENDER_ID) and the same code path transmits real SMS via Termii.
Every message, real or mock, lands in message_logs.
"""
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.school import User, Role
from app.models.student import Student, Guardian
from app.models.communication import AnnouncementTarget
from app.models.notifications import (
    MessageLog, Channel, MessageStatus, MessagePurpose,
)

TERMII_SMS_URL = "https://api.termii.com/api/sms/send"


def normalize_msisdn(raw: str) -> str:
    """Put a Nigerian number into the international format Termii expects.

    Schools enter numbers however they like — 08031234567, 0803 123 4567,
    +234 803… — but Termii only accepts 2348031234567. Left unnormalized, every
    message would silently fail. Rules:
      08031234567   -> 2348031234567   (drop the leading 0, prepend 234)
      8031234567    -> 2348031234567   (bare 10-digit)
      +2348031234567 / 2348031234567 -> 2348031234567 (already international)
    Non-Nigerian or unrecognizable numbers are returned digits-only, untouched
    otherwise, so international parents still work.
    """
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("234"):
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return "234" + digits[1:]
    if len(digits) == 10:            # bare line without the leading 0
        return "234" + digits
    return digits


class MockProvider:
    name = "mock"

    async def send_sms(self, to: str, body: str) -> tuple[MessageStatus, str | None, str | None]:
        return MessageStatus.MOCK, None, None


class TermiiProvider:
    name = "termii"

    def __init__(self, api_key: str, sender_id: str):
        self.api_key = api_key
        self.sender_id = sender_id

    async def send_sms(self, to: str, body: str) -> tuple[MessageStatus, str | None, str | None]:
        payload = {
            "to": normalize_msisdn(to), "from": self.sender_id, "sms": body,
            "type": "plain", "channel": "generic", "api_key": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(TERMII_SMS_URL, json=payload)
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                if r.status_code == 200 and data.get("message_id"):
                    return MessageStatus.SENT, str(data["message_id"]), None
                return MessageStatus.FAILED, None, f"HTTP {r.status_code}: {data or r.text[:200]}"
        except Exception as e:  # network failure must never crash the request
            return MessageStatus.FAILED, None, str(e)[:300]


def get_provider():
    if settings.TERMII_API_KEY:
        sender = getattr(settings, "TERMII_SENDER_ID", None) or "Fiyox"
        return TermiiProvider(settings.TERMII_API_KEY, sender)
    return MockProvider()


async def send_sms_and_log(db: AsyncSession, *, school_id: str, to: str,
                           body: str, purpose: MessagePurpose,
                           recipient_user_id: str | None = None,
                           related_id: str | None = None,
                           created_by: str | None = None) -> MessageLog:
    provider = get_provider()
    status, ref, error = await provider.send_sms(to, body)
    log = MessageLog(
        school_id=school_id, channel=Channel.SMS, recipient=to,
        recipient_user_id=recipient_user_id, body=body, purpose=purpose,
        related_id=related_id, status=status, provider=provider.name,
        provider_ref=ref, error=error, created_by=created_by)
    db.add(log)
    return log


# ---------- recipient resolution ----------

_TARGET_ROLES = {
    AnnouncementTarget.ALL: [Role.TEACHER, Role.PARENT, Role.STUDENT, Role.BURSAR],
    AnnouncementTarget.TEACHERS: [Role.TEACHER],
    AnnouncementTarget.PARENTS: [Role.PARENT],
    AnnouncementTarget.STUDENTS: [Role.STUDENT],
}


async def recipients_for_target(db: AsyncSession, school_id: str,
                                target: AnnouncementTarget) -> list[User]:
    roles = _TARGET_ROLES[AnnouncementTarget(target)]
    rows = (await db.execute(select(User).where(
        User.school_id == school_id,
        User.role.in_([r.value for r in roles]),
        User.is_active == True,        # noqa: E712
        User.phone.is_not(None)))).scalars().all()
    return [u for u in rows if (u.phone or "").strip()]


async def guardians_of(db: AsyncSession, school_id: str,
                       student_id: str) -> list[User]:
    links = (await db.execute(select(Guardian).where(
        Guardian.school_id == school_id,
        Guardian.student_id == student_id))).scalars().all()
    users = []
    for link in links:
        u = await db.get(User, link.parent_user_id)
        if u and u.is_active and (u.phone or "").strip():
            users.append(u)
    return users


async def student_name(db: AsyncSession, student_id: str) -> str:
    st = await db.get(Student, student_id)
    return f"{st.first_name} {st.last_name}" if st else "your ward"
