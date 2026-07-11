"""Announcement schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.communication import AnnouncementTarget


class AnnouncementIn(BaseModel):
    title: str
    message: str
    target: AnnouncementTarget = AnnouncementTarget.ALL
    publish: bool = True   # False = save as draft (admins only can see drafts)


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    message: str
    target: AnnouncementTarget
    published_at: datetime | None = None
