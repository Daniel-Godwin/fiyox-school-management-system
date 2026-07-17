"""User management + self-service auth schemas."""
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.school import Role


class UserCreate(BaseModel):
    email: EmailStr
    role: Role
    first_name: str
    last_name: str
    phone: str | None = None
    # omit to auto-generate a temporary password (returned once in the response)
    password: str | None = Field(default=None, min_length=6)
    # for role=student: link the account to an existing student record
    student_id: str | None = None
    # for role=parent: link one or more wards at creation
    ward_student_ids: list[str] = []


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    role: Role
    first_name: str
    last_name: str
    phone: str | None = None
    phone_verified: bool = False
    email_verified: bool = False
    is_active: bool


class UserCreatedOut(BaseModel):
    user: UserAdminOut
    temporary_password: str | None = None  # only when auto-generated


class UserStatusIn(BaseModel):
    is_active: bool


class WardLinkIn(BaseModel):
    student_id: str
    relationship: str | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)
