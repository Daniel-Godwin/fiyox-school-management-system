"""Owner 'open school as admin' support tool."""
from tests.conftest import headers


async def _super(client):
    # the platform owner is seeded by the fixture
    return await headers(client, "owner@fiyox.ng", "owner123")


async def _make_school(client, sh, slug, admin_email):
    await client.post("/api/schools", headers=sh, json={
        "name": slug.title(), "slug": slug, "admin_email": admin_email,
        "admin_password": "startpass1", "admin_first_name": "A", "admin_last_name": "B"})
    rows = (await client.get("/api/schools", headers=sh)).json()
    return next(s["id"] for s in rows if s["slug"] == slug)


async def test_owner_opens_school_as_admin(ctx):
    client, ids = ctx
    sh = await _super(client)
    sid = await _make_school(client, sh, "sunrise", "admin@sunrise.ng")

    r = await client.post(f"/api/schools/{sid}/impersonate", headers=sh)
    assert r.status_code == 200
    body = r.json()
    assert body["acting_as"]["school"] == "Sunrise"
    assert body["acting_as"]["email"] == "admin@sunrise.ng"
    assert "access_token" in body

    # the minted token acts as that school's admin
    ah = {"Authorization": f"Bearer {body['access_token']}"}
    me = (await client.get("/api/auth/me", headers=ah)).json()
    assert me["email"] == "admin@sunrise.ng"
    assert me["role"] == "school_admin"
    assert me["school_id"] == sid


async def test_impersonation_is_audited(ctx):
    client, ids = ctx
    sh = await _super(client)
    sid = await _make_school(client, sh, "audited", "admin@audited.ng")
    await client.post(f"/api/schools/{sid}/impersonate", headers=sh)

    from sqlalchemy import select
    from app.models.audit import AuditLog
    async with ids["session_factory"]() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.action == "impersonate"))).scalars().all()
    assert rows, "impersonation should be recorded in the audit log"


async def test_non_owner_cannot_impersonate(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    meb = (await client.get("/api/auth/me", headers=ah)).json()
    r = await client.post(f"/api/schools/{meb['school_id']}/impersonate", headers=ah)
    assert r.status_code == 403


async def test_impersonate_unknown_school_is_404(ctx):
    client, ids = ctx
    sh = await _super(client)
    r = await client.post(
        "/api/schools/00000000-0000-0000-0000-000000000000/impersonate", headers=sh)
    assert r.status_code == 404
