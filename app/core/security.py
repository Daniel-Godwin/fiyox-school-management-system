"""Auth primitives: password hashing + JWT encode/decode."""
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from app.core.config import settings


def hash_password(raw: str) -> str:
    # bcrypt caps input at 72 bytes; truncate defensively.
    return bcrypt.hashpw(raw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode()[:72], hashed.encode())


# A short list of obviously-guessable passwords to refuse outright. This is a
# floor, not a full policy — length plus "not on this list" already rules out
# the passwords attackers try first.
_COMMON_WEAK = {
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwerty123", "qwertyuiop", "11111111", "00000000",
    "abc12345", "iloveyou", "admin123", "letmein1", "fiyox2026", "changeme",
}


def weak_password_reason(raw: str) -> str | None:
    """Return a human reason if the password is too weak, else None.

    Length (>= 8) is enforced by the schema; this adds cheap extra guards that a
    length check alone misses: all-identical characters and common passwords.
    """
    pw = raw.strip()
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(set(pw)) == 1:
        return "Password is too simple — use a mix of characters."
    if pw.lower() in _COMMON_WEAK:
        return "That password is too common — choose something harder to guess."
    return None


def create_access_token(subject: str, school_id: str | None, role: str,
                        impersonator: str | None = None) -> str:
    """Encode user id, tenant (school) and role directly into the token.

    school_id in the token is what scopes every request to a single tenant.
    When the owner opens a school as its admin, `impersonator` records who is
    acting — carried in the token for traceability.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "school_id": school_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if impersonator:
        payload["imp"] = impersonator
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def create_2fa_challenge(user_id: str) -> str:
    """A short-lived token issued after a correct password when 2FA is on. It is
    NOT a usable access token — it only lets the holder submit the emailed code."""
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "purpose": "2fa", "iat": now,
               "exp": now + timedelta(minutes=10)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_2fa_challenge(token: str) -> str | None:
    """Return the user id from a 2FA challenge token, or None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except Exception:
        return None
    if payload.get("purpose") != "2fa":
        return None
    return payload.get("sub")
