"""Onboarding multiple pilot schools from the platform console.

The property that matters with several pilots running at once: each school is
a sealed tenant. School B's admin must see nothing of school A — not students,
not users, not results — and must not be able to create schools themselves.
"""
from tests.conftest import headers


async def _super(client, ids):
    from app.core.security import hash_password
    from app.models.school import Role, User
    async with ids["session_factory"]() as db:
        db.add(User(school_id=None, email="owner@fiyox.ng",
                    hashed_password=hash_password("owner123"),
                    role=Role.SUPER_ADMIN, first_name="Daniel", last_name="Godwin"))
        await db.commit()
    return await headers(client, "owner@fiyox.ng", "owner123")


async def test_super_admin_onboards_a_school_in_one_call(ctx):
    client, ids = ctx
    sh = await _super(client, ids)

    r = await client.post("/api/schools", headers=sh, json={
        "name": "Pilot College Yola", "slug": "pilot-college-yola",
        "state": "Adamawa", "admin_email": "admin@pilot-yola.ng",
        "admin_password": "start1234", "admin_first_name": "Grace",
        "admin_last_name": "Musa"})
    assert r.status_code == 201

    # the new admin can sign in immediately and finds an EMPTY school
    ah = await headers(client, "admin@pilot-yola.ng", "start1234")
    assert (await client.get("/api/students", headers=ah)).json() == []
    assert (await client.get("/api/academics/terms", headers=ah)).json() == []

    # the console lists both schools with their numbers
    estate = (await client.get("/api/schools", headers=sh)).json()
    names = {s["name"] for s in estate}
    assert "Pilot College Yola" in names
    yola = next(s for s in estate if s["slug"] == "pilot-college-yola")
    assert yola["students"] == 0 and yola["admins"] == 1 and yola["active_accounts"] == 1


async def test_duplicate_slug_is_refused(ctx):
    client, ids = ctx
    sh = await _super(client, ids)
    body = {"name": "A", "slug": "same-slug", "admin_email": "a@a.ng",
            "admin_password": "start1234", "admin_first_name": "A",
            "admin_last_name": "A"}
    assert (await client.post("/api/schools", headers=sh, json=body)).status_code == 201
    body["admin_email"] = "b@b.ng"
    assert (await client.post("/api/schools", headers=sh, json=body)).status_code == 409


async def test_pilot_schools_are_sealed_from_each_other(ctx):
    client, ids = ctx
    sh = await _super(client, ids)
    for n in ("one", "two"):
        await client.post("/api/schools", headers=sh, json={
            "name": f"School {n}", "slug": f"school-{n}",
            "admin_email": f"admin@{n}.ng", "admin_password": "start1234",
            "admin_first_name": "N", "admin_last_name": n.title()})

    one = await headers(client, "admin@one.ng", "start1234")
    two = await headers(client, "admin@two.ng", "start1234")

    # school one builds; school two must see none of it
    await client.post("/api/academics/quick-setup", headers=one, json={
        "session_name": "2026/2027", "term": "first",
        "classes": [{"name": "JSS1", "category": "junior", "level_order": 1,
                     "arms": ["A"]}],
        "subjects": [{"name": "Mathematics"}]})
    await client.post("/api/students", headers=one, json={
        "admission_number": "ONE/26/001", "first_name": "Only",
        "last_name": "InOne", "gender": "male"})

    assert (await client.get("/api/students", headers=two)).json() == []
    assert (await client.get("/api/academics/subjects", headers=two)).json() == []
    users_two = (await client.get("/api/users", headers=two)).json()
    assert all(u["email"].endswith("@two.ng") for u in users_two)


async def test_school_admins_cannot_touch_the_platform_console(ctx):
    client, ids = ctx
    await _super(client, ids)     # console exists
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    assert (await client.get("/api/schools", headers=ah)).status_code == 403
    assert (await client.post("/api/schools", headers=ah, json={
        "name": "Rogue", "slug": "rogue", "admin_email": "r@r.ng",
        "admin_password": "start1234", "admin_first_name": "R",
        "admin_last_name": "R"})).status_code == 403


async def test_offboarding_a_school_blocks_every_account_but_keeps_records(ctx):
    client, ids = ctx
    sh = await _super(client, ids)
    await client.post("/api/schools", headers=sh, json={
        "name": "Leaving College", "slug": "leaving-college",
        "admin_email": "admin@leaving.ng", "admin_password": "start1234",
        "admin_first_name": "L", "admin_last_name": "C"})

    # the school works, then decides not to continue after the pilot
    ah = await headers(client, "admin@leaving.ng", "start1234")
    await client.post("/api/students", headers=ah, json={
        "admission_number": "LV/26/001", "first_name": "Kept",
        "last_name": "Record", "gender": "male"})

    sid = next(s["id"] for s in (await client.get("/api/schools", headers=sh)).json()
               if s["slug"] == "leaving-college")
    r = (await client.delete(f"/api/schools/{sid}", headers=sh)).json()
    assert r["offboarded"] is True and r["accounts_blocked"] >= 1

    # every sign-in is now refused
    assert (await client.post("/api/auth/login", data={
        "username": "admin@leaving.ng", "password": "start1234"})).status_code in (401, 403)

    # gone from the console list; a second offboard is a clean 404
    assert "leaving-college" not in [s["slug"] for s in
        (await client.get("/api/schools", headers=sh)).json()]
    assert (await client.delete(f"/api/schools/{sid}", headers=sh)).status_code == 404


async def test_console_breaks_engagement_down_by_role(ctx):
    client, ids = ctx
    sh = await _super(client, ids)
    estate = (await client.get("/api/schools", headers=sh)).json()
    seeded = next(s for s in estate if s["slug"] == "gss-ikeja")
    # the test fixture school: 3 students, 1 admin, 1 teacher, 1 bursar
    assert seeded["students"] == 3
    assert seeded["admins"] == 1 and seeded["teachers"] == 1
    # the console reports each role count; the fixture seeds no bursar/parent
    assert "bursars" in seeded and "parents" in seeded
