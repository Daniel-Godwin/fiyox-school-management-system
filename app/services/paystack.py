"""Paystack integration.

- initialize_payment: creates a Paystack transaction and returns the checkout
  URL. Requires PAYSTACK_SECRET_KEY; without it, callers get a clear
  'not configured' error instead of a crash.
- verify_signature: HMAC-SHA512 of the raw webhook body with the secret key,
  compared in constant time. Every webhook must pass this before it is trusted.

The webhook handler reuses record_payment(), so Paystack retries and duplicate
events can never record money twice (idempotent by reference).
"""
import hashlib
import hmac
import httpx
from app.core.config import settings

PAYSTACK_INIT_URL = "https://api.paystack.co/transaction/initialize"


def gateway_configured() -> bool:
    return bool(settings.PAYSTACK_SECRET_KEY)


async def initialize_payment(*, email: str, amount_kobo: int, reference: str,
                             metadata: dict) -> tuple[str | None, str | None]:
    """Returns (authorization_url, error)."""
    if not gateway_configured():
        return None, "Online payments are not configured yet"
    payload = {
        "email": email,
        "amount": amount_kobo,          # Paystack expects kobo
        "reference": reference,
        "metadata": metadata,
        "currency": "NGN",
    }
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(PAYSTACK_INIT_URL, json=payload, headers=headers)
            data = r.json()
            if r.status_code == 200 and data.get("status"):
                return data["data"]["authorization_url"], None
            return None, str(data.get("message") or f"HTTP {r.status_code}")
    except Exception as e:  # network failure must surface cleanly
        return None, str(e)[:200]


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not gateway_configured() or not signature:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(),
                        raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
