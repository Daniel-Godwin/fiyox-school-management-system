"""Online admissions — public application, entrance test, review and admit."""
from datetime import datetime, timezone

from tests.conftest import headers

SLUG = "gss-ikeja"


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def _principal(client, ids):
    """Create a principal for the school (via the super admin) and return its headers."""
    oh = await headers(client, "owner@fiyox.ng", "owner123")
    r = await client.post(f"/api/schools/{ids['school_id']}/accounts", headers=oh, json={
        "role": "principal", "email": "principal@gss-ikeja.ng",
        "first_name": "Bola", "last_name": "Adeyemi"})
    assert r.status_code == 201, r.text
    return await headers(client, "principal@gss-ikeja.ng", r.json()["password"])


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

    # admin proposes admission (manual) — nothing the applicant sees changes yet
    pr = await client.post("/api/admissions/reconcile/manual", headers=ah,
                           json={"applicant_ids": [ap["id"]], "proposed_status": "admitted"})
    assert pr.status_code == 200 and pr.json()["proposed"] == 1
    mid = (await client.get(f"/api/admissions/applicants/{ap['id']}", headers=ah)).json()
    assert mid["status"] == "applied" and mid["proposed_status"] == "admitted"

    # the public status still shows nothing — the decision is not yet approved
    pub = (await client.post(f"/api/admissions/{SLUG}/status", json={
        "application_number": res["application_number"], "access_code": res["access_code"]})).json()
    assert pub["status"] == "applied"

    # the admin cannot approve — only the principal can
    denied = await client.post("/api/admissions/proposals/approve", headers=ah,
                               json={"applicant_ids": [ap["id"]]})
    assert denied.status_code == 403

    # enrolment is refused before approval
    early = await client.post(f"/api/admissions/applicants/{ap['id']}/admit", headers=ah,
                              json={"admission_number": "GSS/26/900"})
    assert early.status_code == 409

    # the principal approves -> status becomes admitted and reaches the applicant
    ph = await _principal(client, ids)
    appr = await client.post("/api/admissions/proposals/approve", headers=ph,
                             json={"applicant_ids": [ap["id"]]})
    assert appr.status_code == 200 and appr.json()["approved_total"] == 1
    detail = (await client.get(f"/api/admissions/applicants/{ap['id']}", headers=ah)).json()
    assert detail["status"] == "admitted" and detail["proposed_status"] is None and detail["decided_at"]

    # now the admin enrols -> creates a student
    adm = await client.post(f"/api/admissions/applicants/{ap['id']}/admit", headers=ah,
                            json={"admission_number": "GSS/26/900", "arm_id": ids["arm_id"]})
    assert adm.status_code == 200, adm.text
    students = (await client.get("/api/students", headers=ah)).json()
    assert any(s["admission_number"] == "GSS/26/900" for s in students)


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
    # the applicant is told it was submitted, but never shown the score
    assert sub["submitted"] is True
    assert "score" not in sub and "percent" not in sub

    # the status check also hides the score — only that the test was taken
    st = (await client.post(f"/api/admissions/{SLUG}/status", json=creds)).json()
    assert st["entrance_taken"] is True and "entrance_score" not in st

    # re-submitting is refused
    again = await client.post(f"/api/admissions/{SLUG}/test/submit", json={**creds, "answers": {}})
    assert again.status_code == 409

    # the score still shows to the admin, who decides the outcome
    lst = (await client.get("/api/admissions/applicants", headers=ah)).json()["applicants"]
    joy = next(a for a in lst if a["application_number"] == res["application_number"])
    assert joy["entrance_score"] == 3 and joy["entrance_percent"] == 100


