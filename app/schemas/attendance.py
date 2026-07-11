"""Attendance schemas."""
from datetime import date
from pydantic import BaseModel
from app.models.attendance import AttendanceStatus


class MarkRecord(BaseModel):
    student_id: str
    status: AttendanceStatus
    remark: str | None = None


class MarkAttendanceIn(BaseModel):
    arm_id: str
    date: date
    records: list[MarkRecord]


class AttendanceRow(BaseModel):
    student_id: str
    date: date
    status: AttendanceStatus
    remark: str | None = None


class AttendanceSummary(BaseModel):
    student_id: str
    days_recorded: int
    present: int
    absent: int
    late: int
    excused: int
