"""CBT schemas — exam authoring, the student sitting view, and results."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# ---------- authoring ----------
class QuestionIn(BaseModel):
    type: str = "single"
    text: str
    options: list[dict] = Field(default_factory=list)  # [{"id","text"}]
    correct: Any = None          # shape depends on type (see model docstring)
    marks: float = 1.0
    sequence: int = 0


class QuestionOut(BaseModel):
    """Author view — includes the answer key."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    text: str
    options: list[dict]
    correct: Any
    marks: float
    sequence: int


class ExamIn(BaseModel):
    title: str
    subject_id: str
    arm_id: str
    term_id: str
    instructions: str = ""
    duration_minutes: int = 30
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    shuffle_questions: bool = True
    show_results_immediately: bool = True
    max_attempts: int = 1


class ExamPatch(BaseModel):
    title: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    shuffle_questions: bool | None = None
    show_results_immediately: bool | None = None
    max_attempts: int | None = None


class ExamOut(BaseModel):
    """Summary row used in staff + student lists."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    subject_id: str
    arm_id: str
    term_id: str
    duration_minutes: int
    opens_at: datetime | None
    closes_at: datetime | None
    shuffle_questions: bool
    show_results_immediately: bool
    max_attempts: int
    total_marks: float
    question_count: int
    status: str
    # resolved labels for display (filled by the route, not the ORM)
    subject_name: str | None = None
    class_label: str | None = None


class ExamDetailOut(ExamOut):
    instructions: str = ""
    questions: list[QuestionOut] = Field(default_factory=list)


# ---------- sitting (student) ----------
class SubmitIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)  # question_id -> answer
    auto: bool = False  # set by the client when the timer ran out
