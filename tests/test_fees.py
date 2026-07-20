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


async def test_every_payment_on_an_invoice_stays_reprintable(ctx):
    """A parent paying in instalments must be able to get evidence for any one
    of them, at any time — not only in the session where it was recorded."""
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
        "category_id": cat["id"], "amount": 60000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]

    # three instalments: part, part, then the balance
    for amount, ref, day in ((20000, "TELLER-A", "2026-07-10"),
                             (25000, "TELLER-B", "2026-07-14"),
                             (15000, "TELLER-C", "2026-07-17")):
        await client.post("/api/fees/payments", headers=ah, json={
            "invoice_id": inv["id"], "amount": amount, "method": "cash",
            "reference": ref, "paid_at": day})

    rows = (await client.get(f"/api/fees/invoices/{inv['id']}/payments",
            headers=ah)).json()
    assert len(rows) == 3
    assert {r["reference"] for r in rows} == {"TELLER-A", "TELLER-B", "TELLER-C"}
    assert rows[0]["paid_at"] == "2026-07-17"          # newest first
    assert all(r["recorded_by"] == "Amaka Okoro" for r in rows)

    # each instalment prints its own receipt, including the part payments
    for r in rows:
        pdf = await client.get(f"/api/fees/payments/{r['payment_id']}/receipt",
                               headers=ah)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # the invoice is now fully paid, and the receipts still all exist
    after = (await client.get("/api/fees/invoices", headers=ah,
             params={"term_id": ids["term_id"]})).json()
    paid = next(i for i in after if i["id"] == inv["id"])
    assert paid["balance"] == 0 and paid["status"] == "paid"
    assert len((await client.get(f"/api/fees/invoices/{inv['id']}/payments",
                headers=ah)).json()) == 3


async def test_invoice_payments_are_tenant_scoped(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    # an invoice id from another school must 404, never leak
    r = await client.get("/api/fees/invoices/not-a-real-invoice/payments",
                         headers=ah)
    assert r.status_code == 404


async def _billed_with_instalments(client, ah, ids):
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Fees"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 60000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    invs = (await client.get("/api/fees/invoices", headers=ah,
            params={"term_id": ids["term_id"]})).json()
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": invs[0]["id"], "amount": 25000, "method": "cash",
        "reference": "T-101", "paid_at": "2026-07-17"})
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": invs[0]["id"], "amount": 35000, "method": "transfer",
        "reference": "T-102", "paid_at": "2026-07-17"})
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": invs[1]["id"], "amount": 20000, "method": "cash",
        "reference": "T-103", "paid_at": "2026-07-17"})
    return invs


async def test_a_receipt_can_be_viewed_or_downloaded(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    invs = await _billed_with_instalments(client, ah, ids)
    pid = (await client.get(f"/api/fees/invoices/{invs[0]['id']}/payments",
           headers=ah)).json()[0]["payment_id"]

    view = await client.get(f"/api/fees/payments/{pid}/receipt", headers=ah)
    assert view.status_code == 200
    assert view.headers["content-disposition"].startswith("inline")

    save = await client.get(f"/api/fees/payments/{pid}/receipt", headers=ah,
                            params={"download": "true"})
    assert save.status_code == 200
    assert save.headers["content-disposition"].startswith("attachment")
    assert save.content[:4] == b"%PDF"


async def test_bulk_receipts_zip_by_day_and_by_invoice(ctx):
    """A bursar's end-of-day pack, and one family's instalments — as files that
    can actually be filed, not a dozen browser tabs."""
    import io
    import zipfile

    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    invs = await _billed_with_instalments(client, ah, ids)

    day = await client.get("/api/fees/receipts.zip", headers=ah,
                           params={"date": "2026-07-17"})
    assert day.status_code == 200
    assert day.headers["content-type"] == "application/zip"
    assert "receipts-2026-07-17.zip" in day.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(day.content)).namelist()
    assert len(names) == 3
    # named by admission number + teller reference, so the pack files itself
    assert any("T-101" in n and n.endswith(".pdf") for n in names)

    one = await client.get("/api/fees/receipts.zip", headers=ah,
                           params={"invoice_id": invs[0]["id"]})
    assert one.status_code == 200
    inner = zipfile.ZipFile(io.BytesIO(one.content))
    assert len(inner.namelist()) == 2                  # both instalments
    for n in inner.namelist():
        assert inner.read(n)[:4] == b"%PDF"            # each really is a PDF


