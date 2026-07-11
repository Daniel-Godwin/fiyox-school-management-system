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


def create_access_token(subject: str, school_id: str | None, role: str) -> str:
    """Encode user id, tenant (school) and role directly into the token.

    school_id in the token is what scopes every request to a single tenant.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "school_id": school_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
