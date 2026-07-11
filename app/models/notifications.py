"""Notification delivery log — every outbound message leaves a row, whatever the
provider. This is the school's proof of 'we told the parents'."""
import enum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class Channel(str, enum.Enum):
    SMS = "sms"
    EMAIL = "email"


class MessageStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"
    MOCK = "mock"       # recorded but not actually transmitted (no provider key)


class MessagePurpose(str, enum.Enum):
    ANNOUNCEMENT = "announcement"
    FEE_REMINDER = "fee_reminder"
    RESULT_PUBLISHED = "result_published"
    CUSTOM = "custom"


class MessageLog(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "message_logs"

    channel: Mapped[Channel] = mapped_column(String(10))
    recipient: Mapped[str] = mapped_column(String(120))        # phone or email
    recipient_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    purpose: Mapped[MessagePurpose] = mapped_column(String(20))
    related_id: Mapped[str | None] = mapped_column(String(36))  # announcement/invoice id
    status: Mapped[MessageStatus] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(String(20), default="mock")
    provider_ref: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(String(300))
