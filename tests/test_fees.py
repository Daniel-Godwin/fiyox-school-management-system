"""Fees & payments — lifecycle, derived balances, idempotency, debt gate."""
from sqlalchemy import select
from tests.conftest import headers


async def _setup_fees(client, h, ids, amounts=(30000, 5000)):
    """Create categories + structures for JSS1 in the seeded term. Returns total."""
    total = 0
    for name, amount in zip(("School Fees", "Exam Fees"), amounts):
        cat = (await client.post("/api/fees/categories", headers=h,
               json={"name": name})).json()
        # class_id: fetch from the seeded arm via DB
        from app.models.academics import ClassArm
        async with ids["session_factory"]() as db:
            arm = await db.get(ClassArm, ids["arm_id"])
            class_id = arm.class_id
        r = await client.post("/api/fees/structures", headers=h, json={
            "class_id": class_id, "term_id": ids["term_id"],
            "category_id": cat["id"], "amount": amount})
        assert r.status_code == 201
        total += amount
    return total


async def test_invoice_generation_per_student(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    total = await _setup_fees(client, h, ids)

    res = (await client.post("/api/fees/invoices/generate", headers=h,
           json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert res["created"] == 3                      # one per seeded student
    assert res["amount_per_student"] == total       # 35000

    # regenerating skips everyone already invoiced
    again = (await client.post("/api/fees/invoices/generate", headers=h,
             json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert again["created"] == 0
    assert again["skipped_already_invoiced"] == 3


async def test_payment_reduces_balance_and_updates_status(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _setup_fees(client, h, ids)  # total 35000
    await client.post("/api/fees/invoices/generate", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    invs = (await client.get("/api/fees/invoices", headers=h,
            params={"student_id": ids["student_ids"][0]})).json()
    inv = invs[0]
    assert inv["balance"] == 35000 and inv["status"] == "unpaid"

    # part payment
    r1 = (await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": inv["id"], "method": "transfer",
        "reference": "TRX-001", "amount": 20000})).json()
    assert r1["invoice"]["balance"] == 15000
    assert r1["invoice"]["status"] == "part_paid"

    # settle
    r2 = (await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": inv["id"], "method": "cash",
        "reference": "CASH-002", "amount": 15000})).json()
    assert r2["invoice"]["balance"] == 0
    assert r2["invoice"]["status"] == "paid"


async def test_duplicate_reference_is_idempotent(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _setup_fees(client, h, ids)
    await client.post("/api/fees/invoices/generate", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=h,
           params={"student_id": ids["student_ids"][0]})).json()[0]

    p1 = (await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": inv["id"], "method": "paystack",
        "reference": "PSK-REF-1", "amount": 10000})).json()
    # replay the same reference (double webhook / double click)
    p2 = (await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": inv["id"], "method": "paystack",
        "reference": "PSK-REF-1", "amount": 10000})).json()

    assert p1["duplicate"] is False
    assert p2["duplicate"] is True
    assert p2["payment_id"] == p1["payment_id"]
    # money counted once
    assert p2["invoice"]["paid"] == 10000


async def test_teacher_cannot_touch_fees(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    r = await client.post("/api/fees/categories", headers=h, json={"name": "X"})
    assert r.status_code == 403


async def test_debt_gate_blocks_parent_until_paid(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # turn the policy on + create a parent linked to student 0, directly in DB
    from app.models.school import School, User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        school = await db.get(School, ids["school_id"])
        school.withhold_results_on_debt = True
        parent = User(school_id=ids["school_id"], email="parent@x.ng",
                      hashed_password=hash_password("parent123"),
                      role=Role.PARENT, first_name="Mama", last_name="Chinedu")
        db.add(parent)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=parent.id,
                        student_id=ids["student_ids"][0], relationship="Mother"))
        await db.commit()

    # scores -> compute -> publish (so only the debt gate can block)
    comp = ids["component_ids"]
    for sid in ids["student_ids"]:
        await client.post("/api/scores", headers=h, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: 50}}]})
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    from app.models.results import TermResult
    async with ids["session_factory"]() as db:
        tr = (await db.execute(select(TermResult).where(
            TermResult.student_id == ids["student_ids"][0]))).scalars().first()
    await client.patch(f"/api/term-results/{tr.id}", headers=h,
                       json={"is_published": True})

    # bill the arm
    await _setup_fees(client, h, ids)
    await client.post("/api/fees/invoices/generate", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    ph = await headers(client, "parent@x.ng", "parent123")
    blocked = await client.get(f"/api/report/{ids['student_ids'][0]}",
                               headers=ph, params={"term_id": ids["term_id"]})
    assert blocked.status_code == 402  # withheld: outstanding fees

    # pay in full -> gate opens
    inv = (await client.get("/api/fees/invoices", headers=h,
           params={"student_id": ids["student_ids"][0]})).json()[0]
    await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": inv["id"], "method": "transfer",
        "reference": "SETTLE-1", "amount": inv["balance"]})

    opened = await client.get(f"/api/report/{ids['student_ids'][0]}",
                              headers=ph, params={"term_id": ids["term_id"]})
    assert opened.status_code == 200
    assert opened.json()["student"]["name"] == "Chinedu Eze"


