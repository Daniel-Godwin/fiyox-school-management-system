"""Receipts + bursar summary."""
from tests.conftest import headers


async def _setup_and_invoice(client, h, ids, amount=20000):
    cat = (await client.post("/api/fees/categories", headers=h,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=h, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": amount})
    await client.post("/api/fees/invoices/generate", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})


async def test_receipt_pdf(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _setup_and_invoice(client, h, ids)
    inv = (await client.get("/api/fees/invoices", headers=h,
           params={"student_id": ids["student_ids"][0]})).json()[0]
    pay = (await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": inv["id"], "method": "pos",
        "reference": "POS-77", "amount": 12000})).json()

    r = await client.get(f"/api/fees/payments/{pay['payment_id']}/receipt", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1500  # a real document, not an empty shell

    # teachers cannot pull receipts
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get(
        f"/api/fees/payments/{pay['payment_id']}/receipt", headers=th)).status_code == 403


async def test_bursar_summary_numbers(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _setup_and_invoice(client, h, ids, amount=20000)  # 3 students x 20k = 60k

    # student 0 pays half, student 1 pays in full, student 2 pays nothing
    invs = {}
    for i in range(3):
        invs[i] = (await client.get("/api/fees/invoices", headers=h,
                   params={"student_id": ids["student_ids"][i]})).json()[0]
    await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": invs[0]["id"], "method": "cash",
        "reference": "R-A", "amount": 10000})
    await client.post("/api/fees/payments", headers=h, json={
        "invoice_id": invs[1]["id"], "method": "transfer",
        "reference": "R-B", "amount": 20000})

    s = (await client.get("/api/fees/summary", headers=h,
         params={"term_id": ids["term_id"]})).json()
    assert s["invoices"] == 3
    assert s["expected"] == 60000
    assert s["collected"] == 30000
    assert s["outstanding"] == 30000
    assert s["collection_rate"] == 50.0
    assert s["by_status"] == {"unpaid": 1, "part_paid": 1, "paid": 1}
    # debtors sorted by balance desc: student 2 owes 20k, student 0 owes 10k
    assert [d["balance"] for d in s["debtors"]] == [20000, 10000]
