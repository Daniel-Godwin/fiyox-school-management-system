"""Result-engine schemas."""
from pydantic import BaseModel, ConfigDict


class ComponentIn(BaseModel):
    name: str
    max_score: int = 10
    is_exam: bool = False
    sequence: int = 0


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    max_score: int
    is_exam: bool
    sequence: int


class ScoreRow(BaseModel):
    student_id: str
    scores: dict[str, float]  # component_id -> score


class BulkScoresIn(BaseModel):
    subject_id: str
    arm_id: str
    term_id: str
    rows: list[ScoreRow]


class ComputeIn(BaseModel):
    arm_id: str
    term_id: str


class TermResultUpdate(BaseModel):
    affective: dict | None = None
    form_teacher_comment: str | None = None
    principal_comment: str | None = None
    is_published: bool | None = None
