"""Authentication."""
from tests.conftest import login, headers


async def test_login_success(ctx):
    client, _ = ctx
    token = await login(client, "admin@gss-ikeja.ng", "admin123")
    assert token


async def test_login_wrong_password(ctx):
    client, _ = ctx
    r = await client.post("/api/auth/login",
                          data={"username": "admin@gss-ikeja.ng", "password": "wrong"})
    assert r.status_code == 401


async def test_me_returns_current_user(ctx):
    client, _ = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    r = await client.get("/api/auth/me", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "admin@gss-ikeja.ng"
    assert body["role"] == "school_admin"


async def test_health(ctx):
    client, _ = ctx
    assert (await client.get("/api/health")).json() == {"status": "ok"}
