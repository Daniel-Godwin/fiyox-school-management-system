"""Notifications — mock provider logging, targeting, and access control."""
from tests.conftest import headers


async def _make_parent(ids, email, phone, student_index):
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        parent = User(school_id=ids["school_id"], email=email,
                      hashed_password=hash_password("parent123"),
                      role=Role.PARENT, first_name="P", last_name="Arent",
                      phone=phone)
        db.add(parent)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=parent.id,
                        student_id=ids["student_ids"][student_index],
                        relationship="Guardian"))
        await db.commit()


async def test_announcement_blast_hits_target_group_and_logs(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _make_parent(ids, "p1@x.ng", "+2348020000001", 0)

    ann = (await client.post("/api/announcements", headers=ah, json={
        "title": "Staff Briefing", "message": "Monday 8am", "target": "teachers",
        "publish": True})).json()

    res = (await client.post(
        f"/api/notifications/announcements/{ann['id']}/send", headers=ah)).json()
    # only the teacher (has a phone, role=teachers); the parent must NOT get it
    assert res["recipients"] == 1

    logs = (await client.get("/api/notifications/logs", headers=ah)).json()
    assert len(logs) == 1
    log = logs[0]
    assert log["status"] == "mock" and log["provider"] == "mock"
    assert log["purpose"] == "announcement"
    assert "Staff Briefing" in log["body"]
    assert log["recipient"] == "+2348010000001"


async def test_fee_reminders_target_only_debtors(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    # parents for student 0 (will owe) and student 1 (will pay in full)
    await _make_parent(ids, "owes@x.ng", "+2348030000001", 0)
    await _make_parent(ids, "paid@x.ng", "+2348030000002", 1)

    # fee setup: one category/structure of 10,000 then invoice the arm
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 10000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # student 1 settles in full
    inv1 = (await client.get("/api/fees/invoices", headers=ah,
            params={"student_id": ids["student_ids"][1]})).json()[0]
    await client.post("/api/fees/payments", headers=ah, json={
        "invoice_id": inv1["id"], "method": "transfer",
        "reference": "FULL-1", "amount": 10000})

    res = (await client.post("/api/notifications/fee-reminders", headers=ah,
           json={"term_id": ids["term_id"]})).json()
    # students 0 and 2 owe, but only student 0 has a guardian with a phone
    assert res["students_with_debt_reminded"] == 1
    assert res["messages"] == 1

    logs = (await client.get("/api/notifications/logs", headers=ah,
            params={"purpose": "fee_reminder"})).json()
    assert len(logs) == 1
    assert logs[0]["recipient"] == "+2348030000001"   # the debtor's parent
    assert "10,000.00" in logs[0]["body"]


async def test_draft_announcement_cannot_be_sent(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    draft = (await client.post("/api/announcements", headers=ah, json={
        "title": "Draft", "message": "x", "target": "all", "publish": False})).json()
    r = await client.post(
        f"/api/notifications/announcements/{draft['id']}/send", headers=ah)
    assert r.status_code == 400


async def test_teacher_cannot_send_or_view_logs(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/notifications/logs", headers=th)).status_code == 403
    assert (await client.post("/api/notifications/fee-reminders", headers=th,
            json={"term_id": ids["term_id"]})).status_code == 403
