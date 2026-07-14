"""Scores must survive a student changing class.

Bug found in production: a student's saved scores disappeared from the entry
grid. Root cause — ScoreEntry stamps the arm_id at entry time, and both the
prefill query and compute() filtered on that stamp. The moment a student was
moved to another arm, their marks were stranded: still in the database, but
invisible to the sheet and excluded from their own result.

A score belongs to (student, subject, term). The arm is derived from the
student, never used as a lookup key.
"""
from tests.conftest import headers


async def _second_arm(client, ah, ids):
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    return (await client.post("/api/academics/arms", headers=ah,
            json={"class_id": class_id, "name": "B"})).json()["id"]


async def test_scores_follow_a_student_who_changes_class(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    student = ids["student_ids"][0]

    # marks entered while the student is in JSS1 A
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": student, "scores": {comp[0]: 9, comp[3]: 61}}]})

    arm_b = await _second_arm(client, ah, ids)
    moved = (await client.post("/api/academics/students/transfer", headers=ah,
             json={"student_ids": [student], "to_arm_id": arm_b})).json()
    assert moved["moved"] == 1

    # the sheet for the NEW class still shows the marks
    shown = (await client.get("/api/scores", headers=ah, params={
        "arm_id": arm_b, "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    mine = {s["component_id"]: s["score"] for s in shown
            if s["student_id"] == student}
    assert mine == {comp[0]: 9, comp[3]: 61}, "the student's marks vanished"

    # and they are gone from the OLD class's sheet, where the student no longer sits
    old = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    assert not [s for s in old if s["student_id"] == student]


async def test_compute_includes_a_transferred_students_marks(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    student = ids["student_ids"][0]

    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": student, "scores": {comp[3]: 70}}]})

    arm_b = await _second_arm(client, ah, ids)
    await client.post("/api/academics/students/transfer", headers=ah,
                      json={"student_ids": [student], "to_arm_id": arm_b})

    # computing the NEW arm must find the student and their marks
    res = (await client.post("/api/results/compute", headers=ah, json={
        "arm_id": arm_b, "term_id": ids["term_id"]})).json()
    assert res["students"] == 1, "the transferred student was skipped entirely"

    report = (await client.get(f"/api/report/{student}", headers=ah,
              params={"term_id": ids["term_id"]})).json()
    assert report["summary"]["grand_total"] == 70


async def test_resaving_after_a_move_updates_rather_than_duplicating(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    student = ids["student_ids"][0]

    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": student, "scores": {comp[0]: 5}}]})

    arm_b = await _second_arm(client, ah, ids)
    await client.post("/api/academics/students/transfer", headers=ah,
                      json={"student_ids": [student], "to_arm_id": arm_b})

    # the teacher corrects the mark from the new class's sheet
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": arm_b,
        "term_id": ids["term_id"],
        "rows": [{"student_id": student, "scores": {comp[0]: 8}}]})

    shown = (await client.get("/api/scores", headers=ah, params={
        "arm_id": arm_b, "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    rows = [s for s in shown if s["student_id"] == student
            and s["component_id"] == comp[0]]
    assert len(rows) == 1, "the move created a duplicate score row"
    assert rows[0]["score"] == 8

    # the correction is audited old -> new, not recorded as a fresh entry
    logs = (await client.get("/api/audit-logs", headers=ah,
            params={"table_name": "score_entries"})).json()
    assert any(l["action"] == "update" and l["changes"]["score"] == {"old": 5, "new": 8}
               for l in logs)
