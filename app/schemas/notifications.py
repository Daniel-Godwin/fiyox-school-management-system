"""Notification schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.notifications import Channel, MessageStatus, MessagePurpose


class FeeReminderIn(BaseModel):
    term_id: str


class MessageLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    channel: Channel
    recipient: str
    body: str
    purpose: MessagePurpose
    status: MessageStatus
    provider: str
    error: str | None = None
    created_at: datetime
