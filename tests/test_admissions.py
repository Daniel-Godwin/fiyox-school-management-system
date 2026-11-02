"""Online admissions — public application, entrance test, review and admit."""
from tests.conftest import headers

SLUG = "gss-ikeja"


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def _class_id(client):
    info = (await client.get(f"/api/admissions/{SLUG}/info")).json()
    return info["classes"][0]["id"]


async def _apply(client, class_id, first="Grace", last="Udo"):
    r = await client.post(f"/api/admissions/{SLUG}/apply", json={
        "first_name": first, "last_name": last, "gender": "female",
        "applying_class_id": class_id,
        "guardian_name": "Mr Udo", "guardian_phone": "+2348010000009",
        "guardian_email": "udo@example.com", "previous_school": "Bright Stars"})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------
async def test_public_info_lists_classes(ctx):
    client, ids = ctx
    r = await client.get(f"/api/admissions/{SLUG}/info")
    assert r.status_code == 200
    body = r.json()
    assert body["school"]["slug"] == SLUG
    assert any(c["name"] == "JSS1" for c in body["classes"])


async def test_public_apply_and_status(ctx):
    client, ids = ctx
    cid = await _class_id(client)
    res = await _apply(client, cid)
    assert res["application_number"].startswith("APP/")
    assert len(res["access_code"]) == 6
    assert res["entrance_test"] is None          # none set yet

    # the applicant can check their own status with number + code
    st = (await client.post(f"/api/admissions/{SLUG}/status", json={
        "application_number": res["application_number"],
        "access_code": res["access_code"]})).json()
    assert st["status"] == "applied" and st["applying_class"] == "JSS1"

    # a wrong code is rejected
    bad = await client.post(f"/api/admissions/{SLUG}/status", json={
        "application_number": res["application_number"], "access_code": "ZZZZZZ"})
    assert bad.status_code == 404


async def test_admin_review_and_admit(ctx):
    client, ids = ctx
    cid = await _class_id(client)
    res = await _apply(client, cid)
    ah = await _admin(client)

    lst = (await client.get("/api/admissions/applicants", headers=ah)).json()
    assert lst["counts"]["applied"] >= 1
    ap = next(a for a in lst["applicants"] if a["application_number"] == res["application_number"])

    # shortlist
    s = await client.patch(f"/api/admissions/applicants/{ap['id']}/status", headers=ah,
                           json={"status": "shortlisted", "note": "Strong"})
    assert s.status_code == 200 and s.json()["status"] == "shortlisted"

    # admit -> creates a student
    adm = await client.post(f"/api/admissions/applicants/{ap['id']}/admit", headers=ah,
                            json={"admission_number": "GSS/26/900", "arm_id": ids["arm_id"]})
    assert adm.status_code == 200, adm.text
    assert adm.json()["admission_number"] == "GSS/26/900"

    # the student now exists and the applicant reads as admitted
    students = (await client.get("/api/students", headers=ah)).json()
    assert any(s["admission_number"] == "GSS/26/900" for s in students)
    detail = (await client.get(f"/api/admissions/applicants/{ap['id']}", headers=ah)).json()
    assert detail["status"] == "admitted" and detail["admitted_student_id"]

    # a duplicate admission number is refused
    res2 = await _apply(client, cid, first="Sam", last="Bello")
    ap2 = (await client.get("/api/admissions/applicants", headers=ah)).json()["applicants"]
    ap2 = next(a for a in ap2 if a["application_number"] == res2["application_number"])
    dup = await client.post(f"/api/admissions/applicants/{ap2['id']}/admit", headers=ah,
                            json={"admission_number": "GSS/26/900"})
    assert dup.status_code == 409


async def test_entrance_test_flow(ctx):
    client, ids = ctx
    ah = await _admin(client)
    # admin creates a general entrance test + two questions, then activates it
    t = (await client.post("/api/admissions/tests", headers=ah, json={
        "title": "Entrance exam", "duration_minutes": 15})).json()
    tid = t["id"]
    await client.post(f"/api/admissions/tests/{tid}/questions", headers=ah, json={
        "type": "single", "text": "2+2?", "marks": 2,
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}], "correct": "b"})
    await client.post(f"/api/admissions/tests/{tid}/questions", headers=ah, json={
        "type": "boolean", "text": "Water is wet.", "marks": 1, "correct": True})
    act = await client.patch(f"/api/admissions/tests/{tid}", headers=ah, json={"is_active": True})
    assert act.status_code == 200 and act.json()["is_active"] and act.json()["total_marks"] == 3

    # applicant applies — now the entrance test is offered
    cid = await _class_id(client)
    res = await _apply(client, cid, first="Joy", last="Eze")
    assert res["entrance_test"]["title"] == "Entrance exam"
    creds = {"application_number": res["application_number"], "access_code": res["access_code"]}

    start = (await client.post(f"/api/admissions/{SLUG}/test/start", json=creds)).json()
    assert len(start["questions"]) == 2
    assert all("correct" not in q for q in start["questions"])    # key never leaks
    qids = {q["text"]: q["id"] for q in start["questions"]}

    sub = (await client.post(f"/api/admissions/{SLUG}/test/submit", json={
        **creds, "answers": {qids["2+2?"]: "b", qids["Water is wet."]: "true"}})).json()
    assert sub["score"] == 3 and sub["max_score"] == 3 and sub["percent"] == 100

    # re-submitting is refused
    again = await client.post(f"/api/admissions/{SLUG}/test/submit", json={**creds, "answers": {}})
    assert again.status_code == 409

    # the score shows to the admin
    lst = (await client.get("/api/admissions/applicants", headers=ah)).json()["applicants"]
    joy = next(a for a in lst if a["application_number"] == res["application_number"])
    assert joy["entrance_score"] == 3 and joy["entrance_percent"] == 100


async def test_review_is_staff_only(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/admissions/applicants", headers=th)).status_code == 403
    # activating a test needs questions
    ah = await _admin(client)
    t = (await client.post("/api/admissions/tests", headers=ah, json={"title": "Empty"})).json()
    r = await client.patch(f"/api/admissions/tests/{t['id']}", headers=ah, json={"is_active": True})
    assert r.status_code == 409
