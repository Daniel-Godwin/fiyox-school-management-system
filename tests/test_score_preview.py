"""Teacher score preview — verify marks (incl. CBT) and spot gaps before submit."""
from tests.conftest import headers
from tests.test_cbt import _teacher, _student_login, _make_exam


async def test_preview_shows_totals_missing_and_cbt_backed(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]          # [Test1, Test2, Assignment, Exam]
    stu = ids["student_ids"][0]

    # a manual mark in Test 1 only (the rest are missing)
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": stu, "scores": {comp[0]: 8}}]})

    # a CBT test tied to the Exam column, sat by the same student
    thdr = await _teacher(client)
    exam = await _make_exam(client, ids, thdr, component_id=comp[3])
    await client.post(f"/api/cbt/exams/{exam}/questions", headers=thdr, json={
        "type": "single", "text": "2+2?", "marks": 1,
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}], "correct": "b"})
    await client.post(f"/api/cbt/exams/{exam}/publish", headers=thdr)
    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    await client.post(f"/api/cbt/attempts/{start['attempt_id']}/submit",
                      headers=shdr, json={"answers": {start["questions"][0]["id"]: "b"}})

    prev = (await client.get("/api/scores/preview", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()

    # the Exam column is flagged as auto-filled from CBT
    cbt_flags = {c["id"]: c["cbt_backed"] for c in prev["components"]}
    assert cbt_flags[comp[3]] is True and cbt_flags[comp[0]] is False

    mine = next(s for s in prev["students"] if s["student_id"] == stu)
    assert mine["scores"][comp[0]] == 8          # manual
    assert mine["scores"][comp[3]] == 70          # from CBT (100% of 70)
    assert mine["total"] == 78
    # Test 2 and Assignment were never entered -> flagged missing
    assert comp[1] in mine["missing"] and comp[2] in mine["missing"]
    assert comp[0] not in mine["missing"]
