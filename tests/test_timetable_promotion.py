"""Timetable (clash-free) and end-of-session promotion."""
from tests.conftest import headers


async def _periods(client, ah):
    p1 = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 1", "sequence": 1,
        "start_time": "08:00", "end_time": "08:40"})).json()
    p2 = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 2", "sequence": 2,
        "start_time": "08:40", "end_time": "09:20"})).json()
    br = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Break", "sequence": 3, "start_time": "09:20",
        "end_time": "09:40", "is_break": True})).json()
    return p1, p2, br


async def test_an_arm_cannot_be_in_two_lessons_at_once(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p1, _, _ = await _periods(client, ah)
    english = (await client.post("/api/academics/subjects", headers=ah,
               json={"name": "English Language"})).json()["id"]

    first = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1["id"],
        "subject_id": ids["subject_id"]})
    assert first.status_code == 201

    clash = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1["id"],
        "subject_id": english})
    assert clash.status_code == 409
    assert "already has Mathematics in Period 1 on Monday" in clash.json()["detail"]


async def test_a_teacher_cannot_be_in_two_classrooms_at_once(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p1, _, _ = await _periods(client, ah)

    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    arm_b = (await client.post("/api/academics/arms", headers=ah,
             json={"class_id": class_id, "name": "B"})).json()["id"]

    teacher_id = ids["teacher_id"]
    ok = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1["id"],
        "subject_id": ids["subject_id"], "teacher_id": teacher_id})
    assert ok.status_code == 201

    # same teacher, same slot, different class -> the clash a paper timetable hides
    clash = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": arm_b, "day": "monday", "period_id": p1["id"],
        "subject_id": ids["subject_id"], "teacher_id": teacher_id})
    assert clash.status_code == 409
    assert "already teaching JSS1 A in Period 1 on Monday" in clash.json()["detail"]

    # a different period is fine
    p2 = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 9", "sequence": 9})).json()
    assert (await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": arm_b, "day": "monday", "period_id": p2["id"],
        "subject_id": ids["subject_id"], "teacher_id": teacher_id})).status_code == 201


async def test_no_lesson_can_be_scheduled_in_a_break(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    _, _, br = await _periods(client, ah)
    r = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": br["id"],
        "subject_id": ids["subject_id"]})
    assert r.status_code == 400
    assert "break" in r.json()["detail"].lower()


async def test_teacher_sees_their_own_timetable_and_parents_see_their_wards(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p1, _, _ = await _periods(client, ah)
    await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "tuesday", "period_id": p1["id"],
        "subject_id": ids["subject_id"], "teacher_id": ids["teacher_id"],
        "room": "Lab 1"})

    # the teacher, with no arguments, gets their personal timetable
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    mine = (await client.get("/api/timetable", headers=th)).json()
    assert len(mine["lessons"]) == 1
    assert mine["lessons"][0]["subject_name"] == "Mathematics"
    assert mine["lessons"][0]["arm_label"] == "JSS1 A"
    assert mine["lessons"][0]["room"] == "Lab 1"

    # a parent gets their ward's class timetable
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        p = User(school_id=ids["school_id"], email="mum@t.ng",
                 hashed_password=hash_password("mum12345"),
                 role=Role.PARENT, first_name="M", last_name="Um")
        db.add(p)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=p.id,
                        student_id=ids["student_ids"][0]))
        await db.commit()
    ph = await headers(client, "mum@t.ng", "mum12345")
    theirs = (await client.get("/api/timetable", headers=ph)).json()
    assert len(theirs["lessons"]) == 1
    assert theirs["lessons"][0]["teacher_name"] == "Tunde Bello"


# ---------------------------------------------------------------- promotion

async def _jss2(client, ah):
    klass = (await client.post("/api/academics/classes", headers=ah,
             json={"name": "JSS2", "category": "junior", "level_order": 2})).json()
    arm = (await client.post("/api/academics/arms", headers=ah,
           json={"class_id": klass["id"], "name": "A"})).json()
    return klass, arm


