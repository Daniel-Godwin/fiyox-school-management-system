"""Academic setup — a new school can configure itself end to end."""
from tests.conftest import headers


async def test_quick_setup_makes_a_school_usable(ctx):
    client, ids = ctx
    # onboard a fresh school (the seeded one already has structure)
    sh = await headers(client, "owner@fiyox.ng", "owner123")
    await client.post("/api/schools", headers=sh, json={
        "name": "New Hope College", "slug": "new-hope",
        "admin_email": "admin@newhope.ng", "admin_password": "pass1234",
        "admin_first_name": "Bola", "admin_last_name": "Ade"})
    ah = await headers(client, "admin@newhope.ng", "pass1234")

    # brand new school: nothing to select yet
    assert (await client.get("/api/academics/terms", headers=ah)).json() == []
    assert (await client.get("/api/academics/arms", headers=ah)).json() == []

    res = (await client.post("/api/academics/quick-setup", headers=ah, json={
        "session_name": "2025/2026", "term": "first",
        "classes": ["JSS1", "JSS2"], "arms": ["A", "B"],
        "subjects": ["Mathematics", "English Language"]})).json()
    assert res["classes"] == ["JSS1", "JSS2"]
    assert len(res["components"]) == 4

    # the selectors every screen needs are now populated
    terms = (await client.get("/api/academics/terms", headers=ah)).json()
    assert len(terms) == 1 and terms[0]["is_current"] is True
    arms = (await client.get("/api/academics/arms", headers=ah)).json()
    assert {a["label"] for a in arms} == {"JSS1 A", "JSS1 B", "JSS2 A", "JSS2 B"}
    subjects = (await client.get("/api/academics/subjects", headers=ah)).json()
    assert len(subjects) == 2
    comps = (await client.get("/api/assessment-components", headers=ah)).json()
    assert sum(c["max_score"] for c in comps) == 100

    # a student can now be admitted straight into a real arm
    arm_id = next(a["id"] for a in arms if a["label"] == "JSS1 A")
    r = await client.post("/api/students", headers=ah, json={
        "admission_number": "NH/26/001", "first_name": "Zainab",
        "last_name": "Yusuf", "gender": "female", "arm_id": arm_id})
    assert r.status_code == 201

    # re-running quick-setup on a configured school is refused
    again = await client.post("/api/academics/quick-setup", headers=ah, json={})
    assert again.status_code == 409


async def test_individual_creates_and_rbac(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    s = (await client.post("/api/academics/sessions", headers=ah,
         json={"name": "2026/2027", "is_current": True})).json()
    t = (await client.post("/api/academics/terms", headers=ah,
         json={"session_id": s["id"], "name": "second", "is_current": True})).json()
    assert t["name"] == "second"

    # is_current moved to the new term (only one current at a time)
    terms = (await client.get("/api/academics/terms", headers=ah)).json()
    assert sum(1 for x in terms if x["is_current"]) == 1

    c = (await client.post("/api/academics/classes", headers=ah,
         json={"name": "SS1", "category": "senior"})).json()
    a = (await client.post("/api/academics/arms", headers=ah,
         json={"class_id": c["id"], "name": "Gold"})).json()
    assert a["label"] == "SS1 Gold"

    subj = (await client.post("/api/academics/subjects", headers=ah,
            json={"name": "Further Maths", "code": "FMT"})).json()
    assert subj["code"] == "FMT"

    # teachers cannot change the academic structure
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.post("/api/academics/classes", headers=th,
            json={"name": "X", "category": "junior"})).status_code == 403
    assert (await client.post("/api/academics/quick-setup", headers=th,
            json={})).status_code == 403
