"""CBT question bank + difficulty balancing (Phase 1)."""
import random

from tests.conftest import headers
from tests.test_cbt import _teacher, _make_exam


# ---- the balancing engine (pure, no HTTP) ----
def test_difficulty_counts_sum_to_pool_size():
    from app.services.cbt import difficulty_counts
    c = difficulty_counts(25, {"easy": 40, "medium": 40, "hard": 20})
    assert c == {"easy": 10, "medium": 10, "hard": 5}
    assert sum(difficulty_counts(50, {"easy": 50, "medium": 30, "hard": 20}).values()) == 50
    # odd ratios still sum exactly, via largest-remainder rounding
    assert sum(difficulty_counts(7, {"easy": 1, "medium": 1, "hard": 1}).values()) == 7


def test_select_balanced_draws_the_right_mix():
    from app.services.cbt import select_balanced

    class Q:
        def __init__(self, i, d): self.id, self.difficulty = i, d
    bank = ([Q(f"e{i}", "easy") for i in range(20)] +
            [Q(f"m{i}", "medium") for i in range(20)] +
            [Q(f"h{i}", "hard") for i in range(20)])
    chosen = select_balanced(bank, 25, {"easy": 40, "medium": 40, "hard": 20},
                             rng=random.Random(1))
    assert len(chosen) == 25
    assert len({q.id for q in chosen}) == 25  # no duplicates
    by = {}
    for q in chosen:
        by[q.difficulty] = by.get(q.difficulty, 0) + 1
    assert by == {"easy": 10, "medium": 10, "hard": 5}


def test_select_backfills_when_a_bucket_is_short():
    from app.services.cbt import select_balanced

    class Q:
        def __init__(self, i, d): self.id, self.difficulty = i, d
    bank = ([Q(f"e{i}", "easy") for i in range(3)] +
            [Q(f"m{i}", "medium") for i in range(20)])
    chosen = select_balanced(bank, 10, {"easy": 40, "medium": 40, "hard": 20},
                             rng=random.Random(2))
    assert len(chosen) == 10  # still a full paper despite no hard questions


# ---- bank API ----
async def _add_bank(client, hdr, ids, difficulty, n, topic="algebra"):
    for i in range(n):
        r = await client.post("/api/cbt/bank", headers=hdr, json={
            "subject_id": ids["subject_id"], "topic": topic,
            "difficulty": difficulty, "type": "single",
            "text": f"{difficulty} Q{i}: 1+{i}?",
            "options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
            "correct": "a", "marks": 1})
        assert r.status_code == 201, r.text


async def test_teacher_builds_and_filters_the_bank(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    await _add_bank(client, hdr, ids, "easy", 4)
    await _add_bank(client, hdr, ids, "medium", 3)
    await _add_bank(client, hdr, ids, "hard", 2)

    # summary counts drive the balancing UI
    s = (await client.get(f"/api/cbt/bank/summary?subject_id={ids['subject_id']}",
                          headers=hdr)).json()
    assert (s["easy"], s["medium"], s["hard"], s["total"]) == (4, 3, 2, 9)

    # filter by difficulty
    hard = (await client.get(
        f"/api/cbt/bank?subject_id={ids['subject_id']}&difficulty=hard",
        headers=hdr)).json()
    assert len(hard) == 2 and all(q["difficulty"] == "hard" for q in hard)


async def test_pool_exam_publish_validates_the_bank(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    exam = await _make_exam(client, ids, hdr, source="pool", pool_size=5,
                            difficulty_ratio={"easy": 40, "medium": 40, "hard": 20})

    # empty bank → cannot publish
    r = await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)
    assert r.status_code == 409

    # enough questions in each difficulty → publishes, sized to the pool
    await _add_bank(client, hdr, ids, "easy", 3)
    await _add_bank(client, hdr, ids, "medium", 3)
    await _add_bank(client, hdr, ids, "hard", 2)
    r = await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["question_count"] == 5


async def test_pool_publishes_from_a_skewed_bank(ctx):
    """A bank heavy in one difficulty still publishes — the per-sitting draw
    backfills across difficulties, so total >= pool_size is enough."""
    client, ids = ctx
    hdr = await _teacher(client)
    exam = await _make_exam(client, ids, hdr, source="pool", pool_size=5,
                            difficulty_ratio={"easy": 40, "medium": 40, "hard": 20})
    # all one difficulty (mirrors a Word import with no [easy]/[hard] tags)
    await _add_bank(client, hdr, ids, "medium", 6)
    r = await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["question_count"] == 5


async def test_fill_manual_exam_from_bank(ctx):
    """A manual (write-my-own) draft test can be filled straight from the bank
    and then published like any other manual test."""
    client, ids = ctx
    hdr = await _teacher(client)
    exam = await _make_exam(client, ids, hdr, source="manual")
    await _add_bank(client, hdr, ids, "easy", 3)
    await _add_bank(client, hdr, ids, "medium", 3)
    await _add_bank(client, hdr, ids, "hard", 2)

    r = await client.post(f"/api/cbt/exams/{exam}/questions/from-bank",
                          headers=hdr, json={"count": 5})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 5

    # the exam now has real attached questions and publishes normally
    detail = (await client.get(f"/api/cbt/exams/{exam}", headers=hdr)).json()
    assert len(detail["questions"]) == 5
    pub = await client.post(f"/api/cbt/exams/{exam}/publish", headers=hdr)
    assert pub.status_code == 200, pub.text
    assert pub.json()["question_count"] == 5


async def test_fill_from_bank_needs_a_stocked_bank(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    exam = await _make_exam(client, ids, hdr, source="manual")
    r = await client.post(f"/api/cbt/exams/{exam}/questions/from-bank",
                          headers=hdr, json={"count": 5})
    assert r.status_code == 409  # empty bank for this subject


async def test_bank_rejects_bad_difficulty(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    r = await client.post("/api/cbt/bank", headers=hdr, json={
        "subject_id": ids["subject_id"], "difficulty": "impossible",
        "type": "single", "text": "x?",
        "options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
        "correct": "a"})
    assert r.status_code == 422


async def test_bank_question_can_be_edited_and_deleted(ctx):
    client, ids = ctx
    hdr = await _teacher(client)
    created = (await client.post("/api/cbt/bank", headers=hdr, json={
        "subject_id": ids["subject_id"], "topic": "algebra", "difficulty": "easy",
        "type": "single", "text": "2+2?",
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
        "correct": "a", "marks": 1})).json()
    qid = created["id"]

    # edit: fix the text, difficulty and correct answer
    r = await client.patch(f"/api/cbt/bank/{qid}", headers=hdr, json={
        "text": "What is 2+2?", "difficulty": "medium", "correct": "b"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "What is 2+2?" and body["difficulty"] == "medium"
    assert body["correct"] == "b"

    # delete
    assert (await client.delete(f"/api/cbt/bank/{qid}", headers=hdr)).status_code == 204
    remaining = (await client.get(
        f"/api/cbt/bank?subject_id={ids['subject_id']}", headers=hdr)).json()
    assert all(q["id"] != qid for q in remaining)
