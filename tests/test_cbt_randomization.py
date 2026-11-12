"""CBT Phase 2 — per-attempt randomization, option shuffling, stable resume."""
from tests.test_cbt import _teacher, _student_login, _make_exam
from tests.test_cbt_bank import _add_bank


async def _published_pool_exam(client, ids, hdr, pool_size=5):
    exam = await _make_exam(client, ids, hdr, source="pool", pool_size=pool_size,
                            difficulty_ratio={"easy": 40, "medium": 40, "hard": 20})
    await _add_bank(client, hdr, ids, "easy", 4)
    await _add_bank(client, hdr, ids, "medium", 4)
    await _add_bank(client, hdr, ids, "hard", 3)
    r = await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)
    assert r.status_code == 200, r.text
    return exam


async def test_pool_sitting_draws_balanced_set_and_grades(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _published_pool_exam(client, ids, thdr, pool_size=5)

    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    qs = start["questions"]
    assert len(qs) == 5                       # drew exactly the pool size
    assert len({q["id"] for q in qs}) == 5    # all distinct
    assert all("correct" not in q for q in qs)  # answer key never leaks

    # every bank question's correct option is "a" (a stable id), so answering "a"
    # scores full marks regardless of the shuffled display order
    answers = {q["id"]: "a" for q in qs}
    res = (await client.post(f"/api/cbt/attempts/{start['attempt_id']}/submit",
                             headers=shdr, json={"answers": answers})).json()
    assert res["score"] == res["max_score"] and res["percent"] == 100


async def test_attempt_order_is_stable_across_resume(ctx):
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _published_pool_exam(client, ids, thdr, pool_size=5)
    shdr = await _student_login(client, ids, 0)

    first = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    order1 = [q["id"] for q in first["questions"]]
    opts1 = {q["id"]: [o["id"] for o in q["options"]] for q in first["questions"]}

    # re-opening (refresh / device switch) returns the same frozen set + order
    again = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    assert again["attempt_id"] == first["attempt_id"]
    order2 = [q["id"] for q in again["questions"]]
    opts2 = {q["id"]: [o["id"] for o in q["options"]] for q in again["questions"]}
    assert order2 == order1
    assert opts2 == opts1


async def test_manual_exam_sitting_still_works(ctx):
    """The manual-exam path is unchanged by the pool work."""
    from tests.test_cbt import _add_questions
    client, ids = ctx
    thdr = await _teacher(client)
    exam = await _make_exam(client, ids, thdr)
    await _add_questions(client, thdr, exam)
    assert (await client.post(f"/api/cbt/exams/{exam}/publish", headers=thdr)).status_code == 200

    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    assert len(start["questions"]) == 4
