"""Schools change: fee increments, retired categories, arms opened and closed.

The invariant under test throughout: **money already collected is never
rewritten.** Editing a fee changes future bills; existing invoices only move
when the admin explicitly re-issues, and even then never below what was paid.
"""
from tests.conftest import headers


async def _class_id(ids):
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        return arm.class_id


async def _bill(client, ah, ids, amount=30000, name="School Fees"):
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": name})).json()
    cid = await _class_id(ids)
    st = (await client.post("/api/fees/structures", headers=ah, json={
        "class_id": cid, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": amount})).json()
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    return cat, st, cid


async def test_fee_increment_does_not_touch_existing_invoices(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    cat, st, cid = await _bill(client, ah, ids, 30000)

    before = (await client.get("/api/fees/invoices", headers=ah,
              params={"term_id": ids["term_id"]})).json()
    assert all(i["amount"] == 30000 for i in before)

    # the school raises the fee
    r = (await client.patch(f"/api/fees/structures/{st['id']}", headers=ah,
         json={"amount": 45000})).json()
    assert r["amount"] == 45000

    # existing bills are untouched — nobody's debt changes behind their back
    after = (await client.get("/api/fees/invoices", headers=ah,
             params={"term_id": ids["term_id"]})).json()
    assert all(i["amount"] == 30000 for i in after)

    # ...until the admin explicitly re-issues
    res = (await client.post("/api/fees/invoices/reissue", headers=ah,
           json={"term_id": ids["term_id"], "class_id": cid})).json()
    assert res["new_total"] == 45000 and res["updated"] == 3
    reissued = (await client.get("/api/fees/invoices", headers=ah,
                params={"term_id": ids["term_id"]})).json()
    assert all(i["amount"] == 45000 for i in reissued)
    assert all(i["balance"] == 45000 for i in reissued)


async def test_reissue_never_rewrites_settled_money(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    cat, st, cid = await _bill(client, ah, ids, 30000)
    invs = (await client.get("/api/fees/invoices", headers=ah,
            params={"term_id": ids["term_id"]})).json()

    # student A settles in full; student B pays 25,000 of 30,000
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": invs[0]["id"], "method": "transfer",
        "reference": "FULL-A", "amount": 30000})
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": invs[1]["id"], "method": "cash",
        "reference": "PART-B", "amount": 25000})

    # the school now REDUCES the fee to 10,000 and re-issues
    await client.patch(f"/api/fees/structures/{st['id']}", headers=ah,
                       json={"amount": 10000})
    res = (await client.post("/api/fees/invoices/reissue", headers=ah,
           json={"term_id": ids["term_id"], "class_id": cid})).json()

    assert res["skipped_paid"] == 1          # the settled invoice is left alone
    assert res["clamped_to_amount_paid"] == 1  # B cannot be billed below 25,000

    after = {i["id"]: i for i in (await client.get("/api/fees/invoices", headers=ah,
             params={"term_id": ids["term_id"]})).json()}
    assert after[invs[0]["id"]]["amount"] == 30000   # settled: untouched
    assert after[invs[0]["id"]]["status"] == "paid"
    assert after[invs[1]["id"]]["amount"] == 25000   # clamped to what was paid
    assert after[invs[1]["id"]]["balance"] == 0
    assert after[invs[2]["id"]]["amount"] == 10000   # untouched student: new fee


async def test_retiring_a_category_removes_its_fees_but_keeps_history(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    cat, st, cid = await _bill(client, ah, ids, 30000, "School Fees")

    # add a second category: Exam Fees 5,000
    cat2 = (await client.post("/api/fees/categories", headers=ah,
            json={"name": "Exam Fees"})).json()
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": cid, "term_id": ids["term_id"],
        "category_id": cat2["id"], "amount": 5000})

    # the school drops Exam Fees entirely
    r = (await client.delete(f"/api/fees/categories/{cat2['id']}", headers=ah)).json()
    assert r["retired"] is True and r["structures_removed"] == 1

    # it disappears from the pickers, but the old invoices are unchanged
    cats = (await client.get("/api/fees/categories", headers=ah)).json()
    assert [c["name"] for c in cats] == ["School Fees"]
    invs = (await client.get("/api/fees/invoices", headers=ah,
            params={"term_id": ids["term_id"]})).json()
    assert all(i["amount"] == 30000 for i in invs)   # billed before Exam Fees existed

    # re-issuing now applies the reduced structure (School Fees only)
    res = (await client.post("/api/fees/invoices/reissue", headers=ah,
           json={"term_id": ids["term_id"], "class_id": cid})).json()
    assert res["new_total"] == 30000

    # the audit trail records who dropped it
    logs = (await client.get("/api/audit-logs", headers=ah,
            params={"table_name": "fee_categories"})).json()
    assert any(l["action"] == "delete" for l in logs)


async def test_arms_can_be_opened_closed_and_students_moved(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    cid = await _class_id(ids)

    # open a second arm: JSS1 B
    arm_b = (await client.post("/api/academics/arms", headers=ah,
             json={"class_id": cid, "name": "B"})).json()
    assert arm_b["label"] == "JSS1 B"

    # it cannot be closed while empty? it can — closing an EMPTY arm is fine
    tmp = (await client.post("/api/academics/arms", headers=ah,
           json={"class_id": cid, "name": "C"})).json()
    assert (await client.delete(f"/api/academics/arms/{tmp['id']}",
            headers=ah)).status_code == 200

    # the original arm has students: closing it must be refused
    refused = await client.delete(f"/api/academics/arms/{ids['arm_id']}", headers=ah)
    assert refused.status_code == 409
    assert "student" in refused.json()["detail"].lower()

    # move the students into JSS1 B, then the old arm can be closed
    moved = (await client.post("/api/academics/students/transfer", headers=ah,
             json={"student_ids": ids["student_ids"], "to_arm_id": arm_b["id"]})).json()
    assert moved["moved"] == 3
    assert (await client.delete(f"/api/academics/arms/{ids['arm_id']}",
            headers=ah)).status_code == 200

    arms = (await client.get("/api/academics/arms", headers=ah)).json()
    assert [a["label"] for a in arms] == ["JSS1 B"]


async def test_only_admin_can_restructure(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    cat, st, cid = await _bill(client, ah, ids, 30000)

    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.patch(f"/api/fees/structures/{st['id']}", headers=th,
            json={"amount": 1})).status_code == 403
    assert (await client.delete(f"/api/academics/arms/{ids['arm_id']}",
            headers=th)).status_code == 403

    # a bursar may correct a category name, but not restructure fees or classes
    from app.models.school import User, Role
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        db.add(User(school_id=ids["school_id"], email="bursar@x.ng",
                    hashed_password=hash_password("bursar123"),
                    role=Role.BURSAR, first_name="B", last_name="Ursar"))
        await db.commit()
    bh = await headers(client, "bursar@x.ng", "bursar123")
    assert (await client.patch(f"/api/fees/categories/{cat['id']}", headers=bh,
            json={"name": "Tuition"})).status_code == 200
    assert (await client.post("/api/fees/invoices/reissue", headers=bh,
            json={"term_id": ids["term_id"], "class_id": cid})).status_code == 403
