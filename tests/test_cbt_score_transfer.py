"""CBT scores must land in the right result-sheet column and reach the report.

Regression cover for the reported "CBT shows 0 in Score Entry" issue: the
pipeline works when the test is tied to a column, and sitting-before-linking
is recoverable with /sync-scores (instead of being stuck at 0).
"""
from tests.test_cbt import _teacher, _admin, _student_login, _make_exam


async def _one_q_exam(client, ids, hdr, **ov):
    exam = await _make_exam(client, ids, hdr, **ov)
    await client.post(f"/api/cbt/exams/{exam}/questions", headers=hdr, json={
        "type": "single", "text": "2+2?", "marks": 1,
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
        "correct": "b"})
    assert (await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)).status_code == 200
    return exam


async def _sit(client, ids, exam, idx=0, answer="b"):
    shdr = await _student_login(client, ids, idx)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    qid = start["questions"][0]["id"]
    return (await client.post(f"/api/cbt/attempts/{start['attempt_id']}/submit",
                              headers=shdr, json={"answers": {qid: answer}})).json()


async def test_linked_cbt_lands_in_the_right_column_and_report(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    comp = ids["component_ids"]        # [Test1, Test2, Assignment, Exam]
    stu = ids["student_ids"][0]
    exam = await _one_q_exam(client, ids, thdr, component_id=comp[0])  # 1st Test

    sub = await _sit(client, ids, exam, 0, "b")
    assert sub["recorded_to_results"] is True

    ah = await _admin(client)
    scores = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    mine = {s["component_id"]: s["score"] for s in scores if s["student_id"] == stu}
    assert mine.get(comp[0]) == 10          # 100% of a 10-mark Test 1
    assert comp[3] not in mine               # nothing leaked into the Exam column


async def test_unlinked_sitting_is_recoverable_with_sync(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    comp = ids["component_ids"]
    stu = ids["student_ids"][0]

    # sat with NO column linked -> score not written (the reported 0)
    exam = await _one_q_exam(client, ids, thdr)
    sub = await _sit(client, ids, exam, 0, "b")
    assert sub["recorded_to_results"] is False

    ah = await _admin(client)
    before = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    assert not [s for s in before if s["student_id"] == stu]

    # syncing before linking is refused with guidance
    assert (await client.post(f"/api/cbt/exams/{exam}/sync-scores",
                              headers=thdr)).status_code == 409

    # link the column, then sync -> the earlier sitting is recovered
    await client.patch(f"/api/cbt/exams/{exam}", headers=thdr,
                       json={"component_id": comp[3]})
    r = (await client.post(f"/api/cbt/exams/{exam}/sync-scores", headers=thdr)).json()
    assert r["recorded"] == 1

    after = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    mine = {s["component_id"]: s["score"] for s in after if s["student_id"] == stu}
    assert mine.get(comp[3]) == 70

    # idempotent — running again doesn't duplicate or change anything
    again = (await client.post(f"/api/cbt/exams/{exam}/sync-scores", headers=thdr)).json()
    assert again["recorded"] == 1
    after2 = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    assert len([s for s in after2 if s["student_id"] == stu
                and s["component_id"] == comp[3]]) == 1
