"""Attendance — bulk marking, corrections audited, summaries, access control."""
from tests.conftest import headers


async def _mark(client, h, ids, day, statuses):
    recs = [{"student_id": sid, "status": st}
            for sid, st in zip(ids["student_ids"], statuses)]
    return (await client.post("/api/attendance/mark", headers=h, json={
        "arm_id": ids["arm_id"], "date": day, "records": recs})).json()


async def test_bulk_mark_and_register(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")

    res = await _mark(client, h, ids, "2026-07-06", ["present", "absent", "late"])
    assert res == {"date": "2026-07-06", "created": 3, "updated": 0, "unchanged": 0}

    reg = (await client.get("/api/attendance/register", headers=h,
           params={"arm_id": ids["arm_id"], "date": "2026-07-06"})).json()
    assert len(reg) == 3
    assert {r["status"] for r in reg} == {"present", "absent", "late"}


async def test_remark_is_upsert_and_audited(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _mark(client, h, ids, "2026-07-06", ["absent", "present", "present"])
    # teacher corrects the first student: absent -> present
    res = await _mark(client, h, ids, "2026-07-06", ["present", "present", "present"])
    assert res["created"] == 0 and res["updated"] == 1 and res["unchanged"] == 2

    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    logs = (await client.get("/api/audit-logs", headers=ah,
            params={"table_name": "attendance"})).json()
    assert logs[0]["changes"]["status"] == {"old": "absent", "new": "present"}


async def test_summary_counts(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _mark(client, h, ids, "2026-07-06", ["present", "present", "present"])
    await _mark(client, h, ids, "2026-07-07", ["absent", "present", "present"])
    await _mark(client, h, ids, "2026-07-08", ["late", "present", "present"])

    s = (await client.get("/api/attendance/summary", headers=h,
         params={"student_id": ids["student_ids"][0]})).json()
    assert s["days_recorded"] == 3
    assert s["present"] == 1 and s["absent"] == 1 and s["late"] == 1


async def test_parent_sees_own_ward_only(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _mark(client, h, ids, "2026-07-06", ["present", "present", "present"])

    # create a parent linked to student 0 only
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        parent = User(school_id=ids["school_id"], email="parent@x.ng",
                      hashed_password=hash_password("parent123"),
                      role=Role.PARENT, first_name="Mama", last_name="Chinedu")
        db.add(parent)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=parent.id,
                        student_id=ids["student_ids"][0], relationship="Mother"))
        await db.commit()

    ph = await headers(client, "parent@x.ng", "parent123")
    own = await client.get("/api/attendance/summary", headers=ph,
                           params={"student_id": ids["student_ids"][0]})
    assert own.status_code == 200 and own.json()["present"] == 1

    other = await client.get("/api/attendance/summary", headers=ph,
                             params={"student_id": ids["student_ids"][1]})
    assert other.status_code == 403

    # and a parent can never mark attendance
    blocked = await client.post("/api/attendance/mark", headers=ph, json={
        "arm_id": ids["arm_id"], "date": "2026-07-06",
        "records": [{"student_id": ids["student_ids"][0], "status": "present"}]})
    assert blocked.status_code == 403
