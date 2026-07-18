"""The online-payments switch and closing a pilot school.

Two safety properties for the pilot phase:
* Parents must not see a Pay online button unless the school has deliberately
  switched it on — pilots start with it OFF.
* When a school leaves, every account locks at once, but nothing is destroyed.
"""
from tests.conftest import headers


async def _fees_setup(client, ah, ids):
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 20000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})


async def _parent(client, ids, ward_index=0):
    from app.core.security import hash_password
    from app.models.school import Role, User
    from app.models.student import Guardian
    async with ids["session_factory"]() as db:
        p = User(school_id=ids["school_id"], email="pp@x.ng",
                 hashed_password=hash_password("par12345"), role=Role.PARENT,
                 first_name="P", last_name="P")
        db.add(p)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=p.id,
                        student_id=ids["student_ids"][ward_index]))
        await db.commit()
    return await headers(client, "pp@x.ng", "par12345")


async def test_online_payment_is_off_by_default_and_the_button_hidden(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _fees_setup(client, ah, ids)
    ph = await _parent(client, ids)

    fees = (await client.get("/api/my/fees", headers=ph,
            params={"term_id": ids["term_id"]})).json()
    assert fees and fees[0]["can_pay_online"] is False   # button never renders

    # and the API itself refuses even a hand-crafted attempt
    r = await client.post(f"/api/fees/invoices/{fees[0]['id']}/pay/init",
                          headers=ph)
    assert r.status_code == 400
    assert "not enabled" in r.json()["detail"]


async def test_the_school_can_switch_online_payment_on(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _fees_setup(client, ah, ids)

    r = (await client.patch("/api/schools/me", headers=ah,
         json={"online_payments_enabled": True})).json()
    assert r["online_payments_enabled"] is True

    ph = await _parent(client, ids)
    fees = (await client.get("/api/my/fees", headers=ph,
            params={"term_id": ids["term_id"]})).json()
    assert fees[0]["can_pay_online"] is True
    # (pay/init would now proceed to the gateway-configured check)


async def test_offboarding_a_school_locks_everyone_but_destroys_nothing(ctx):
    client, ids = ctx
    from app.core.security import hash_password
    from app.models.school import Role, User
    async with ids["session_factory"]() as db:
        db.add(User(school_id=None, email="owner@fiyox.ng",
                    hashed_password=hash_password("owner123"),
                    role=Role.SUPER_ADMIN, first_name="D", last_name="G"))
        await db.commit()
    sh = await headers(client, "owner@fiyox.ng", "owner123")

    # a pilot school with an admin
    await client.post("/api/schools", headers=sh, json={
        "name": "Leaving College", "slug": "leaving-college",
        "admin_email": "admin@leaving.ng", "admin_password": "start1234",
        "admin_first_name": "L", "admin_last_name": "C"})
    school_id = next(s["id"] for s in
                     (await client.get("/api/schools", headers=sh)).json()
                     if s["slug"] == "leaving-college")

    r = (await client.delete(f"/api/schools/{school_id}", headers=sh)).json()
    assert r["offboarded"] is True and r["accounts_blocked"] == 1

    # their admin can no longer sign in
    from httpx import AsyncClient
    login = await client.post("/api/auth/login", data={
        "username": "admin@leaving.ng", "password": "start1234"})
    assert login.status_code in (401, 403)   # blocked either way

    # the school is gone from the console list, and cannot be offboarded twice
    estate = (await client.get("/api/schools", headers=sh)).json()
    assert "leaving-college" not in {s["slug"] for s in estate}
    assert (await client.delete(f"/api/schools/{school_id}",
                                headers=sh)).status_code == 404

    # the untouched demo school is unaffected
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    assert (await client.get("/api/students", headers=ah)).status_code == 200


async def test_school_admins_cannot_offboard_schools(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    r = await client.delete(f"/api/schools/{ids['school_id']}", headers=ah)
    assert r.status_code == 403
