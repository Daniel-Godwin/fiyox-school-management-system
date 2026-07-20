"""Finance schemas."""
from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from app.models.fees import InvoiceStatus, PaymentMethod


class CategoryIn(BaseModel):
    name: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class StructureIn(BaseModel):
    class_id: str
    term_id: str
    category_id: str
    amount: float = Field(ge=0)


class StructureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    class_id: str
    term_id: str
    category_id: str
    amount: float


class GenerateInvoicesIn(BaseModel):
    arm_id: str
    term_id: str
    due_date: date | None = None


class InvoiceLine(BaseModel):
    """One billed category, frozen as at invoice generation."""
    name: str
    amount: float


class InvoiceOut(BaseModel):
    id: str
    student_id: str
    term_id: str
    invoice_number: str
    amount: float
    discount: float
    paid: float
    balance: float
    status: InvoiceStatus
    due_date: date | None = None
    items: list[InvoiceLine] = []


class PaymentIn(BaseModel):
    invoice_id: str
    method: PaymentMethod
    reference: str = Field(min_length=3, max_length=80)
    amount: float = Field(gt=0)
    paid_at: date | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    invoice_id: str
    method: PaymentMethod
    reference: str
    amount: float
