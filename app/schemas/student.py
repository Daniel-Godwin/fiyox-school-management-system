"""Student schemas."""
from pydantic import BaseModel, ConfigDict
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
