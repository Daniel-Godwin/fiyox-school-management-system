"""Score-sheet ownership — a teacher may only touch the subjects they teach.

This is a security boundary, not a convenience: without it any teacher could
silently rewrite another teacher's exam marks.
"""
import pytest
from tests.conftest import headers


async def _make_teacher(ids, email, first="T", last="Eacher"):
    from app.models.school import User, Role
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        t = User(school_id=ids["school_id"], email=email,
                 hashed_password=hash_password("teach123"),
                 role=Role.TEACHER, first_name=first, last_name=last)
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return t.id


async def _second_subject(client, ah):
    return (await client.post("/api/academics/subjects", headers=ah,
            json={"name": "English Language", "code": "ENG"})).json()["id"]


async def test_teacher_cannot_write_scores_for_a_subject_they_do_not_teach(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    english_id = await _second_subject(client, ah)

    maths_teacher = await _make_teacher(ids, "maths@x.ng", "Musa", "Maths")
    # assigned ONLY to Mathematics in this arm
    await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": maths_teacher, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"]})

    mh = await headers(client, "maths@x.ng", "teach123")
    comp = ids["component_ids"]
    body = {"arm_id": ids["arm_id"], "term_id": ids["term_id"],
            "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 9}}]}

    # their own subject: allowed
    ok = await client.post("/api/scores", headers=mh,
                           json={**body, "subject_id": ids["subject_id"]})
    assert ok.status_code == 200

    # someone else's subject: REFUSED
    denied = await client.post("/api/scores", headers=mh,
                               json={**body, "subject_id": english_id})
    assert denied.status_code == 403
    assert "not assigned" in denied.json()["detail"].lower()

    # and they cannot even READ the other subject's sheet
    peek = await client.get("/api/scores", headers=mh, params={
        "arm_id": ids["arm_id"], "subject_id": english_id,
        "term_id": ids["term_id"]})
    assert peek.status_code == 403


async def test_teacher_cannot_touch_the_same_subject_in_a_class_they_do_not_teach(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # a second arm of the same class
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    arm_b = (await client.post("/api/academics/arms", headers=ah,
             json={"class_id": class_id, "name": "B"})).json()["id"]

    tid = await _make_teacher(ids, "jss1a@x.ng")
    await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": tid, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"]})          # JSS1 A only

    th = await headers(client, "jss1a@x.ng", "teach123")
    comp = ids["component_ids"]
    denied = await client.post("/api/scores", headers=th, json={
        "subject_id": ids["subject_id"], "arm_id": arm_b,
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 10}}]})
    assert denied.status_code == 403


async def test_unassigned_teacher_can_do_nothing_deny_by_default(ctx):
    client, ids = ctx
    await _make_teacher(ids, "new@x.ng")
    nh = await headers(client, "new@x.ng", "teach123")
    comp = ids["component_ids"]

    r = await client.post("/api/scores", headers=nh, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 5}}]})
    assert r.status_code == 403      # no assignments -> no access at all


async def test_admin_is_never_restricted(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    english_id = await _second_subject(client, ah)
    comp = ids["component_ids"]

    # the admin holds no teaching assignment, yet may correct any sheet
    for subject in (ids["subject_id"], english_id):
        r = await client.post("/api/scores", headers=ah, json={
            "subject_id": subject, "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 8}}]})
        assert r.status_code == 200


async def test_altering_another_teachers_mark_is_blocked_and_legitimate_edits_are_audited(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    english_id = await _second_subject(client, ah)
    comp = ids["component_ids"]

    eng_teacher = await _make_teacher(ids, "eng@x.ng", "Ngozi", "English")
    maths_teacher = await _make_teacher(ids, "mth@x.ng", "Musa", "Maths")
    await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": eng_teacher, "subject_id": english_id,
        "arm_id": ids["arm_id"]})
    await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": maths_teacher, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"]})

    # the English teacher records a mark
    eh = await headers(client, "eng@x.ng", "teach123")
    await client.post("/api/scores", headers=eh, json={
        "subject_id": english_id, "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[3]: 65}}]})

    # the Maths teacher tries to inflate it — blocked
    mh = await headers(client, "mth@x.ng", "teach123")
    attack = await client.post("/api/scores", headers=mh, json={
        "subject_id": english_id, "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[3]: 99}}]})
    assert attack.status_code == 403

    # the mark is untouched
    still = (await client.get("/api/scores", headers=eh, params={
        "arm_id": ids["arm_id"], "subject_id": english_id,
        "term_id": ids["term_id"]})).json()
    assert [s["score"] for s in still if s["component_id"] == comp[3]] == [65]

    # when the rightful teacher corrects it, the trail names them
    await client.post("/api/scores", headers=eh, json={
        "subject_id": english_id, "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[3]: 70}}]})
    logs = (await client.get("/api/audit-logs", headers=ah,
            params={"table_name": "score_entries"})).json()
    edit = next(l for l in logs if l["action"] == "update")
    assert edit["changes"]["score"] == {"old": 65, "new": 70}
    assert edit["user_id"] == eng_teacher


async def test_admin_manages_assignments_and_removal_revokes_access(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    tid = await _make_teacher(ids, "temp@x.ng")

    created = (await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": tid, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"]})).json()

    # duplicate assignment refused
    dup = await client.post("/api/users/assignments", headers=ah, json={
        "teacher_id": tid, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"]})
    assert dup.status_code == 409

    th = await headers(client, "temp@x.ng", "teach123")
    comp = ids["component_ids"]
    body = {"subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 7}}]}
    assert (await client.post("/api/scores", headers=th, json=body)).status_code == 200

    # a teacher sees only their own assignments
    mine = (await client.get("/api/users/assignments", headers=th)).json()
    assert len(mine) == 1 and mine[0]["subject_name"] == "Mathematics"

    # teachers cannot assign themselves anything
    assert (await client.post("/api/users/assignments", headers=th, json={
        "teacher_id": tid, "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"]})).status_code == 403

    # revoking the assignment revokes access immediately
    await client.delete(f"/api/users/assignments/{created['id']}", headers=ah)
    assert (await client.post("/api/scores", headers=th, json=body)).status_code == 403
