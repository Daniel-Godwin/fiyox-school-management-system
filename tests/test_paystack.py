"""Paystack gateway — signature-gated webhook, idempotent recording, safe defaults."""
import hashlib
import hmac
import json
from app.core.config import settings
from tests.conftest import headers

TEST_KEY = "sk_test_fiyox_secret"


async def _billed_invoice(client, ids):
    """Create category+structure (10,000), generate invoices, return student 0's invoice."""
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 10000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"student_id": ids["student_ids"][0]})).json()[0]
    return ah, inv


def _signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    sig = hmac.new(TEST_KEY.encode(), raw, hashlib.sha512).hexdigest()
    return raw, sig


async def test_init_returns_503_when_gateway_not_configured(ctx):
    client, ids = ctx
    ah, inv = await _billed_invoice(client, ids)
    # force the unconfigured state — a developer's .env may set the key to ''
    # (falsy, still unconfigured) or even a real value; the test must not
    # depend on the ambient environment.
    saved = settings.PAYSTACK_SECRET_KEY
    settings.PAYSTACK_SECRET_KEY = None
    try:
        r = await client.post(f"/api/fees/invoices/{inv['id']}/pay/init", headers=ah)
        assert r.status_code == 503
        assert "bursary" in r.json()["detail"]
    finally:
        settings.PAYSTACK_SECRET_KEY = saved


async def test_webhook_verifies_signature_and_records_once(ctx):
    client, ids = ctx
    ah, inv = await _billed_invoice(client, ids)

    saved = settings.PAYSTACK_SECRET_KEY
    settings.PAYSTACK_SECRET_KEY = TEST_KEY
    try:
        event = {
            "event": "charge.success",
            "data": {
                "reference": "PSK-TEST-REF-1",
                "amount": 1000000,  # kobo -> NGN 10,000
                "metadata": {"invoice_id": inv["id"], "school_id": ids["school_id"]},
            },
        }
        raw, sig = _signed(event)

        # bad signature is rejected, nothing recorded
        bad = await client.post("/api/fees/paystack/webhook", content=raw,
                                headers={"x-paystack-signature": "0" * 128,
                                         "Content-Type": "application/json"})
        assert bad.status_code == 401

        # good signature records the payment and settles the invoice
        ok = await client.post("/api/fees/paystack/webhook", content=raw,
                               headers={"x-paystack-signature": sig,
                                        "Content-Type": "application/json"})
        assert ok.status_code == 200 and ok.json()["duplicate"] is False

        after = (await client.get("/api/fees/invoices", headers=ah,
                 params={"student_id": ids["student_ids"][0]})).json()[0]
        assert after["paid"] == 10000 and after["status"] == "paid"

        # Paystack retries: same event replayed -> counted once
        again = await client.post("/api/fees/paystack/webhook", content=raw,
                                  headers={"x-paystack-signature": sig,
                                           "Content-Type": "application/json"})
        assert again.status_code == 200 and again.json()["duplicate"] is True
        final = (await client.get("/api/fees/invoices", headers=ah,
                 params={"student_id": ids["student_ids"][0]})).json()[0]
        assert final["paid"] == 10000  # not 20000
    finally:
        settings.PAYSTACK_SECRET_KEY = saved


async def test_parent_cannot_init_for_another_ward(ctx):
    client, ids = ctx
    ah, inv = await _billed_invoice(client, ids)
    # parent linked to student 1 tries to pay student 0's invoice
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        p = User(school_id=ids["school_id"], email="p2@x.ng",
                 hashed_password=hash_password("parent123"),
                 role=Role.PARENT, first_name="P", last_name="Two")
        db.add(p)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=p.id,
                        student_id=ids["student_ids"][1], relationship="Father"))
        await db.commit()
    ph = await headers(client, "p2@x.ng", "parent123")
    r = await client.post(f"/api/fees/invoices/{inv['id']}/pay/init", headers=ph)
    assert r.status_code == 403
