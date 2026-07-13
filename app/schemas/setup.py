"""Academic setup schemas — how a new school configures itself."""
from pydantic import BaseModel, Field
from app.models.academics import ClassCategory, TermName


class SessionIn(BaseModel):
    name: str = Field(examples=["2025/2026"])
    is_current: bool = True


class TermIn(BaseModel):
    session_id: str
    name: TermName
    is_current: bool = True


class ClassIn(BaseModel):
    name: str = Field(examples=["JSS1"])
    category: ClassCategory
    level_order: int = 0


class ArmIn(BaseModel):
    class_id: str
    name: str = Field(examples=["A"])


class SubjectIn(BaseModel):
    name: str
    code: str | None = None
    category: ClassCategory | None = None


class QuickSetupIn(BaseModel):
    """One call that gives a brand-new school a working structure."""
    session_name: str = Field(default="2025/2026", examples=["2025/2026"])
    term: TermName = TermName.FIRST
    classes: list[str] = Field(default_factory=lambda: ["JSS1", "JSS2", "JSS3"])
    arms: list[str] = Field(default_factory=lambda: ["A"])
    subjects: list[str] = Field(
        default_factory=lambda: ["Mathematics", "English Language", "Basic Science"])
    # standard Nigerian CA/exam split
    with_default_components: bool = True