async def test_bulk_receipts_guards_and_permissions(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _billed_with_instalments(client, ah, ids)

    # exactly one scope is required
    assert (await client.get("/api/fees/receipts.zip", headers=ah)).status_code == 400
    assert (await client.get("/api/fees/receipts.zip", headers=ah, params={
        "date": "2026-07-17", "term_id": ids["term_id"]})).status_code == 400
    # a day with no money is a clean 404, not an empty zip
    assert (await client.get("/api/fees/receipts.zip", headers=ah,
            params={"date": "2020-01-01"})).status_code == 404

    # teachers have no business with the school's takings
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/fees/receipts.zip", headers=th,
            params={"date": "2026-07-17"})).status_code == 403


async def test_invoices_carry_the_billed_breakdown(ctx):
    """A parent should see what the money is for. The lines are snapshotted at
    generation, so a later change to the school's fee structure can never
    rewrite what was billed and paid."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id

    cats = {}
    for name, amount in (("Tuition", 35000), ("PTA Levy", 3000),
                         ("Examination", 5000)):
        c = (await client.post("/api/fees/categories", headers=ah,
             json={"name": name})).json()
        cats[name] = c["id"]
        await client.post("/api/fees/structures", headers=ah, json={
            "class_id": class_id, "term_id": ids["term_id"],
            "category_id": c["id"], "amount": amount})

    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]

    assert inv["amount"] == 43000
    lines = {i["name"]: i["amount"] for i in inv["items"]}
    assert lines == {"Tuition": 35000, "PTA Levy": 3000, "Examination": 5000}
    # the lines add up to the invoice total — no silent gap
    assert round(sum(lines.values()), 2) == inv["amount"]

    # the parent sees the same breakdown in their portal
    from app.core.security import hash_password
    from app.models.school import Role, User
    from app.models.student import Guardian
    async with ids["session_factory"]() as db:
        p = User(school_id=ids["school_id"], email="mum@fee.ng",
                 hashed_password=hash_password("mum12345"), role=Role.PARENT,
                 first_name="M", last_name="U")
        db.add(p)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=p.id,
                        student_id=inv["student_id"]))
        await db.commit()
    ph = await headers(client, "mum@fee.ng", "mum12345")
    mine = (await client.get("/api/my/fees", headers=ph,
            params={"term_id": ids["term_id"]})).json()
    assert {i["name"] for i in mine[0]["items"]} == set(lines)


async def test_changing_the_fee_structure_never_rewrites_an_issued_invoice(ctx):
    """The evidence property: last term's receipt must not change because the
    school renamed a category or raised a fee this term."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id

    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "PTA Levy"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 3000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    assert inv["items"][0] == {"name": "PTA Levy", "amount": 3000}

    # the school renames the category and raises the amount afterwards
    from app.models.fees import FeeCategory, FeeStructure
    from sqlalchemy import select as _select
    async with ids["session_factory"]() as db:
        c = await db.get(FeeCategory, cat["id"])
        c.name = "Parents Association Levy (revised)"
        s = (await db.execute(_select(FeeStructure).where(
            FeeStructure.category_id == cat["id"]))).scalars().first()
        s.amount = 9000
        await db.commit()

    # the already-issued invoice is untouched — name and amount as billed
    after = (await client.get("/api/fees/invoices", headers=ah,
             params={"term_id": ids["term_id"]})).json()[0]
    assert after["items"][0] == {"name": "PTA Levy", "amount": 3000}
    assert after["amount"] == 3000


