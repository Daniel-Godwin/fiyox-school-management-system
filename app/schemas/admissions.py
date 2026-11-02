"""Admissions schemas — the public application, the entrance test, and the
admin review views."""
from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- public application ----------
class ApplicationIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    other_names: str | None = Field(default=None, max_length=100)
    gender: str
    date_of_birth: date | None = None
    applying_class_id: str
    previous_school: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    guardian_name: str = Field(min_length=1, max_length=160)
    guardian_phone: str = Field(min_length=1, max_length=40)
    guardian_email: EmailStr | None = None


class ApplicantCredentials(BaseModel):
    """What an applicant sends to prove ownership of their application."""
    application_number: str
    access_code: str


class EntranceSubmitIn(ApplicantCredentials):
    answers: dict[str, Any] = Field(default_factory=dict)
    auto: bool = False


# ---------- admin: entrance test authoring ----------
class AdmTestIn(BaseModel):
    title: str
    instructions: str = ""
    applying_class_id: str | None = None
    duration_minutes: int = 30
    shuffle_questions: bool = True


class AdmTestPatch(BaseModel):
    title: str | None = None
    instructions: str | None = None
    applying_class_id: str | None = None
    duration_minutes: int | None = None
    shuffle_questions: bool | None = None
    is_active: bool | None = None


class AdmQuestionIn(BaseModel):
    type: str = "single"
    text: str
    options: list[dict] = Field(default_factory=list)
    correct: Any = None
    marks: float = 1.0
    sequence: int = 0


# ---------- admin: review + admit ----------
class ApplicantStatusIn(BaseModel):
    status: str
    note: str | None = None


class AdmitIn(BaseModel):
    admission_number: str
    arm_id: str | None = None
