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
    shuffle_options: bool = True
    show_results_immediately: bool = True
    max_attempts: int = 1
    # result-sheet column this test counts towards; None = practice only
    component_id: str | None = None
    # question sourcing: "manual" or "pool" (draw a balanced set from the bank)
    source: str = "manual"
    pool_size: int = 0
    difficulty_ratio: dict = Field(default_factory=dict)
    # anti-cheat
    proctored: bool = False
    max_violations: int = 3


class ExamPatch(BaseModel):
    title: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    shuffle_questions: bool | None = None
    shuffle_options: bool | None = None
    show_results_immediately: bool | None = None
    max_attempts: int | None = None
    component_id: str | None = None
    source: str | None = None
    pool_size: int | None = None
    difficulty_ratio: dict | None = None
    proctored: bool | None = None
    max_violations: int | None = None


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
    component_id: str | None = None
    shuffle_options: bool = True
    source: str = "manual"
    pool_size: int = 0
    difficulty_ratio: dict = Field(default_factory=dict)
    proctored: bool = False
    max_violations: int = 3
    # resolved labels for display (filled by the route, not the ORM)
    subject_name: str | None = None
    class_label: str | None = None
    component_name: str | None = None


class ExamDetailOut(ExamOut):
    instructions: str = ""
    questions: list[QuestionOut] = Field(default_factory=list)


# ---------- sitting (student) ----------
class SubmitIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)  # question_id -> answer
    auto: bool = False  # set by the client when the timer ran out


# ---------- question bank ----------
class BankQuestionIn(BaseModel):
    subject_id: str
    term_id: str | None = None
    topic: str = ""
    difficulty: str = "medium"       # easy | medium | hard
    type: str = "single"
    text: str
    options: list[dict] = Field(default_factory=list)
    correct: Any = None
    marks: float = 1.0
    active: bool = True


class BankQuestionPatch(BaseModel):
    term_id: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    type: str | None = None
    text: str | None = None
    options: list[dict] | None = None
    correct: Any = None
    marks: float | None = None
    active: bool | None = None


class BankQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    subject_id: str
    term_id: str | None = None
    topic: str
    difficulty: str
    type: str
    text: str
    options: list[dict]
    correct: Any
    marks: float
    active: bool
    subject_name: str | None = None


class BankSummary(BaseModel):
    """Per-difficulty counts for a subject, for the balancing UI."""
    subject_id: str
    easy: int = 0
    medium: int = 0
    hard: int = 0
    total: int = 0


class ViolationIn(BaseModel):
    kind: str = "tab_switch"     # tab_switch | blur | fullscreen_exit | ...
    detail: str = ""


class ExtendIn(BaseModel):
    minutes: int = 5


class ImportItem(BaseModel):
    text: str = ""
    type: str = "single"
    options: list[dict] = Field(default_factory=list)
    correct: Any = None
    difficulty: str = "medium"
    topic: str = ""
    marks: float = 1.0


class BankImportIn(BaseModel):
    subject_id: str
    questions: list[ImportItem] = Field(default_factory=list)


class FromBankIn(BaseModel):
    """Pull a balanced set of bank questions into a draft exam as real,
    attached questions."""
    count: int = 20
    difficulty_ratio: dict = Field(default_factory=dict)
