"""CBT Phase 3 — anti-cheat violations and server-enforced auto-submit."""
from sqlalchemy import select, func

from tests.test_cbt import _teacher, _student_login, _make_exam, _add_questions


async def _proctored_exam(client, ids, hdr, max_violations=3):
    exam = await _make_exam(client, ids, hdr, proctored=True,
                            max_violations=max_violations)
    await _add_questions(client, hdr, exam)
    assert (await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)).status_code == 200
    return exam


async def test_violations_auto_submit_on_the_limit(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _proctored_exam(client, ids, thdr, max_violations=3)
    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    aid = start["attempt_id"]
    assert start["exam"]["proctored"] is True

    # first two violations warn but keep the sitting open
    for n in (1, 2):
        r = (await client.post(f"/api/cbt/attempts/{aid}/violation", headers=shdr,
                               json={"kind": "tab_switch"})).json()
        assert r["count"] == n and r["auto_submit"] is False

    # the third hits the limit → server ends the sitting itself
    r = (await client.post(f"/api/cbt/attempts/{aid}/violation", headers=shdr,
                           json={"kind": "tab_switch"})).json()
    assert r["count"] == 3 and r["auto_submit"] is True

    # the attempt is now submitted (auto), and a further answer/submit is refused
    again = await client.post(f"/api/cbt/attempts/{aid}/submit", headers=shdr,
                              json={"answers": {}})
    assert again.status_code == 409

    # every event was logged for the proctor record
    from app.models.cbt import CBTViolation, CBTAttempt
    async with ids["session_factory"]() as db:
        n = (await db.execute(select(func.count()).select_from(CBTViolation).where(
            CBTViolation.attempt_id == aid))).scalar()
        a = await db.get(CBTAttempt, aid)
    assert n == 3
    assert a.auto_submitted is True and a.status == "submitted"


async def test_violation_on_finished_attempt_is_a_noop(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _proctored_exam(client, ids, thdr)
    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    aid = start["attempt_id"]
    await client.post(f"/api/cbt/attempts/{aid}/submit", headers=shdr, json={"answers": {}})
    r = (await client.post(f"/api/cbt/attempts/{aid}/violation", headers=shdr,
                           json={"kind": "blur"})).json()
    assert r["auto_submit"] is False
