"""A parent with several children in the school must see all of them.

Nigerian families commonly have three or four children in the same school. Every
parent-facing surface has to handle that — and must scope strictly to the
caller's own family, never to a class id they simply asked for.
"""
from tests.conftest import headers


async def _family(client, ids, ward_indexes, email="mama@x.ng"):
    """Create a parent linked to several students, in different classes."""
    from app.core.security import hash_password
    from app.models.school import Role, User
    from app.models.student import Guardian

    async with ids["session_factory"]() as db:
        parent = User(school_id=ids["school_id"], email=email,
                      hashed_password=hash_password("mama1234"),
                      role=Role.PARENT, first_name="Mama", last_name="Eze")
        db.add(parent)
        await db.flush()
        for i in ward_indexes:
            db.add(Guardian(school_id=ids["school_id"], parent_user_id=parent.id,
                            student_id=ids["student_ids"][i],
                            relationship="Mother"))
        await db.commit()
        return parent.id


async def _second_arm(client, ah, ids, name="B"):
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    return (await client.post("/api/academics/arms", headers=ah,
            json={"class_id": class_id, "name": name})).json()["id"]


async def test_parent_sees_every_ward_in_the_portal(ctx):
    client, ids = ctx
    await _family(client, ids, [0, 1, 2])           # three children
    ph = await headers(client, "mama@x.ng", "mama1234")

    wards = (await client.get("/api/my/wards", headers=ph)).json()
    assert len(wards) == 3
    names = {w["name"] for w in wards}
    assert len(names) == 3
    assert "Chinedu Eze" in names and "Fatima Bello" in names


async def test_parent_sees_fees_for_every_ward(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _family(client, ids, [0, 1, 2])

    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 25000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    ph = await headers(client, "mama@x.ng", "mama1234")
    fees = (await client.get("/api/my/fees", headers=ph,
            params={"term_id": ids["term_id"]})).json()
    assert len(fees) == 3                       # one invoice per child
    assert {f["balance"] for f in fees} == {25000}


async def test_timetable_covers_all_wards_across_different_classes(ctx):
    """The bug: a parent saw only their FIRST child's timetable."""
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # a period, and a second class arm
    p1 = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 1", "sequence": 1})).json()["id"]
    arm_b = await _second_arm(client, ah, ids)
    english = (await client.post("/api/academics/subjects", headers=ah,
               json={"name": "English Language"})).json()["id"]

    # move the second child into JSS1 B, so the family spans two classes
    await client.post("/api/academics/students/transfer", headers=ah, json={
        "student_ids": [ids["student_ids"][1]], "to_arm_id": arm_b})

    await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1,
        "subject_id": ids["subject_id"]})              # JSS1 A: Maths
    await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": arm_b, "day": "monday", "period_id": p1,
        "subject_id": english})                        # JSS1 B: English

    await _family(client, ids, [0, 1])   # one child in each class
    ph = await headers(client, "mama@x.ng", "mama1234")

    grid = (await client.get("/api/timetable", headers=ph)).json()

    # both children are named
    assert len(grid["wards"]) == 2
    assert {w["name"] for w in grid["wards"]} == {"Chinedu Eze", "Fatima Bello"}

    # and BOTH classes' lessons come back, each tagged with its class
    subjects = {l["subject_name"] for l in grid["lessons"]}
    assert subjects == {"Mathematics", "English Language"}
    labels = {l["arm_label"] for l in grid["lessons"]}
    assert labels == {"JSS1 A", "JSS1 B"}


async def test_parent_can_filter_to_one_ward_but_not_to_a_strangers_class(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    p1 = (await client.post("/api/timetable/periods", headers=ah, json={
        "name": "Period 1", "sequence": 1})).json()["id"]
    arm_b = await _second_arm(client, ah, ids)
    await client.post("/api/timetable/lessons", headers=ah, json={
        "arm_id": ids["arm_id"], "day": "monday", "period_id": p1,
        "subject_id": ids["subject_id"]})

    # this parent's only child is in JSS1 A
    await _family(client, ids, [0])
    ph = await headers(client, "mama@x.ng", "mama1234")

    # their own child's class: allowed
    ok = await client.get("/api/timetable", headers=ph,
                          params={"arm_id": ids["arm_id"]})
    assert ok.status_code == 200
    assert len(ok.json()["lessons"]) == 1

    # a class no child of theirs is in: refused
    denied = await client.get("/api/timetable", headers=ph,
                              params={"arm_id": arm_b})
    assert denied.status_code == 403
    assert "your child" in denied.json()["detail"].lower()

    # and they cannot browse a teacher's personal timetable by passing teacher_id
    peek = await client.get("/api/timetable", headers=ph,
                            params={"teacher_id": ids["teacher_id"]})
    assert peek.status_code == 200
    # the teacher filter is ignored; they still only see their own child's class
    assert all(l["arm_label"] == "JSS1 A" for l in peek.json()["lessons"])


async def test_a_parent_with_no_wards_sees_nothing_rather_than_everything(ctx):
    client, ids = ctx
    from app.core.security import hash_password
    from app.models.school import Role, User
    async with ids["session_factory"]() as db:
        db.add(User(school_id=ids["school_id"], email="nowards@x.ng",
                    hashed_password=hash_password("mama1234"),
                    role=Role.PARENT, first_name="No", last_name="Wards"))
        await db.commit()
    ph = await headers(client, "nowards@x.ng", "mama1234")

    grid = (await client.get("/api/timetable", headers=ph)).json()
    assert grid["wards"] == []
    assert grid["lessons"] == []          # not "every lesson in the school"
    assert (await client.get("/api/my/wards", headers=ph)).json() == []
