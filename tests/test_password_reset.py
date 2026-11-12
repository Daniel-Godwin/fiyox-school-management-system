"""Self-service password reset and login lockout."""
import re

from sqlalchemy import select

from tests.conftest import headers, login


async def _code_from_log(ids, user_id: str) -> str:
    """Pull the 6-digit reset code out of the logged email body."""
    from app.models.notifications import MessageLog
    async with ids["session_factory"]() as db:
        log = (await db.execute(select(MessageLog).where(
            MessageLog.recipient_user_id == user_id).order_by(
            MessageLog.created_at.desc()))).scalars().first()
    m = re.search(r"\b(\d{6})\b", log.body)
    assert m, f"no code in message body: {log.body!r}"
    return m.group(1)


async def _make_teacher(client, email):
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    res = (await client.post("/api/users", headers=ah, json={
        "email": email, "role": "teacher",
        "first_name": "T", "last_name": "T"})).json()
    return res["user"]["id"], res["temporary_password"]


async def test_forgot_and_reset_password(ctx):
    client, ids = ctx
    uid, temp = await _make_teacher(client, "reset.me@gss-ikeja.ng")

    # request a reset code — always a generic success
    r = await client.post("/api/auth/forgot-password",
                          json={"email": "reset.me@gss-ikeja.ng"})
    assert r.status_code == 200 and r.json()["sent"] is True

    code = await _code_from_log(ids, uid)
    rr = await client.post("/api/auth/reset-password", json={
        "email": "reset.me@gss-ikeja.ng", "code": code, "new_password": "brandnew99"})
    assert rr.status_code == 200 and rr.json()["reset"] is True

    # the new password works; the temporary one no longer does
    assert await login(client, "reset.me@gss-ikeja.ng", "brandnew99")
    assert (await client.post("/api/auth/login", data={
        "username": "reset.me@gss-ikeja.ng", "password": temp})).status_code == 401


async def test_reset_rejects_a_wrong_code(ctx):
    client, ids = ctx
    uid, _ = await _make_teacher(client, "wrong.code@gss-ikeja.ng")
    await client.post("/api/auth/forgot-password",
                      json={"email": "wrong.code@gss-ikeja.ng"})
    code = await _code_from_log(ids, uid)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"  # guaranteed different
    rr = await client.post("/api/auth/reset-password", json={
        "email": "wrong.code@gss-ikeja.ng", "code": wrong, "new_password": "whatever99"})
    assert rr.status_code == 400


async def test_forgot_password_does_not_reveal_whether_email_exists(ctx):
    client, ids = ctx
    r = await client.post("/api/auth/forgot-password",
                          json={"email": "nobody@nowhere.ng"})
    assert r.status_code == 200 and r.json()["sent"] is True


async def test_reset_requires_a_strong_enough_password(ctx):
    client, ids = ctx
    uid, _ = await _make_teacher(client, "shortpw@gss-ikeja.ng")
    await client.post("/api/auth/forgot-password", json={"email": "shortpw@gss-ikeja.ng"})
    code = await _code_from_log(ids, uid)
    rr = await client.post("/api/auth/reset-password", json={
        "email": "shortpw@gss-ikeja.ng", "code": code, "new_password": "short"})
    assert rr.status_code == 422  # min_length on the schema


async def test_login_locks_out_after_repeated_failures(ctx):
    client, ids = ctx
    from app.api.routes.auth import LOCKOUT_THRESHOLD
    email = "admin@gss-ikeja.ng"

    for _ in range(LOCKOUT_THRESHOLD):
        assert (await client.post("/api/auth/login", data={
            "username": email, "password": "wrongpass"})).status_code == 401

    # now locked — even the correct password is refused
    assert (await client.post("/api/auth/login", data={
        "username": email, "password": "admin123"})).status_code == 429
