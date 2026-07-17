"""Contact verification — proving a phone number or email actually reaches its owner.

Design notes, because the details are the security:

* Codes are 6 digits, generated with `secrets` (not `random`).
* Only a **hash** of the code is stored. A database leak must not hand an
  attacker a table of live verification codes.
* Codes expire after 10 minutes and allow at most 5 wrong attempts, after
  which the code is dead and a new one must be requested.
* Requesting is rate-limited (3 codes per contact per hour) so the endpoint
  cannot be used to bombard someone's phone with SMS — or drain the school's
  Termii credit.
* The same table serves email verification and, later, OTP login: the flow is
  identical, only the `purpose` differs. That is deliberate — it means OTP
  login becomes a small toggle later, not a new subsystem.
"""
import enum

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class VerifyChannel(str, enum.Enum):
    PHONE = "phone"
    EMAIL = "email"


class VerifyPurpose(str, enum.Enum):
    VERIFY_CONTACT = "verify_contact"
    # reserved for the future login-by-code feature; same machinery
    LOGIN_OTP = "login_otp"


class VerificationCode(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "verification_codes"

    user_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[VerifyChannel] = mapped_column(String(10))
    purpose: Mapped[VerifyPurpose] = mapped_column(String(20),
                                                   default=VerifyPurpose.VERIFY_CONTACT)
    # the contact the code was sent to, frozen at request time — if the user's
    # phone number changes afterwards, this code must not verify the new one
    contact: Mapped[str] = mapped_column(String(200))
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
