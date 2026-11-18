"""Automatic parent notifications on result-published and payment-received.

A parent with a phone and an email on file should get a message over both
channels when their child's result is published and when a fee payment is
recorded — and nothing at all when the school has switched notifications off.
Every message must land in the delivery log.
"""
from sqlalchemy import select

from tests.conftest import headers
from app.models.notifications import MessageLog, MessagePurpose


async def _make_parent(ids, email, student_index, *, phone="08030000001"):
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        parent = User(school_id=ids["school_id"], email=email, phone=phone,
                      hashed_password=hash_password("parent123"),
                      role=Role.PARENT, first_name="Pa", last_name="Rent")
        db.add(parent)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=parent.id,
                        student_id=ids["student_ids"][student_index],
                        relationship="Guardian"))
        await db.commit()


async def _logs(ids, purpose):
    async with ids["session_factory"]() as db:
        return (await db.execute(select(MessageLog).where(
            MessageLog.purpose == purpose))).scalars().all()


async def _seed_and_compute(client, ids, teacher, admin):
    comp = ids["component_ids"]
    arm, subj, term = ids["arm_id"], ids["subject_id"], ids["term_id"]
    rows = [{"student_id": s, "scores": {comp[0]: 8, comp[1]: 7, comp[2]: 9, comp[3]: 60}}
            for s in ids["student_ids"]]
    await client.post("/api/scores", headers=teacher, json={
        "subject_id": subj, "arm_id": arm, "term_id": term, "rows": rows})
    await client.post("/api/results/compute", headers=admin,
                      json={"arm_id": arm, "term_id": term})


async def test_result_published_notifies_parent_on_both_channels(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    teacher = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _make_parent(ids, "parent0@x.ng", 0)
    await _seed_and_compute(client, ids, teacher, admin)

    pub = (await client.post("/api/results/publish", headers=admin,
                             json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert pub["published"] == 3
    assert pub["parents_notified"] == 1            # only student 0 has a guardian

    logs = await _logs(ids, MessagePurpose.RESULT_PUBLISHED)
    # one SMS + one email to the single linked parent
    channels = sorted(l.channel for l in logs)
    assert len(logs) == 2 and channels == ["email", "sms"]
    assert all(l.related_id == ids["student_ids"][0] for l in logs)


async def test_payment_received_notifies_parent(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _make_parent(ids, "parent0@x.ng", 0)

    # a fee structure + invoice for student 0, then a payment
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        class_id = (await db.get(ClassArm, ids["arm_id"])).class_id
    cat = (await client.post("/api/fees/categories", headers=admin,
                             json={"name": "School Fees"})).json()
    await client.post("/api/fees/structures", headers=admin, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 30000})
    await client.post("/api/fees/invoices/generate", headers=admin,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    inv = (await client.get("/api/fees/invoices", headers=admin,
                            params={"student_id": ids["student_ids"][0]})).json()[0]
    pay = (await client.post("/api/fees/payments", headers=admin, json={
        "invoice_id": inv["id"], "method": "cash", "reference": "PN-1",
        "amount": 20000})).json()
    assert pay["parent_notified"] is True

    logs = await _logs(ids, MessagePurpose.PAYMENT_RECEIVED)
    assert len(logs) == 2                           # SMS + email
    assert any("20,000" in l.body for l in logs)    # the amount is in the message
    assert any("10,000" in l.body for l in logs)    # and the remaining balance


async def test_notifications_can_be_switched_off(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    teacher = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _make_parent(ids, "parent0@x.ng", 0)
    # switch the school's parent notifications off
    r = (await client.patch("/api/schools/me", headers=admin,
                            json={"parent_notifications_enabled": False})).json()
    assert r["parent_notifications_enabled"] is False

    await _seed_and_compute(client, ids, teacher, admin)
    pub = (await client.post("/api/results/publish", headers=admin,
                             json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert pub["published"] == 3
    assert pub["parents_notified"] == 0
    assert await _logs(ids, MessagePurpose.RESULT_PUBLISHED) == []
