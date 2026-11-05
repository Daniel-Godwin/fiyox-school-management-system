"""Notification service.

Provider abstraction: with no TERMII_API_KEY configured, the MockProvider is
used — messages are fully logged with status 'mock' but nothing leaves the
server (safe for dev, tests, and demos). Set TERMII_API_KEY (+ optional
TERMII_SENDER_ID) and the same code path transmits real SMS via Termii.
Every message, real or mock, lands in message_logs.
"""
import asyncio
import smtplib
from email.message import EmailMessage

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

def _termii_sms_url() -> str:
    base = (settings.TERMII_BASE_URL or "https://v3.api.termii.com").rstrip("/")
    return f"{base}/api/sms/send"


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

    def __init__(self, api_key: str, sender_id: str, channel: str = "dnd"):
        self.api_key = api_key
        self.sender_id = sender_id
        self.channel = channel

    async def send_sms(self, to: str, body: str) -> tuple[MessageStatus, str | None, str | None]:
        payload = {
            "to": normalize_msisdn(to), "from": self.sender_id, "sms": body,
            "type": "plain", "channel": self.channel, "api_key": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(_termii_sms_url(), json=payload)
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                if r.status_code == 200 and data.get("message_id"):
                    return MessageStatus.SENT, str(data["message_id"]), None
                return MessageStatus.FAILED, None, f"HTTP {r.status_code}: {data or r.text[:200]}"
        except Exception as e:  # network failure must never crash the request
            return MessageStatus.FAILED, None, str(e)[:300]


def get_provider():
    key = (settings.TERMII_API_KEY or "").strip()
    if key:
        sender = (getattr(settings, "TERMII_SENDER_ID", None) or "Termii").strip()
        channel = (getattr(settings, "TERMII_CHANNEL", None) or "dnd").strip()
        return TermiiProvider(key, sender, channel)
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


# ---------- email ----------

class MockEmailProvider:
    name = "mock"

    async def send_email(self, to: str, subject: str, body: str) -> tuple[MessageStatus, str | None, str | None]:
        return MessageStatus.MOCK, None, None


class SmtpEmailProvider:
    name = "smtp"

    def __init__(self, host: str, port: int, user: str | None, password: str | None,
                 sender: str, sender_name: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.sender_name = sender_name

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{self.sender_name} <{self.sender}>"
        msg["To"] = to
        msg.set_content(body)
        # STARTTLS on 587 (Gmail, most providers); implicit SSL on 465
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=20) as s:
                if self.user:
                    s.login(self.user, self.password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                s.starttls()
                if self.user:
                    s.login(self.user, self.password or "")
                s.send_message(msg)

    async def send_email(self, to: str, subject: str, body: str) -> tuple[MessageStatus, str | None, str | None]:
        try:
            # smtplib is blocking — keep it off the event loop
            await asyncio.to_thread(self._send_blocking, to, subject, body)
            return MessageStatus.SENT, None, None
        except Exception as e:  # a mail failure must never crash the request
            return MessageStatus.FAILED, None, str(e)[:300]


class ResendEmailProvider:
    """Sends over Resend's HTTPS API (port 443). Unlike SMTP, this works on
    hosts like Render that block outbound SMTP ports."""
    name = "resend"

    def __init__(self, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender  # "Name <addr>" or a bare address

    async def send_email(self, to: str, subject: str, body: str) -> tuple[MessageStatus, str | None, str | None]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"from": self.sender, "to": [to],
                          "subject": subject, "text": body},
                )
            if r.status_code // 100 == 2:
                ref = None
                try:
                    ref = r.json().get("id")
                except Exception:
                    pass
                return MessageStatus.SENT, ref, None
            # surface Resend's own explanation (e.g. domain not verified)
            return MessageStatus.FAILED, None, f"HTTP {r.status_code}: {r.text[:260]}"
        except Exception as e:
            return MessageStatus.FAILED, None, str(e)[:300]


def get_email_provider():
    # prefer Resend (HTTPS API — works where SMTP ports are blocked)
    key = (settings.RESEND_API_KEY or "").strip()
    if key:
        name = settings.SMTP_FROM_NAME or "Fiyox"
        addr = (settings.RESEND_FROM or "onboarding@resend.dev").strip()
        sender = addr if "<" in addr else f"{name} <{addr}>"
        return ResendEmailProvider(api_key=key, sender=sender)
    host = (settings.SMTP_HOST or "").strip()
    if host:
        sender = (settings.SMTP_FROM or settings.SMTP_USER or "").strip()
        return SmtpEmailProvider(
            host=host, port=settings.SMTP_PORT,
            user=(settings.SMTP_USER or "").strip() or None,
            password=settings.SMTP_PASSWORD,
            sender=sender, sender_name=settings.SMTP_FROM_NAME or "Fiyox")
    return MockEmailProvider()


async def send_email_and_log(db: AsyncSession, *, school_id: str, to: str,
                             subject: str, body: str, purpose: MessagePurpose,
                             recipient_user_id: str | None = None,
                             related_id: str | None = None,
                             created_by: str | None = None) -> MessageLog:
    provider = get_email_provider()
    status, ref, error = await provider.send_email(to, subject, body)
    log = MessageLog(
        school_id=school_id, channel=Channel.EMAIL, recipient=to,
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