async def test_promotion_previews_before_it_moves_anybody(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _jss2(client, ah)
    repeater = ids["student_ids"][2]

    preview = (await client.post("/api/promotion/preview", headers=ah, json={
        "from_arm_id": ids["arm_id"],
        "repeat_student_ids": [repeater]})).json()

    assert preview["from"] == "JSS1 A" and preview["to"] == "JSS2 A"
    assert preview["committed"] is False
    assert len(preview["promoted"]) == 2
    assert len(preview["repeated"]) == 1
    assert preview["repeated"][0]["student_id"] == repeater

    # nothing has actually moved yet
    students = (await client.get("/api/students", headers=ah)).json()
    assert all(s["current_arm_id"] == ids["arm_id"] for s in students)


async def test_promotion_moves_the_class_up_and_repeats_stay(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    _, jss2a = await _jss2(client, ah)
    repeater = ids["student_ids"][2]

    res = (await client.post("/api/promotion/run", headers=ah, json={
        "from_arm_id": ids["arm_id"], "repeat_student_ids": [repeater],
        "commit": True})).json()
    assert res["committed"] is True and len(res["promoted"]) == 2

    students = {s["id"]: s for s in (await client.get("/api/students",
                headers=ah)).json()}
    assert students[ids["student_ids"][0]]["current_arm_id"] == jss2a["id"]
    assert students[ids["student_ids"][1]]["current_arm_id"] == jss2a["id"]
    assert students[repeater]["current_arm_id"] == ids["arm_id"]   # repeats

    # the move is on the audit trail with a reason
    logs = (await client.get("/api/audit-logs", headers=ah,
            params={"table_name": "students"})).json()
    assert any(l["changes"].get("reason", {}).get("new") == "promoted" for l in logs)


async def test_final_year_graduates_rather_than_being_promoted(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    # JSS1 is the only class -> it is the final year, so it graduates
    res = (await client.post("/api/promotion/run", headers=ah, json={
        "from_arm_id": ids["arm_id"], "commit": True})).json()

    assert res["graduating_class"] is True
    assert len(res["graduated"]) == 3 and res["promoted"] == []

    # graduates are deactivated, never deleted — transcripts must survive
    students = (await client.get("/api/students", headers=ah)).json()
    assert all(s["is_active"] is False for s in students)
    assert len(students) == 3


# ------------------------------------------------ living-timetable uniqueness

async def test_a_removed_lesson_frees_its_slot(ctx):
    """The bug: removing a lesson left a soft-deleted ghost that still occupied
    the database uniqueness rule, so re-placing anything in that slot 500'd."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p1, _, _ = await _periods(client, ah)
    english = (await client.post("/api/academics/subjects", headers=ah,
               json={"name": "English Language"})).json()["id"]

    first = (await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1["id"],
        "subject_id": ids["subject_id"]})).json()
    await client.delete(f"/api/timetable/lessons/{first['id']}", headers=ah)

    # the slot is free again — a different subject can take it
    again = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1["id"],
        "subject_id": english})
    assert again.status_code == 201

    # and only the new lesson shows on the grid
    grid = (await client.get("/api/timetable", headers=ah,
            params={"arm_id": ids["arm_id"]})).json()
    monday = [l for l in grid["lessons"]
              if l["day"] == "monday" and l["period_id"] == p1["id"]]
    assert [l["subject_name"] for l in monday] == ["English Language"]


async def test_a_deleted_period_frees_its_row_number(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 1", "sequence": 1})).json()
    await client.delete(f"/api/timetable/periods/{p['id']}", headers=ah)

    again = await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 1 (new times)", "sequence": 1,
        "start_time": "08:15", "end_time": "08:55"})
    assert again.status_code == 201


async def test_offboarding_a_teacher_vacates_their_timetable_slots(ctx):
    """A teacher who leaves must disappear from the printed timetable; the
    lesson itself stays — the class still has Maths to attend — but vacant."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p1, _, _ = await _periods(client, ah)

    leaver = (await client.post("/api/users", headers=ah, json={
        "email": "leaving@t.ng", "role": "teacher", "first_name": "Going",
        "last_name": "Soon", "password": "teach123"})).json()["user"]["id"]
    await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "friday", "period_id": p1["id"],
        "subject_id": ids["subject_id"], "teacher_id": leaver})

    r = (await client.delete(f"/api/users/{leaver}", headers=ah))
    assert r.status_code == 200

    grid = (await client.get("/api/timetable", headers=ah,
            params={"arm_id": ids["arm_id"]})).json()
    friday = next(l for l in grid["lessons"] if l["day"] == "friday")
    assert friday["subject_name"] == "Mathematics"   # the lesson survives
    assert friday["teacher_name"] is None            # the leaver does not

    # and the vacant slot accepts a replacement teacher without complaint
    # (the leaver no longer "occupies" it for clash purposes)
    replacement = (await client.post("/api/users", headers=ah, json={
        "email": "newhire@t.ng", "role": "teacher", "first_name": "New",
        "last_name": "Hire", "password": "teach123"})).json()["user"]["id"]
    await client.delete(f"/api/timetable/lessons/{friday['id']}", headers=ah)
    refill = await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "friday", "period_id": p1["id"],
        "subject_id": ids["subject_id"], "teacher_id": replacement})
    assert refill.status_code == 201