async def test_end_of_day_reconciliation_names_every_naira(ctx):
    """Both the admin and the bursar can record payments — reconciliation makes
    the drawer count against a named, referenced list so cash cannot drift."""
    from datetime import date
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    today = str(date.today())

    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 20000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    invoices = (await client.get("/api/fees/invoices", headers=ah,
                params={"term_id": ids["term_id"]})).json()

    # the ADMIN records one cash payment; the BURSAR records two
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": invoices[0]["id"], "amount": 20000, "method": "cash",
        "reference": "TELLER-001", "paid_at": today})
    # the fixture seeds no bursar — create one for this test
    await client.post("/api/users", headers=ah, json={
        "email": "bursar@gss-ikeja.ng", "role": "bursar",
        "first_name": "Chika", "last_name": "Nwosu", "password": "bursar123"})
    bh = await headers(client, "bursar@gss-ikeja.ng", "bursar123")
    await client.post("/api/fees/payments", headers=bh, json={
        "invoice_id": invoices[1]["id"], "amount": 10000, "method": "cash",
        "reference": "TELLER-002", "paid_at": today})
    await client.post("/api/fees/payments", headers=bh, json={
        "invoice_id": invoices[2]["id"], "amount": 20000, "method": "transfer",
        "reference": "TRF-903311", "paid_at": today})

    recon = (await client.get("/api/fees/reconciliation", headers=bh,
             params={"date": today})).json()

    assert recon["count"] == 3 and recon["grand_total"] == 50000

    cash = next(m for m in recon["by_method"] if m["method"] == "cash")
    assert cash["count"] == 2 and cash["total"] == 30000

    # each person answers for their own lines — this is the anti-discrepancy core
    admin_cash = next(r for r in recon["by_recorder"]
                      if r["method"] == "cash" and "Amaka" in r["recorded_by"])
    bursar_cash = next(r for r in recon["by_recorder"]
                       if r["method"] == "cash" and "Amaka" not in r["recorded_by"])
    assert admin_cash["total"] == 20000
    assert bursar_cash["total"] == 10000

    # every row carries its teller reference
    refs = {p["reference"] for p in recon["payments"]}
    assert refs == {"TELLER-001", "TELLER-002", "TRF-903311"}

    # a teacher may not see the money at all
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/fees/reconciliation", headers=th,
            params={"date": today})).status_code == 403


async def test_receipt_is_school_branded_with_signatures_and_stamp(ctx):
    """A receipt is evidence of payment — it must look official: crest, the
    bursar and principal signatures, and the school stamp. It must also render
    for a PART payment (showing the balance) and a FULL one."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # give the school branding assets (tiny valid PNGs as data-URIs)
    png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
           "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    uri = f"data:image/png;base64,{png}"
    await client.patch("/api/schools/me", headers=ah, json={
        "principal_name": "Dr. Test Principal"})
    # upload signature + stamp via the branding endpoints if present; else patch
    async with ids["session_factory"]() as db:
        from app.models.school import School
        s = await db.get(School, ids["school_id"])
        s.signature_url = uri
        s.stamp_url = uri
        s.logo_url = uri
        await db.commit()

    # bill and take a PART payment
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Fees"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 50000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    pay = (await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv["id"], "amount": 20000, "method": "cash",
        "reference": "TELLER-9", "paid_at": "2026-07-17"})).json()
    pid = pay.get("payment_id") or pay.get("id")

    r = await client.get(f"/api/fees/payments/{pid}/receipt", headers=ah)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"          # a real PDF came back
    assert len(r.content) > 3000             # branding images made it non-trivial


async def test_receipt_still_renders_without_any_branding(ctx):
    """A school that has uploaded no signature or stamp must still get a valid
    receipt — ruled lines stand in for the missing assets."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Fees"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 15000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    pay = (await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv["id"], "amount": 15000, "method": "cash",
        "reference": "TELLER-Z", "paid_at": "2026-07-17"})).json()
    pid = pay.get("payment_id") or pay.get("id")
    r = await client.get(f"/api/fees/payments/{pid}/receipt", headers=ah)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
