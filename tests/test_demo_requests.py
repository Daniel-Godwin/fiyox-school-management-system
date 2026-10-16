"""Public demo requests from the landing page, and the owner's view of them."""
from tests.conftest import headers


async def _super(client, ids):
    from app.core.security import hash_password
    from app.models.school import Role, User
    async with ids["session_factory"]() as db:
        db.add(User(school_id=None, email="owner@fiyox.ng",
                    hashed_password=hash_password("owner123"),
                    role=Role.SUPER_ADMIN, first_name="D", last_name="G"))
        await db.commit()
    return await headers(client, "owner@fiyox.ng", "owner123")


async def test_anyone_can_submit_a_demo_request(ctx):
    client, ids = ctx
    # no auth header at all — the landing page is public
    r = await client.post("/api/demo-requests", json={
        "school_name": "Hilltop Academy", "contact_name": "Mrs Bello",
        "email": "principal@hilltop.ng", "phone": "08030000000",
        "message": "We have about 300 students."})
    assert r.status_code == 201
    assert r.json()["received"] is True


async def test_bad_submissions_are_rejected(ctx):
    client, ids = ctx
    # missing required fields / bad email
    assert (await client.post("/api/demo-requests", json={
        "school_name": "X", "contact_name": "Y", "email": "not-an-email"})).status_code == 422


async def test_only_the_platform_owner_sees_requests(ctx):
    client, ids = ctx
    sh = await _super(client, ids)
    await client.post("/api/demo-requests", json={
        "school_name": "Hilltop Academy", "contact_name": "Mrs Bello",
        "email": "principal@hilltop.ng"})

    # a school admin cannot see the platform's demo requests
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    assert (await client.get("/api/demo-requests", headers=ah)).status_code == 403

    # the owner sees it, newest first, and the email is normalised
    rows = (await client.get("/api/demo-requests", headers=sh)).json()
    assert len(rows) == 1
    assert rows[0]["school_name"] == "Hilltop Academy"
    assert rows[0]["email"] == "principal@hilltop.ng"
    assert rows[0]["handled"] is False

    # the owner can mark it handled
    rid = rows[0]["id"]
    done = (await client.patch(f"/api/demo-requests/{rid}?handled=true", headers=sh)).json()
    assert done["handled"] is True
