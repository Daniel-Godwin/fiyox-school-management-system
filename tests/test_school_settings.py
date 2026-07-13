"""School settings + the withhold-results-on-debt gate, end to end."""
from tests.conftest import headers


async def _setup_fees_and_results(client, ids, amount=20000):
    """Bill the arm, compute + publish results, link a parent to student 0."""
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # fees
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": amount})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # scores -> compute -> publish
    comp = ids["component_ids"]
    for sid, mark in zip(ids["student_ids"], [60, 50, 40]):
        await client.post("/api/scores", headers=ah, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: mark}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    await client.post("/api/results/publish", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # parent of student 0
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        p = User(school_id=ids["school_id"], email="mum@x.ng",
                 hashed_password=hash_password("mumpass1"),
                 role=Role.PARENT, first_name="M", last_name="Um")
        db.add(p)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=p.id,
                        student_id=ids["student_ids"][0], relationship="Mother"))
        await db.commit()
    return ah


async def test_settings_default_off_then_gate_blocks_and_clears(ctx):
    client, ids = ctx
    ah = await _setup_fees_and_results(client, ids)
    ph = await headers(client, "mum@x.ng", "mumpass1")
    sid = ids["student_ids"][0]

    # default: withholding is OFF — a debtor parent still sees the result
    settings = (await client.get("/api/schools/me", headers=ah)).json()
    assert settings["withhold_results_on_debt"] is False
    r = await client.get(f"/api/report/{sid}", headers=ph,
                         params={"term_id": ids["term_id"]})
    assert r.status_code == 200

    # admin turns the policy ON
    res = (await client.patch("/api/schools/me", headers=ah,
           json={"withhold_results_on_debt": True})).json()
    assert res["withhold_results_on_debt"] is True
    assert "withhold_results_on_debt" in res["updated"]

    # now the debtor parent is blocked with 402 (both JSON and PDF)
    blocked = await client.get(f"/api/report/{sid}", headers=ph,
                               params={"term_id": ids["term_id"]})
    assert blocked.status_code == 402
    assert "withheld" in blocked.json()["detail"].lower()
    blocked_pdf = await client.get(f"/api/report/{sid}/pdf", headers=ph,
                                   params={"term_id": ids["term_id"]})
    assert blocked_pdf.status_code == 402

    # staff are never blocked by the gate
    staff = await client.get(f"/api/report/{sid}", headers=ah,
                             params={"term_id": ids["term_id"]})
    assert staff.status_code == 200

    # bursar records full payment -> the gate clears automatically
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"student_id": sid})).json()[0]
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv["id"], "method": "transfer",
        "reference": "SETTLED-1", "amount": 20000})

    cleared = await client.get(f"/api/report/{sid}", headers=ph,
                               params={"term_id": ids["term_id"]})
    assert cleared.status_code == 200
    assert cleared.json()["summary"]["average"] > 0


async def test_part_payment_still_withholds(ctx):
    client, ids = ctx
    ah = await _setup_fees_and_results(client, ids)
    ph = await headers(client, "mum@x.ng", "mumpass1")
    sid = ids["student_ids"][0]
    await client.patch("/api/schools/me", headers=ah,
                       json={"withhold_results_on_debt": True})

    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"student_id": sid})).json()[0]
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv["id"], "method": "cash",
        "reference": "PART-1", "amount": 15000})   # 5,000 still owing

    still = await client.get(f"/api/report/{sid}", headers=ph,
                             params={"term_id": ids["term_id"]})
    assert still.status_code == 402   # a balance is a balance


async def test_only_admin_changes_settings(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.patch("/api/schools/me", headers=th,
            json={"withhold_results_on_debt": True})).status_code == 403
