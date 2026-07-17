"""User lifecycle: people leave schools, and mistakes must be correctable.

Offboarding closes the account and the person's *relationships* (a teacher's
sheets, a parent's ward links) while never rewriting history — the marks a
departed teacher entered keep their name on the audit trail forever.
"""
from tests.conftest import headers


async def _make(client, ah, role, email, wards=None):
    body = {"email": email, "role": role, "first_name": "Life",
            "last_name": "Cycle", "password": "pass1234"}
    if wards:
        body["ward_student_ids"] = wards
    r = await client.post("/api/users", headers=ah, json=body)
    return r.json()["user"]["id"]


async def test_offboarding_a_teacher_closes_access_and_frees_their_sheets(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    tid = await _make(client, ah, "teacher", "leaver@x.ng")

    # they own a sheet and have entered a mark
    await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": tid, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"], "allow_co_teacher": True})
    th = await headers(client, "leaver@x.ng", "pass1234")
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=th, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 7}}]})

    r = await client.delete(f"/api/users/{tid}", headers=ah)
    assert r.status_code == 200 and r.json()["offboarded"] is True

    # sign-in is dead
    dead = await client.post("/api/auth/login",
                             data={"username": "leaver@x.ng", "password": "pass1234"})
    assert dead.status_code == 401

    # their sheet is released (no owner), but the mark they entered survives
    asgs = (await client.get("/api/users/assignments", headers=ah)).json()
    assert not any(a["teacher_id"] == tid for a in asgs)
    grid = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    assert any(s["student_id"] == ids["student_ids"][0] and s["score"] == 7
               for s in grid)

    # gone from the user list
    users = (await client.get("/api/users", headers=ah)).json()
    assert tid not in [u["id"] for u in users]

    # and the email is free for a corrected or returning account
    again = await client.post("/api/users", headers=ah, json={
        "email": "leaver@x.ng", "role": "teacher",
        "first_name": "Back", "last_name": "Again", "password": "pass1234"})
    assert again.status_code == 201


async def test_offboarding_a_parent_removes_ward_links_but_not_students(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    pid = await _make(client, ah, "parent", "gone@x.ng",
                      wards=[ids["student_ids"][0], ids["student_ids"][1]])

    r = await client.delete(f"/api/users/{pid}", headers=ah)
    assert r.status_code == 200

    # the students themselves are untouched and still on the roll
    roll = (await client.get("/api/students", headers=ah)).json()
    assert {ids["student_ids"][0], ids["student_ids"][1]} <= {s["id"] for s in roll}


async def test_the_last_admin_cannot_be_offboarded_and_nobody_offboards_themselves(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    me = (await client.get("/api/auth/me", headers=ah)).json()

    # self-offboard refused
    self_r = await client.delete(f"/api/users/{me['id']}", headers=ah)
    assert self_r.status_code == 400
    assert "your own" in self_r.json()["detail"]

    # a second admin can offboard the first…
    second = await _make(client, ah, "school_admin", "admin2@x.ng")
    ah2 = await headers(client, "admin2@x.ng", "pass1234")
    ok = await client.delete(f"/api/users/{me['id']}", headers=ah2)
    assert ok.status_code == 200

    # …but now they are the last admin: every route to removing them is blocked
    # (self-offboard is refused, and no other admin exists to try) — the school
    # cannot lock itself out
    third_try = await client.delete(f"/api/users/{second}", headers=ah2)
    assert third_try.status_code == 400   # refused as self-offboard

    users = (await client.get("/api/users?role=school_admin", headers=ah2)).json()
    assert [u["id"] for u in users] == [second]   # one admin remains, active
    assert users[0]["is_active"] is True


async def test_editing_fixes_a_mistaken_account(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    uid = await _make(client, ah, "teacher", "misspelt@x.ng")

    r = await client.patch(f"/api/users/{uid}", headers=ah, json={
        "first_name": "Chiamaka", "last_name": "Nwosu",
        "email": "c.nwosu@x.ng", "phone": "08031112222"})
    assert r.status_code == 200
    assert set(r.json()["changed"]) == {"email", "first_name", "last_name", "phone"}

    # the corrected account signs in with the NEW email
    ok = await client.post("/api/auth/login",
                           data={"username": "c.nwosu@x.ng", "password": "pass1234"})
    assert ok.status_code == 200


async def test_removing_a_subject_keeps_history_but_ends_its_future(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # a subject with real marks in it
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[3]: 55}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    r = await client.delete(f"/api/academics/subjects/{ids['subject_id']}",
                            headers=ah)
    assert r.status_code == 200

    # gone from the pick lists
    subjects = (await client.get("/api/academics/subjects", headers=ah)).json()
    assert ids["subject_id"] not in [s["id"] for s in subjects]

    # but the computed result — what a parent already received — is intact
    report = (await client.get(f"/api/report/{ids['student_ids'][0]}", headers=ah,
              params={"term_id": ids["term_id"]})).json()
    assert any(row["total"] == 55 for row in report["subjects"])
