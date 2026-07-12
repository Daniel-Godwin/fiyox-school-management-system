"""User administration + self-service auth — the school staffs itself."""
from tests.conftest import headers, login


async def test_admin_creates_teacher_with_temp_password_and_they_log_in(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    res = (await client.post("/api/users", headers=ah, json={
        "email": "newteacher@gss-ikeja.ng", "role": "teacher",
        "first_name": "Ade", "last_name": "Ogun"})).json()
    temp = res["temporary_password"]
    assert temp and len(temp) >= 8
    assert res["user"]["role"] == "teacher" and res["user"]["is_active"] is True

    # the new teacher signs in with the temp password, then rotates it
    tok = await login(client, "newteacher@gss-ikeja.ng", temp)
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post("/api/auth/change-password", headers=h, json={
        "current_password": temp, "new_password": "myownpass1"})
    assert r.status_code == 200 and r.json()["changed"] is True

    # old password dead, new one works
    bad = await client.post("/api/auth/login",
                            data={"username": "newteacher@gss-ikeja.ng", "password": temp})
    assert bad.status_code == 401
    assert await login(client, "newteacher@gss-ikeja.ng", "myownpass1")

    # duplicate email rejected
    dup = await client.post("/api/users", headers=ah, json={
        "email": "newteacher@gss-ikeja.ng", "role": "teacher",
        "first_name": "X", "last_name": "Y"})
    assert dup.status_code == 409


async def test_parent_created_with_ward_sees_ward_in_portal(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    res = (await client.post("/api/users", headers=ah, json={
        "email": "mum@x.ng", "role": "parent", "first_name": "Ada",
        "last_name": "Eze", "password": "mumpass1",
        "ward_student_ids": [ids["student_ids"][0]]})).json()
    assert res["temporary_password"] is None  # explicit password given

    ph = await headers(client, "mum@x.ng", "mumpass1")
    wards = (await client.get("/api/my/wards", headers=ph)).json()
    assert len(wards) == 1 and wards[0]["name"] == "Chinedu Eze"

    # link a second ward afterwards
    uid = res["user"]["id"]
    r = await client.post(f"/api/users/{uid}/wards", headers=ah,
                          json={"student_id": ids["student_ids"][1],
                                "relationship": "Mother"})
    assert r.status_code == 201
    assert len((await client.get("/api/my/wards", headers=ph)).json()) == 2


async def test_deactivated_user_cannot_log_in(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    res = (await client.post("/api/users", headers=ah, json={
        "email": "leaver@x.ng", "role": "teacher", "first_name": "L",
        "last_name": "Eaver", "password": "leaver12"})).json()
    uid = res["user"]["id"]
    assert await login(client, "leaver@x.ng", "leaver12")

    r = await client.patch(f"/api/users/{uid}/status", headers=ah,
                           json={"is_active": False})
    assert r.json()["is_active"] is False

    blocked = await client.post("/api/auth/login",
                                data={"username": "leaver@x.ng", "password": "leaver12"})
    assert blocked.status_code == 403
    assert "deactivated" in blocked.json()["detail"]


async def test_rbac_and_self_protection(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.post("/api/users", headers=th, json={
        "email": "x@x.ng", "role": "teacher", "first_name": "a",
        "last_name": "b"})).status_code == 403

    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    me = (await client.get("/api/auth/me", headers=ah)).json()
    self_off = await client.patch(f"/api/users/{me['id']}/status", headers=ah,
                                  json={"is_active": False})
    assert self_off.status_code == 400  # cannot deactivate yourself

    # admin resets a user's password; temp works
    res = (await client.post("/api/users", headers=ah, json={
        "email": "forgot@x.ng", "role": "bursar", "first_name": "F",
        "last_name": "Orgot", "password": "original1"})).json()
    temp = (await client.post(f"/api/users/{res['user']['id']}/reset-password",
                              headers=ah)).json()["temporary_password"]
    assert await login(client, "forgot@x.ng", temp)
