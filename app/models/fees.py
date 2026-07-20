"""Finance module — two rules keep this correct:

1. An invoice's balance is always derived: amount - discount - sum(payments).
   We never store a mutable 'balance' that can drift out of sync.
2. Payments are idempotent by (school_id, reference): replaying a webhook or a
   double-click can never record money twice.
"""
import enum
from datetime import date
from sqlalchemy import Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin, TenantMixin


class InvoiceStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PART_PAID = "part_paid"
    PAID = "paid"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    TRANSFER = "transfer"
    POS = "pos"
    PAYSTACK = "paystack"
    FLUTTERWAVE = "flutterwave"


class FeeCategory(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """e.g. School Fees, Exam Fees, Sports, Transport, Hostel."""
    __tablename__ = "fee_categories"

    name: Mapped[str] = mapped_column(String(100))


class FeeStructure(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """What a given class pays for a given category in a given term."""
    __tablename__ = "fee_structures"
    __table_args__ = (
        UniqueConstraint("class_id", "term_id", "category_id",
                         name="uq_fee_structure"),
    )

    class_id: Mapped[str] = mapped_column(ForeignKey("school_classes.id"))
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"))
    category_id: Mapped[str] = mapped_column(ForeignKey("fee_categories.id"))
    amount: Mapped[float] = mapped_column(Float, default=0.0)


class Invoice(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One bill per student per term (sum of the class's fee structures)."""
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("student_id", "term_id", name="uq_invoice_student_term"),
        UniqueConstraint("school_id", "invoice_number", name="uq_invoice_number"),
    )

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"))
    invoice_number: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    discount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[InvoiceStatus] = mapped_column(String(12), default=InvoiceStatus.UNPAID)
    due_date: Mapped[date | None] = mapped_column(Date)


class InvoiceItem(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """One line of an invoice: "Tuition — 30,000".

    The category NAME is copied here, not just referenced, and the amount is
    frozen at generation time. A school that renames "PTA Levy" or deletes a
    category next session must not silently rewrite what a parent was billed
    and paid last term — a receipt is evidence, and evidence does not change.
    """
    __tablename__ = "invoice_items"

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("fee_categories.id"))
    category_name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float, default=0.0)


class Payment(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A received payment against an invoice. reference is the idempotency key."""
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("school_id", "reference", name="uq_payment_reference"),
    )

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"))
    method: Mapped[PaymentMethod] = mapped_column(String(15))
    reference: Mapped[str] = mapped_column(String(80))
    amount: Mapped[float] = mapped_column(Float)
    paid_at: Mapped[date | None] = mapped_column(Date)
    received_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
