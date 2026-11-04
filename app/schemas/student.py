"""Student schemas."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.student import Gender


class StudentCreate(BaseModel):
    admission_number: str
    first_name: str
    last_name: str
    other_names: str | None = None
    gender: Gender
    current_arm_id: str | None = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    admission_number: str
    first_name: str
    last_name: str
    gender: Gender
    current_arm_id: str | None = None
    is_active: bool


class RenumberIn(BaseModel):
    """Re-sequence a whole class's admission numbers into a chosen format.

    `apply` false (the default) previews the before -> after mapping without
    changing anything; the admin reviews it, then sends `apply` true.
    """
    arm_id: str
    year: str                              # the year segment, e.g. "25"
    prefix: str | None = None              # defaults to the school's prefix
    start: int = Field(1, ge=1)
    pad: int | None = Field(None, ge=2, le=6)
    apply: bool = False

    @field_validator("year")
    @classmethod
    def _year(cls, v: str) -> str:
        v = "".join(c for c in v if c.isdigit())
        if len(v) < 2 or len(v) > 4:
            raise ValueError("year must be 2 to 4 digits, e.g. 25 or 2025")
        return v

    @field_validator("prefix")
    @classmethod
    def _prefix(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = "".join(c for c in v if c.isalnum()).upper()
        return v or None