async def test_auto_reconcile_by_score_then_principal_approves(ctx):
    client, ids = ctx
    ah = await _admin(client)
    cid = await _class_id(client)

    # a 3-mark entrance test
    t = (await client.post("/api/admissions/tests", headers=ah, json={
        "title": "Entrance", "duration_minutes": 15})).json()
    await client.post(f"/api/admissions/tests/{t['id']}/questions", headers=ah, json={
        "type": "single", "text": "2+2?", "marks": 2,
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}], "correct": "b"})
    await client.post(f"/api/admissions/tests/{t['id']}/questions", headers=ah, json={
        "type": "boolean", "text": "Water is wet.", "marks": 1, "correct": True})
    await client.patch(f"/api/admissions/tests/{t['id']}", headers=ah, json={"is_active": True})

    async def apply_and_score(first, right):
        res = await _apply(client, cid, first=first, last="Test")
        creds = {"application_number": res["application_number"], "access_code": res["access_code"]}
        start = (await client.post(f"/api/admissions/{SLUG}/test/start", json=creds)).json()
        qids = {q["text"]: q["id"] for q in start["questions"]}
        answers = {}
        if right >= 1: answers[qids["2+2?"]] = "b"      # 2 marks
        if right >= 2: answers[qids["Water is wet."]] = "true"  # +1 mark
        await client.post(f"/api/admissions/{SLUG}/test/submit", json={**creds, "answers": answers})
        return res["application_number"]

    top = await apply_and_score("Top", 2)      # 3/3 = 100%
    mid = await apply_and_score("Mid", 1)       # 2/3 = 67%
    low = await apply_and_score("Low", 0)       # 0/3 = 0%

    # auto-reconcile: pass mark 50, one seat in the class
    r = await client.post("/api/admissions/reconcile/auto", headers=ah,
                          json={"pass_mark": 50, "seats_per_class": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["proposed"]["admitted"] == 1       # Top takes the one seat
    assert body["proposed"]["shortlisted"] == 1    # Mid is above the mark but out of seats
    assert body["proposed"]["rejected"] == 1       # Low is below the mark

    def by_no(rows, no): return next(a for a in rows if a["application_number"] == no)
    lst = (await client.get("/api/admissions/applicants", headers=ah)).json()
    assert lst["pending"] == 3
    assert by_no(lst["applicants"], top)["proposed_status"] == "admitted"
    assert by_no(lst["applicants"], mid)["proposed_status"] == "shortlisted"
    assert by_no(lst["applicants"], low)["proposed_status"] == "rejected"
    # still nothing published to applicants
    assert by_no(lst["applicants"], top)["status"] == "applied"

    # principal approves everything at once
    ph = await _principal(client, ids)
    appr = await client.post("/api/admissions/proposals/approve", headers=ph, json={})
    assert appr.status_code == 200 and appr.json()["approved_total"] == 3
    lst2 = (await client.get("/api/admissions/applicants", headers=ah)).json()
    assert lst2["pending"] == 0
    assert by_no(lst2["applicants"], top)["status"] == "admitted"
    assert by_no(lst2["applicants"], mid)["status"] == "shortlisted"
    assert by_no(lst2["applicants"], low)["status"] == "rejected"


async def test_principal_only_approves_and_clear_returns(ctx):
    client, ids = ctx
    ah = await _admin(client)
    cid = await _class_id(client)
    res = await _apply(client, cid, first="Pat", last="Oke")
    ap = (await client.get("/api/admissions/applicants", headers=ah)).json()["applicants"][0]

    await client.post("/api/admissions/reconcile/manual", headers=ah,
                      json={"applicant_ids": [ap["id"]], "proposed_status": "shortlisted"})
    # returning a proposal clears it
    cl = await client.post("/api/admissions/proposals/clear", headers=ah,
                           json={"applicant_ids": [ap["id"]]})
    assert cl.status_code == 200 and cl.json()["cleared"] == 1
    mid = (await client.get(f"/api/admissions/applicants/{ap['id']}", headers=ah)).json()
    assert mid["proposed_status"] is None

    # a teacher can neither reconcile nor approve
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.post("/api/admissions/reconcile/auto", headers=th,
                              json={"pass_mark": 50})).status_code == 403
    assert (await client.post("/api/admissions/proposals/approve", headers=th,
                              json={})).status_code == 403


async def test_admission_number_auto_generated_from_pattern(ctx):
    client, ids = ctx
    ah = await _admin(client)
    ph = await _principal(client, ids)
    cid = await _class_id(client)

    # the school sets its admission-number format
    s = await client.patch("/api/schools/me", headers=ah,
                           json={"admission_prefix": "fad", "admission_pad": 3})
    assert s.status_code == 200
    yy = datetime.now(timezone.utc).strftime("%y")
    me = (await client.get("/api/schools/me", headers=ah)).json()
    assert me["admission_prefix"] == "FAD"        # normalised to upper-case
    assert me["admission_number_preview"] == f"FAD/{yy}/001"

    async def approved_applicant(first):
        res = await _apply(client, cid, first=first, last="Test")
        ap = next(a for a in (await client.get("/api/admissions/applicants", headers=ah)).json()["applicants"]
                  if a["application_number"] == res["application_number"])
        await client.post("/api/admissions/reconcile/manual", headers=ah,
                          json={"applicant_ids": [ap["id"]], "proposed_status": "admitted"})
        await client.post("/api/admissions/proposals/approve", headers=ph,
                          json={"applicant_ids": [ap["id"]]})
        return ap["id"]

    # enrol with no number -> generated, and the serial advances
    id1 = await approved_applicant("Ada")
    e1 = await client.post(f"/api/admissions/applicants/{id1}/admit", headers=ah, json={})
    assert e1.status_code == 200 and e1.json()["admission_number"] == f"FAD/{yy}/001"

    id2 = await approved_applicant("Bode")
    e2 = await client.post(f"/api/admissions/applicants/{id2}/admit", headers=ah, json={})
    assert e2.json()["admission_number"] == f"FAD/{yy}/002"

    # a custom number still overrides the automatic one
    id3 = await approved_applicant("Chidi")
    e3 = await client.post(f"/api/admissions/applicants/{id3}/admit", headers=ah,
                           json={"admission_number": "FAD/OLD/077"})
    assert e3.json()["admission_number"] == "FAD/OLD/077"


async def test_admission_number_defaults_to_initials(ctx):
    client, ids = ctx
    ah = await _admin(client)
    ph = await _principal(client, ids)
    cid = await _class_id(client)
    yy = datetime.now(timezone.utc).strftime("%y")
    # no prefix set -> falls back to the school-name initials ("GSS Ikeja" -> "GI")
    me = (await client.get("/api/schools/me", headers=ah)).json()
    assert me["admission_number_preview"] == f"GI/{yy}/001"

    res = await _apply(client, cid, first="Zara", last="Test")
    ap = next(a for a in (await client.get("/api/admissions/applicants", headers=ah)).json()["applicants"]
              if a["application_number"] == res["application_number"])
    await client.post("/api/admissions/reconcile/manual", headers=ah,
                      json={"applicant_ids": [ap["id"]], "proposed_status": "admitted"})
    await client.post("/api/admissions/proposals/approve", headers=ph,
                      json={"applicant_ids": [ap["id"]]})
    e = await client.post(f"/api/admissions/applicants/{ap['id']}/admit", headers=ah, json={})
    assert e.json()["admission_number"] == f"GI/{yy}/001"


async def test_review_is_staff_only(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/admissions/applicants", headers=th)).status_code == 403
    # activating a test needs questions
    ah = await _admin(client)
    t = (await client.post("/api/admissions/tests", headers=ah, json={"title": "Empty"})).json()
    r = await client.patch(f"/api/admissions/tests/{t['id']}", headers=ah, json={"is_active": True})
    assert r.status_code == 409
