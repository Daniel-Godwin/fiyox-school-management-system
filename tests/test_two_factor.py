"""Opt-in two-factor sign-in (email code)."""
import re

from sqlalchemy import select

from tests.conftest import headers


async def _latest_code(ids, user_id: str) -> str:
    from app.models.notifications import MessageLog
    async with ids["session_factory"]() as db:
        log = (await db.execute(select(MessageLog).where(
            MessageLog.recipient_user_id == user_id).order_by(
            MessageLog.created_at.desc()))).scalars().first()
    m = re.search(r"\b(\d{6})\b", log.body)
    assert m, f"no code in {log.body!r}"
    return m.group(1)


async def _make_verified_teacher(client, ids, email):
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    res = (await client.post("/api/users", headers=ah, json={
        "email": email, "role": "teacher", "first_name": "T", "last_name": "T"})).json()
    uid, temp = res["user"]["id"], res["temporary_password"]
    # mark the email verified so 2FA can be enabled
    from app.models.school import User
    async with ids["session_factory"]() as db:
        u = await db.get(User, uid)
        u.email_verified = True
        await db.commit()
    return uid, temp


async def test_enable_requires_a_verified_email(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    res = (await client.post("/api/users", headers=ah, json={
        "email": "no.verify@gss-ikeja.ng", "role": "teacher",
        "first_name": "N", "last_name": "V"})).json()
    th = await headers(client, "no.verify@gss-ikeja.ng", res["temporary_password"])
    assert (await client.post("/api/auth/2fa/enable", headers=th)).status_code == 400


async def test_two_factor_login_flow(ctx):
    client, ids = ctx
    uid, temp = await _make_verified_teacher(client, ids, "tfa@gss-ikeja.ng")
    th = await headers(client, "tfa@gss-ikeja.ng", temp)
    assert (await client.post("/api/auth/2fa/enable", headers=th)).status_code == 200

    # password step no longer returns a token — it asks for the code
    r = await client.post("/api/auth/login", data={
        "username": "tfa@gss-ikeja.ng", "password": temp})
    assert r.status_code == 200
    body = r.json()
    assert body.get("two_factor_required") is True
    assert "access_token" not in body
    challenge = body["challenge"]

    # the emailed code completes the sign-in
    code = await _latest_code(ids, uid)
    vr = await client.post("/api/auth/login/2fa",
                           json={"challenge": challenge, "code": code})
    assert vr.status_code == 200 and "access_token" in vr.json()


async def test_two_factor_rejects_a_wrong_code(ctx):
    client, ids = ctx
    uid, temp = await _make_verified_teacher(client, ids, "tfa.wrong@gss-ikeja.ng")
    th = await headers(client, "tfa.wrong@gss-ikeja.ng", temp)
    await client.post("/api/auth/2fa/enable", headers=th)
    body = (await client.post("/api/auth/login", data={
        "username": "tfa.wrong@gss-ikeja.ng", "password": temp})).json()
    code = await _latest_code(ids, uid)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    vr = await client.post("/api/auth/login/2fa",
                           json={"challenge": body["challenge"], "code": wrong})
    assert vr.status_code == 400


async def test_login_without_2fa_still_returns_a_token(ctx):
    client, ids = ctx
    r = await client.post("/api/auth/login", data={
        "username": "admin@gss-ikeja.ng", "password": "admin123"})
    assert r.status_code == 200 and "access_token" in r.json()
