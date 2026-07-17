"""Auth & identity schemas."""
from pydantic import BaseModel, EmailStr, ConfigDict
from app.models.school import Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    school_slug: str | None = None  # which tenant to log into


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    role: Role
    first_name: str
    last_name: str
    school_id: str | None = None
    phone: str | None = None
    phone_verified: bool = False
    email_verified: bool = False
