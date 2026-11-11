"""Globally-unique emails and unambiguous login.

One email = one account. Login must resolve to exactly one account that can
actually sign in, and an offboarded school's account must never shadow a live
account that happens to share the email.
"""
from tests.conftest import headers, login


async def _super(client, ids):
    # the platform owner is already seeded by the test fixture
    return await headers(client, "owner@fiyox.ng", "owner123")


async def test_email_is_unique_across_schools(ctx):
    client, ids = ctx
    sh = await _super(client, ids)

    # onboarding a school claims the admin email globally
    assert (await client.post("/api/schools", headers=sh, json={
        "name": "Alpha", "slug": "alpha", "admin_email": "dup@x.ng",
        "admin_password": "start1234", "admin_first_name": "A",
        "admin_last_name": "A"})).status_code == 201

    # a second school cannot reuse that email
    assert (await client.post("/api/schools", headers=sh, json={
        "name": "Beta", "slug": "beta", "admin_email": "dup@x.ng",
        "admin_password": "start1234", "admin_first_name": "B",
        "admin_last_name": "B"})).status_code == 409

    # nor can another school's admin add a staff member with that email
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    assert (await client.post("/api/users", headers=ah, json={
        "email": "DUP@x.ng", "role": "teacher", "first_name": "T",
        "last_name": "T"})).status_code == 409


async def test_offboarded_duplicate_does_not_shadow_live_account(ctx):
    """The exact bug: an email reused after offboarding resolves to the live
    account, never the retired one, and the email is freed for reuse."""
    client, ids = ctx
    sh = await _super(client, ids)

    await client.post("/api/schools", headers=sh, json={
        "name": "Old", "slug": "old-school", "admin_email": "shared@x.ng",
        "admin_password": "oldpass12", "admin_first_name": "Old",
        "admin_last_name": "Admin"})
    sid = next(s["id"] for s in (await client.get("/api/schools", headers=sh)).json()
               if s["slug"] == "old-school")

    # offboard the old school → its admin is retired and the email is freed
    await client.delete(f"/api/schools/{sid}", headers=sh)
    assert (await client.post("/api/auth/login", data={
        "username": "shared@x.ng", "password": "oldpass12"})).status_code in (401, 403)

    # the same email now stands up a brand-new, live school
    assert (await client.post("/api/schools", headers=sh, json={
        "name": "New", "slug": "new-school", "admin_email": "shared@x.ng",
        "admin_password": "newpass12", "admin_first_name": "New",
        "admin_last_name": "Admin"})).status_code == 201

    # login resolves to the NEW account; the retired one never shadows it
    assert await login(client, "shared@x.ng", "newpass12")
    assert (await client.post("/api/auth/login", data={
        "username": "shared@x.ng", "password": "oldpass12"})).status_code in (401, 403)


async def test_login_refuses_ambiguous_duplicate_accounts(ctx):
    """If legacy data somehow leaves two LIVE accounts on one email+password,
    login refuses to guess rather than silently picking one."""
    client, ids = ctx
    from app.core.security import hash_password
    from app.models.school import User, Role, School
    async with ids["session_factory"]() as db:
        for slug in ("amb-a", "amb-b"):
            s = School(name=slug.upper(), slug=slug)
            db.add(s)
            await db.flush()
            db.add(User(school_id=s.id, email="ambi@x.ng",
                        hashed_password=hash_password("samepass1"),
                        role=Role.SCHOOL_ADMIN, first_name="A", last_name="B"))
        await db.commit()

    assert (await client.post("/api/auth/login", data={
        "username": "ambi@x.ng", "password": "samepass1"})).status_code == 409
