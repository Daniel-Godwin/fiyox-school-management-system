"""Principal role — a distinct oversight account, separate from the Admin.

The Principal approves results and monitors fees/analytics, but cannot run
setup, enter scores, record payments, or manage accounts. The platform owner
creates Principal accounts.
"""
from tests.conftest import headers


async def _make_principal(client, ids, email="principal@gss.ng"):
    oh = await headers(client, "owner@fiyox.ng", "owner123")
    r = await client.post(f"/api/schools/{ids['school_id']}/accounts", headers=oh, json={
        "role": "principal", "email": email,
        "first_name": "Mrs", "last_name": "Head"})
    assert r.status_code == 201, r.text
    return await headers(client, email, r.json()["password"])


async def test_super_admin_creates_principal_with_one_time_credentials(ctx):
    client, ids = ctx
    oh = await headers(client, "owner@fiyox.ng", "owner123")
    r = await client.post(f"/api/schools/{ids['school_id']}/accounts", headers=oh, json={
        "role": "principal", "email": "p@gss.ng", "first_name": "P", "last_name": "H"})
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "principal" and body["password"]
    # the principal signs in with those credentials
    ph = await headers(client, "p@gss.ng", body["password"])
    assert (await client.get("/api/results/approval-queue", headers=ph)).status_code == 200
    # the console now counts a principal for the school
    estate = (await client.get("/api/schools", headers=oh)).json()
    school = next(s for s in estate if s["id"] == ids["school_id"])
    assert school["principals"] == 1


async def test_admin_cannot_create_a_principal(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    r = await client.post("/api/users", headers=ah, json={
        "role": "principal", "email": "x@gss.ng", "first_name": "X",
        "last_name": "Y", "password": "secret12"})
    assert r.status_code == 403


async def test_principal_sees_oversight_but_cannot_operate(ctx):
    client, ids = ctx
    ph = await _make_principal(client, ids)

    # oversight reads — allowed
    assert (await client.get("/api/students", headers=ph)).status_code == 200
    assert (await client.get("/api/fees/summary", headers=ph,
            params={"term_id": ids["term_id"]})).status_code == 200
    assert (await client.get("/api/fees/debtors", headers=ph)).status_code == 200
    assert (await client.get("/api/schools/me", headers=ph)).status_code == 200
    assert (await client.get("/api/export/school.xlsx", headers=ph)).status_code == 200

    # operational writes — forbidden
    assert (await client.post("/api/academics/subjects", headers=ph,
            json={"name": "Z"})).status_code == 403
    assert (await client.post("/api/scores", headers=ph, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"], "rows": []})).status_code == 403
    assert (await client.post("/api/fees/payments", headers=ph, json={
            "invoice_id": "x", "amount": 1, "method": "cash",
            "reference": "r"})).status_code == 403
    assert (await client.post("/api/users", headers=ph, json={
            "role": "teacher", "email": "t@gss.ng", "first_name": "T",
            "last_name": "T", "password": "secret12"})).status_code == 403


async def test_principal_approves_results_the_admin_submitted(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    ph = await _make_principal(client, ids)

    # the school routes results through the approval gate
    async with ids["session_factory"]() as db:
        from app.models.school import School
        s = await db.get(School, ids["school_id"])
        s.result_approval_required = True
        await db.commit()

    comp = ids["component_ids"]
    for sid in ids["student_ids"]:
        await client.post("/api/scores", headers=ah, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"], "rows": [{"student_id": sid, "scores": {comp[3]: 55}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    await client.post("/api/results/submit", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # the principal sees the class in the approval queue
    q = (await client.get("/api/results/approval-queue", headers=ph)).json()
    assert q["count"] == 1 and q["arms"][0]["count"] == len(ids["student_ids"])

    # the principal approves and publishes
    assert (await client.post("/api/results/approve", headers=ph, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()["approved"] \
        == len(ids["student_ids"])
    assert (await client.post("/api/results/publish", headers=ph, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()["published"] \
        == len(ids["student_ids"])

    # queue is now clear
    assert (await client.get("/api/results/approval-queue", headers=ph)).json()["count"] == 0
