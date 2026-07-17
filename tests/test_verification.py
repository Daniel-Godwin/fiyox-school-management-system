"""Contact verification — the code flow, its limits, and its honesty.

Everything runs with the mock SMS provider (no Termii key), which is exactly
how a school runs before going live: codes are generated and logged, the flow
works end to end, nothing is delivered. The tests reach into the database for
the code the way a phone would receive it.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.verification import VerificationCode
from tests.conftest import headers


async def _parent_with_phone(client, ids, phone="08031234567"):
    from app.core.security import hash_password
    from app.models.school import Role, User
    async with ids["session_factory"]() as db:
        p = User(school_id=ids["school_id"], email="vparent@x.ng",
                 hashed_password=hash_password("par12345"), role=Role.PARENT,
                 first_name="Veri", last_name="Parent", phone=phone)
        db.add(p)
        await db.commit()
        return p.id


async def _latest_code_plain(ids, user_id):
    """The tests' stand-in for reading the SMS off a phone: we cannot un-hash,
    so we brute-force the 6-digit space against the stored hash (fast, and it
    doubles as proof the hash really is of a 6-digit code)."""
    async with ids["session_factory"]() as db:
        vc = (await db.execute(select(VerificationCode).where(
            VerificationCode.user_id == user_id).order_by(
                VerificationCode.created_at.desc()))).scalars().first()
        assert vc is not None
        for n in range(1_000_000):
            code = f"{n:06d}"
            if hashlib.sha256(code.encode()).hexdigest() == vc.code_hash:
                return code, vc
        raise AssertionError("stored hash matches no 6-digit code")


async def test_phone_verification_end_to_end(ctx):
    client, ids = ctx
    uid = await _parent_with_phone(client, ids)
    ph = await headers(client, "vparent@x.ng", "par12345")

    r = (await client.post("/api/verify/request", headers=ph,
                           json={"channel": "phone"})).json()
    assert r["sent"] is True
    assert "preview mode" in r["note"]        # honest: mock provider, not delivered

    code, _ = await _latest_code_plain(ids, uid)
    ok = (await client.post("/api/verify/confirm", headers=ph,
                            json={"channel": "phone", "code": code})).json()
    assert ok["verified"] is True

    # the badge is now visible to the admin
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    users = (await client.get("/api/users?role=parent", headers=ah)).json()
    me = next(u for u in users if u["email"] == "vparent@x.ng")
    assert me["phone_verified"] is True

    # asking again is a friendly no-op, not another SMS
    again = (await client.post("/api/verify/request", headers=ph,
                               json={"channel": "phone"})).json()
    assert again["sent"] is False and "already verified" in again["note"]


async def test_wrong_codes_are_limited_then_locked(ctx):
    client, ids = ctx
    uid = await _parent_with_phone(client, ids)
    ph = await headers(client, "vparent@x.ng", "par12345")
    await client.post("/api/verify/request", headers=ph, json={"channel": "phone"})

    for i in range(5):
        r = await client.post("/api/verify/confirm", headers=ph,
                              json={"channel": "phone", "code": "000001"})
        # (one-in-a-million flake accepted: the real code could be 000001)
        assert r.status_code == 400

    locked = await client.post("/api/verify/confirm", headers=ph,
                               json={"channel": "phone", "code": "000001"})
    assert locked.status_code == 429

    # even the RIGHT code no longer works on a locked code
    code, _ = await _latest_code_plain(ids, uid)
    still = await client.post("/api/verify/confirm", headers=ph,
                              json={"channel": "phone", "code": code})
    assert still.status_code == 429


async def test_requesting_codes_is_rate_limited(ctx):
    client, ids = ctx
    await _parent_with_phone(client, ids)
    ph = await headers(client, "vparent@x.ng", "par12345")

    for _ in range(3):
        assert (await client.post("/api/verify/request", headers=ph,
                json={"channel": "phone"})).status_code == 200
    fourth = await client.post("/api/verify/request", headers=ph,
                               json={"channel": "phone"})
    assert fourth.status_code == 429   # no SMS bombardment, no drained credit


async def test_expired_codes_are_refused(ctx):
    client, ids = ctx
    uid = await _parent_with_phone(client, ids)
    ph = await headers(client, "vparent@x.ng", "par12345")
    await client.post("/api/verify/request", headers=ph, json={"channel": "phone"})

    code, vc = await _latest_code_plain(ids, uid)
    async with ids["session_factory"]() as db:
        row = await db.get(VerificationCode, vc.id)
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

    r = await client.post("/api/verify/confirm", headers=ph,
                          json={"channel": "phone", "code": code})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"]


async def test_email_verification_is_honest_about_no_mail_provider(ctx):
    client, ids = ctx
    await _parent_with_phone(client, ids)
    ph = await headers(client, "vparent@x.ng", "par12345")
    r = (await client.post("/api/verify/request", headers=ph,
                           json={"channel": "email"})).json()
    assert r["sent"] is False
    assert "not configured" in r["note"]     # never pretend a mail was sent


async def test_user_without_phone_gets_a_clear_message(ctx):
    client, ids = ctx
    from app.core.security import hash_password
    from app.models.school import Role, User
    async with ids["session_factory"]() as db:
        db.add(User(school_id=ids["school_id"], email="nophone@x.ng",
                    hashed_password=hash_password("par12345"), role=Role.PARENT,
                    first_name="No", last_name="Phone"))
        await db.commit()
    ph = await headers(client, "nophone@x.ng", "par12345")
    r = await client.post("/api/verify/request", headers=ph,
                          json={"channel": "phone"})
    assert r.status_code == 400
    assert "No phone" in r.json()["detail"]
