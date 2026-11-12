"""CBT Phase 4 — live proctor dashboard (monitor, extend, force-submit)."""
from tests.test_cbt import _teacher, _student_login, _make_exam, _add_questions


async def _live_exam(client, ids, thdr):
    exam = await _make_exam(client, ids, thdr)
    await _add_questions(client, thdr, exam)
    assert (await client.post(f"/api/cbt/exams/{exam}/publish", headers=thdr)).status_code == 200
    return exam


async def test_monitor_shows_progress_and_controls_work(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _live_exam(client, ids, thdr)

    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    aid = start["attempt_id"]
    qid = start["questions"][0]["id"]
    await client.post(f"/api/cbt/attempts/{aid}/answer", headers=shdr,
                      json={"answers": {qid: "b"}})

    mon = (await client.get(f"/api/cbt/exams/{exam}/monitor", headers=thdr)).json()
    assert mon["counts"]["in_progress"] >= 1
    me = next(r for r in mon["students"] if r["attempt_id"] == aid)
    assert me["status"] == "in_progress"
    assert me["answered"] >= 1 and me["total"] >= 1 and me["remaining"] is not None

    # extend time
    assert (await client.post(f"/api/cbt/attempts/{aid}/extend", headers=thdr,
                              json={"minutes": 10})).status_code == 200

    # force-submit ends the sitting
    fs = await client.post(f"/api/cbt/attempts/{aid}/force-submit", headers=thdr)
    assert fs.status_code == 200 and fs.json()["status"] == "submitted"
    # the student can no longer submit it themselves
    assert (await client.post(f"/api/cbt/attempts/{aid}/submit", headers=shdr,
                              json={"answers": {}})).status_code == 409

    # monitor now reflects the submission
    mon2 = (await client.get(f"/api/cbt/exams/{exam}/monitor", headers=thdr)).json()
    assert mon2["counts"]["submitted"] >= 1


async def test_students_cannot_open_the_monitor(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _live_exam(client, ids, thdr)
    shdr = await _student_login(client, ids, 0)
    assert (await client.get(f"/api/cbt/exams/{exam}/monitor", headers=shdr)).status_code == 403


async def test_force_submit_on_finished_attempt_is_409(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _live_exam(client, ids, thdr)
    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    aid = start["attempt_id"]
    await client.post(f"/api/cbt/attempts/{aid}/submit", headers=shdr, json={"answers": {}})
    assert (await client.post(f"/api/cbt/attempts/{aid}/force-submit",
                              headers=thdr)).status_code == 409