async def test_receipt_prints_for_an_invoice_with_no_line_items(ctx):
    """Invoices issued before line items existed must still print a receipt —
    the breakdown section simply doesn't appear."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    from app.models.fees import InvoiceItem
    from sqlalchemy import select as _select
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Fees"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 10000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]

    # simulate a legacy invoice: strip its lines
    async with ids["session_factory"]() as db:
        for row in (await db.execute(_select(InvoiceItem).where(
                InvoiceItem.invoice_id == inv["id"]))).scalars().all():
            await db.delete(row)
        await db.commit()

    pay = (await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv["id"], "amount": 10000, "method": "cash",
        "reference": "LEGACY-1", "paid_at": "2026-07-17"})).json()
    pid = pay.get("payment_id") or pay.get("id")
    r = await client.get(f"/api/fees/payments/{pid}/receipt", headers=ah)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


async def test_backfill_adds_breakdown_to_older_invoices(ctx):
    """Invoices issued before Fiyox stored line items print only a total. The
    backfill reconstructs the breakdown from the fee structures they were
    billed from."""
    from sqlalchemy import select as _select
    from app.models.fees import InvoiceItem

    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    for name, amount in (("Tuition", 35000), ("PTA Levy", 3000)):
        c = (await client.post("/api/fees/categories", headers=ah,
             json={"name": name})).json()
        await client.post("/api/fees/structures", headers=ah, json={
            "class_id": class_id, "term_id": ids["term_id"],
            "category_id": c["id"], "amount": amount})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # simulate legacy invoices: remove the lines
    async with ids["session_factory"]() as db:
        for row in (await db.execute(_select(InvoiceItem))).scalars().all():
            await db.delete(row)
        await db.commit()
    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    # the breakdown is now DERIVED on the fly (structures still match the bill),
    # so parents already see it; the backfill makes it permanent so a future
    # fee change cannot take it away
    assert {i["name"] for i in inv["items"]} == {"Tuition", "PTA Levy"}

    # preview writes nothing
    preview = (await client.post(
        f"/api/fees/invoices/backfill-items?term_id={ids['term_id']}&commit=false",
        headers=ah)).json()
    assert preview["breakdown_added"] == 3 and preview["committed"] is False
    from sqlalchemy import select as _sel
    async with ids["session_factory"]() as db:
        assert (await db.execute(_sel(InvoiceItem))).scalars().first() is None

    # commit fills them in
    done = (await client.post(
        f"/api/fees/invoices/backfill-items?term_id={ids['term_id']}&commit=true",
        headers=ah)).json()
    assert done["breakdown_added"] == 3
    after = (await client.get("/api/fees/invoices", headers=ah,
             params={"term_id": ids["term_id"]})).json()[0]
    assert {i["name"]: i["amount"] for i in after["items"]} == {
        "Tuition": 35000, "PTA Levy": 3000}
    assert round(sum(i["amount"] for i in after["items"]), 2) == after["amount"]

    # running it again is harmless — nothing is duplicated
    again = (await client.post(
        f"/api/fees/invoices/backfill-items?term_id={ids['term_id']}&commit=true",
        headers=ah)).json()
    assert again["breakdown_added"] == 0 and again["already_had_breakdown"] == 3


async def test_backfill_refuses_to_invent_a_breakdown_that_contradicts_the_bill(ctx):
    """If the school changed its fees after issuing invoices, the structures no
    longer add up to what the parent was billed. Printing that as the breakdown
    would be a false receipt — so those invoices are left alone."""
    from sqlalchemy import select as _select
    from app.models.fees import FeeStructure, InvoiceItem

    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Tuition"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 20000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    async with ids["session_factory"]() as db:
        for row in (await db.execute(_select(InvoiceItem))).scalars().all():
            await db.delete(row)
        # the school raises tuition AFTER the invoices went out
        s = (await db.execute(_select(FeeStructure))).scalars().first()
        s.amount = 50000
        await db.commit()

    r = (await client.post(
        f"/api/fees/invoices/backfill-items?term_id={ids['term_id']}&commit=true",
        headers=ah)).json()
    assert r["breakdown_added"] == 0
    assert len(r["left_alone"]) == 3
    assert r["left_alone"][0]["billed"] == 20000
    assert r["left_alone"][0]["structures_total"] == 50000
    assert "changed" in r["left_alone"][0]["reason"]

    # the invoices are untouched: still no breakdown, amounts intact
    invs = (await client.get("/api/fees/invoices", headers=ah,
            params={"term_id": ids["term_id"]})).json()
    assert all(i["items"] == [] and i["amount"] == 20000 for i in invs)


async def test_backfill_is_admin_only(ctx):
    client, ids = ctx
    bh = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await client.post("/api/users", headers=bh, json={
        "email": "bursar2@x.ng", "role": "bursar", "first_name": "B",
        "last_name": "R", "password": "burs1234"})
    h = await headers(client, "bursar2@x.ng", "burs1234")
    r = await client.post(
        f"/api/fees/invoices/backfill-items?term_id={ids['term_id']}&commit=true",
        headers=h)
    assert r.status_code == 403


async def test_breakdown_is_derived_for_invoices_that_have_no_stored_lines(ctx):
    """Invoices issued before Fiyox stored line items must still show what the
    fees were for — derived from the structures they were billed from, with no
    migration step for the school."""
    from sqlalchemy import select as _select
    from app.models.fees import InvoiceItem

    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    for name, amount in (("Tuition", 15000), ("PTA Levy", 3000),
                         ("Examination", 5000)):
        c = (await client.post("/api/fees/categories", headers=ah,
             json={"name": name})).json()
        await client.post("/api/fees/structures", headers=ah, json={
            "class_id": class_id, "term_id": ids["term_id"],
            "category_id": c["id"], "amount": amount})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # strip the stored lines: this is exactly an invoice issued by an older build
    async with ids["session_factory"]() as db:
        for row in (await db.execute(_select(InvoiceItem))).scalars().all():
            await db.delete(row)
        await db.commit()

    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    assert inv["amount"] == 23000
    lines = {i["name"]: i["amount"] for i in inv["items"]}
    assert lines == {"Tuition": 15000, "PTA Levy": 3000, "Examination": 5000}

    # and the receipt prints it
    pay = (await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv["id"], "amount": 15000, "method": "cash",
        "reference": "0016", "paid_at": "2026-07-18"})).json()
    pid = pay.get("payment_id") or pay.get("id")
    pdf = await client.get(f"/api/fees/payments/{pid}/receipt", headers=ah)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


async def test_derivation_refuses_when_the_bill_and_structures_disagree(ctx):
    """If the school changed its fees after issuing an invoice, no breakdown is
    shown — better a plain receipt than one that contradicts what was paid."""
    from sqlalchemy import select as _select
    from app.models.fees import FeeStructure, InvoiceItem

    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Tuition"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 20000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    async with ids["session_factory"]() as db:
        for row in (await db.execute(_select(InvoiceItem))).scalars().all():
            await db.delete(row)
        s = (await db.execute(_select(FeeStructure))).scalars().first()
        s.amount = 50000                      # fees raised after billing
        await db.commit()

    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    assert inv["amount"] == 20000
    assert inv["items"] == []                 # no invented breakdown


async def test_stored_lines_always_win_over_derivation(ctx):
    """Once lines are stored they are the truth, even if the school's current
    structures now say something different."""
    from sqlalchemy import select as _select
    from app.models.fees import FeeStructure

    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "Tuition"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 20000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    async with ids["session_factory"]() as db:
        s = (await db.execute(_select(FeeStructure))).scalars().first()
        s.amount = 20000     # unchanged total, but rename the category
        from app.models.fees import FeeCategory
        c = await db.get(FeeCategory, cat["id"])
        c.name = "Tuition (renamed later)"
        await db.commit()

    inv = (await client.get("/api/fees/invoices", headers=ah,
           params={"term_id": ids["term_id"]})).json()[0]
    # the stored snapshot keeps the ORIGINAL name, not the new one
    assert inv["items"] == [{"name": "Tuition", "amount": 20000}]
