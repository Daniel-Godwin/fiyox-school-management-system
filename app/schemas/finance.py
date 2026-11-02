"""Finance schemas — expenses, income, salaries, payroll."""
from datetime import date
from pydantic import BaseModel, Field


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ExpenseIn(BaseModel):
    spent_on: date
    category_id: str | None = None
    description: str = Field(min_length=1, max_length=300)
    amount: float = Field(gt=0)
    payee: str | None = Field(default=None, max_length=160)
    method: str = "cash"
    note: str | None = None


class IncomeIn(BaseModel):
    received_on: date
    source: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=300)
    amount: float = Field(gt=0)
    method: str = "cash"


class SalaryIn(BaseModel):
    staff_user_id: str
    gross: float = Field(ge=0)
    deduction: float = Field(default=0, ge=0)
    is_active: bool = True


class PayrollRunIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")   # YYYY-MM
    note: str | None = Field(default=None, max_length=300)


class PayslipAdjustIn(BaseModel):
    gross: float | None = Field(default=None, ge=0)
    deduction: float | None = Field(default=None, ge=0)
