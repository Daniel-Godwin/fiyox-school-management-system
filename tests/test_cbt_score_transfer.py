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


async def test_best_attempt_counts_not_the_last(ctx):
    """A good sitting then a 0-scoring retake must record the BEST (not the last),
    both live and on sync — the exact 'CBT shows 0' case from a double auto-submit.
    """
    client, ids = ctx
    thdr = await _teacher(client)
    comp = ids["component_ids"]
    stu = ids["student_ids"][0]
    # allow 2 attempts so a student can sit twice
    exam = await _make_exam(client, ids, thdr, component_id=comp[3], max_attempts=2)
    await client.post(f"/api/cbt/exams/{exam}/questions", headers=thdr, json={
        "type": "single", "text": "2+2?", "marks": 1,
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}], "correct": "b"})
    assert (await client.post(f"/api/cbt/exams/{exam}/publish", headers=thdr)).status_code == 200

    shdr = await _student_login(client, ids, 0)
    # attempt 1: correct -> 100%
    s1 = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    await client.post(f"/api/cbt/attempts/{s1['attempt_id']}/submit", headers=shdr,
                      json={"answers": {s1['questions'][0]['id']: "b"}})
    # attempt 2: wrong -> 0% (mimics a second auto-submitted sitting)
    s2 = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    await client.post(f"/api/cbt/attempts/{s2['attempt_id']}/submit", headers=shdr,
                      json={"answers": {s2['questions'][0]['id']: "a"}})

    ah = await _admin(client)
    scores = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    mine = {s["component_id"]: s["score"] for s in scores if s["student_id"] == stu}
    assert mine.get(comp[3]) == 70, f"best attempt should win, got {mine}"

    # sync must also keep the best, not overwrite with the 0 sitting
    r = (await client.post(f"/api/cbt/exams/{exam}/sync-scores", headers=thdr)).json()
    assert r["recorded"] == 1
    scores2 = (await client.get("/api/scores", headers=ah, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    mine2 = {s["component_id"]: s["score"] for s in scores2 if s["student_id"] == stu}
    assert mine2.get(comp[3]) == 70


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
