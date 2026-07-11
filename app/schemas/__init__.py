"""Schema package — re-exports every domain schema so callers can do
`from app.schemas import X` regardless of which module it lives in.

Each domain owns its own file (auth, school, student, results). New modules
(fees, attendance, ...) add their own file here and extend this re-export.
"""
from app.schemas.auth import Token, LoginIn, UserOut
from app.schemas.school import SchoolCreate, SchoolOut
from app.schemas.student import StudentCreate, StudentOut
from app.schemas.results import (
    ComponentIn, ComponentOut, ScoreRow, BulkScoresIn, ComputeIn, TermResultUpdate,
)
from app.schemas.fees import (
    CategoryIn, CategoryOut, StructureIn, StructureOut,
    GenerateInvoicesIn, InvoiceOut, PaymentIn, PaymentOut,
)

__all__ = [
    "Token", "LoginIn", "UserOut",
    "SchoolCreate", "SchoolOut",
    "StudentCreate", "StudentOut",
    "ComponentIn", "ComponentOut", "ScoreRow", "BulkScoresIn",
    "ComputeIn", "TermResultUpdate",
    "CategoryIn", "CategoryOut", "StructureIn", "StructureOut",
    "GenerateInvoicesIn", "InvoiceOut", "PaymentIn", "PaymentOut",
]
