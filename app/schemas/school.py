"""School (tenant) schemas."""
from pydantic import BaseModel, EmailStr, ConfigDict, Field


class SchoolCreate(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    admin_password: str = Field(min_length=6)
    admin_first_name: str
    admin_last_name: str
    state: str | None = None
    phone: str | None = None


class SchoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    state: str | None = None
    is_active: bool
