"""Computer-Based Testing — authoring, publishing, sitting and auto-grading.

Covers the three audiences: a teacher authors and publishes a test for the
class they teach; a student sits it and is graded instantly; admin/principal
read the result table. Also pins down the guard rails (empty publish, attempt
limit, role restrictions, answer key never leaking to a sitting student).
"""
from sqlalchemy import select

from app.core.security import hash_password
from app.models.school import User, Role
from app.models.student import Student
from tests.conftest import headers


async def _teacher(client):
    return await headers(client, "teacher@gss-ikeja.ng", "teach123")


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def _student_login(client, ids, idx=0, email=None):
    """Attach a login account to the idx-th seeded student and sign in."""
    email = email or f"student{idx}@gss.ng"
    TestSession = ids["session_factory"]
    async with TestSession() as db:
        st = await db.get(Student, ids["student_ids"][idx])
        u = User(school_id=ids["school_id"], email=email,
                 hashed_password=hash_password("study123"), role=Role.STUDENT,
                 first_name=st.first_name, last_name=st.last_name)
        db.add(u)
        await db.flush()
        st.user_id = u.id
        await db.commit()
    return await headers(client, email, "study123")


async def _make_exam(client, ids, hdr, **overrides):
    payload = {
        "title": "Maths quiz 1", "subject_id": ids["subject_id"],
        "arm_id": ids["arm_id"], "term_id": ids["term_id"],
        "duration_minutes": 20, "max_attempts": 1,
    }
    payload.update(overrides)
    r = await client.post("/api/cbt/exams", headers=hdr, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _add_questions(client, hdr, exam_id):
    """Add one of each type; return {label: question_id}."""
    qs = {
        "single": {"type": "single", "text": "2 + 2 = ?", "marks": 2,
                   "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
                   "correct": "b"},
        "boolean": {"type": "boolean", "text": "The earth orbits the sun.",
                    "marks": 1, "correct": True},
        "short": {"type": "short", "text": "Spell the number 8.",
                  "marks": 1, "correct": ["eight", "8"]},
        "multiple": {"type": "multiple", "text": "Pick the even numbers.", "marks": 2,
                     "options": [{"id": "a", "text": "2"}, {"id": "b", "text": "3"},
                                 {"id": "c", "text": "4"}],
                     "correct": ["a", "c"]},
    }
    ids_map = {}
    for label, body in qs.items():
        r = await client.post(f"/api/cbt/exams/{exam_id}/questions", headers=hdr, json=body)
        assert r.status_code == 201, r.text
        ids_map[label] = r.json()["id"]
    return ids_map


# ------------------------------------------------------------------
async def test_teacher_authors_and_publishes(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    await _add_questions(client, th, exam_id)

    r = await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "published"
    assert body["question_count"] == 4
    assert body["total_marks"] == 6  # 2 + 1 + 1 + 2
    # it shows up with a readable subject + class label
    lst = (await client.get("/api/cbt/exams", headers=th)).json()
    row = next(e for e in lst if e["id"] == exam_id)
    assert row["subject_name"] == "Mathematics" and row["class_label"] == "JSS1 A"


async def test_cannot_publish_without_questions(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    r = await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)
    assert r.status_code == 409


async def test_questions_frozen_once_published(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)
    # adding a question to a live exam is refused
    r = await client.post(f"/api/cbt/exams/{exam_id}/questions", headers=th, json={
        "type": "boolean", "text": "late add", "correct": True, "marks": 1})
    assert r.status_code == 409


async def test_student_sits_and_is_graded_full_marks(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    qmap = await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    sh = await _student_login(client, ids)
    # the test is listed as available and open
    avail = (await client.get("/api/cbt/available", headers=sh)).json()
    assert any(e["id"] == exam_id and e["open_now"] and e["can_start"] for e in avail)

    start = (await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)).json()
    attempt_id = start["attempt_id"]
    assert len(start["questions"]) == 4
    # the answer key must never reach the sitting student
    assert all("correct" not in q for q in start["questions"])
    # boolean question carries synthesised True/False options
    bq = next(q for q in start["questions"] if q["id"] == qmap["boolean"])
    assert {o["id"] for o in bq["options"]} == {"true", "false"}

    answers = {
        qmap["single"]: "b",
        qmap["boolean"]: "true",
        qmap["short"]: "  Eight ",   # case/space-insensitive
        qmap["multiple"]: ["c", "a"],  # order-insensitive
    }
    r = await client.post(f"/api/cbt/attempts/{attempt_id}/submit", headers=sh,
                          json={"answers": answers})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score"] == 6 and body["max_score"] == 6 and body["percent"] == 100


async def test_grading_is_all_or_nothing_and_partial(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    qmap = await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    sh = await _student_login(client, ids)
    attempt_id = (await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)).json()["attempt_id"]
    answers = {
        qmap["single"]: "a",          # wrong (0 of 2)
        qmap["boolean"]: "true",      # right (1)
        qmap["short"]: "eight",       # right (1)
        qmap["multiple"]: ["a"],      # incomplete -> 0 of 2 (all-or-nothing)
    }
    body = (await client.post(f"/api/cbt/attempts/{attempt_id}/submit", headers=sh,
                              json={"answers": answers})).json()
    assert body["score"] == 2 and body["max_score"] == 6


async def test_attempt_limit_enforced(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th, max_attempts=1)
    await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    sh = await _student_login(client, ids)
    a1 = (await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)).json()["attempt_id"]
    await client.post(f"/api/cbt/attempts/{a1}/submit", headers=sh, json={"answers": {}})
    # one attempt only — a second start is refused
    r = await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)
    assert r.status_code == 409


async def test_students_cannot_author(ctx):
    client, ids = ctx
    sh = await _student_login(client, ids)
    r = await client.post("/api/cbt/exams", headers=sh, json={
        "title": "x", "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"]})
    assert r.status_code == 403


async def test_student_only_sees_own_class_exams(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    # move this student into a different (freshly made) arm, then they should
    # no longer see the JSS1 A exam
    TestSession = ids["session_factory"]
    from app.models.academics import ClassArm, SchoolClass, ClassCategory
    async with TestSession() as db:
        cls = (await db.execute(select(SchoolClass).where(
            SchoolClass.school_id == ids["school_id"]))).scalars().first()
        other = ClassArm(school_id=ids["school_id"], class_id=cls.id, name="B")
        db.add(other)
        await db.flush()
        st = await db.get(Student, ids["student_ids"][0])
        st.current_arm_id = other.id
        await db.commit()

    sh = await _student_login(client, ids)
    avail = (await client.get("/api/cbt/available", headers=sh)).json()
    assert all(e["id"] != exam_id for e in avail)
    # and a direct start is refused
    r = await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)
    assert r.status_code == 403


async def _score_entry(ids, student_id, component_id):
    """Read a student's ScoreEntry for a component straight from the DB."""
    from app.models.results import ScoreEntry
    TestSession = ids["session_factory"]
    async with TestSession() as db:
        return (await db.execute(select(ScoreEntry).where(
            ScoreEntry.student_id == student_id,
            ScoreEntry.component_id == component_id))).scalars().first()


async def test_cbt_records_scaled_score_to_result_sheet(ctx):
    client, ids = ctx
    th = await _teacher(client)
    comp_id = ids["component_ids"][0]          # "Test 1", max 10
    exam_id = await _make_exam(client, ids, th, component_id=comp_id)
    qmap = await _add_questions(client, th, exam_id)   # total 6 marks
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    sh = await _student_login(client, ids)
    attempt = (await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)).json()["attempt_id"]
    # 4 of 6 marks: single wrong, boolean right, short right, multiple incomplete
    answers = {qmap["single"]: "a", qmap["boolean"]: "true",
               qmap["short"]: "eight", qmap["multiple"]: ["a"]}
    body = (await client.post(f"/api/cbt/attempts/{attempt}/submit", headers=sh,
                              json={"answers": answers})).json()
    assert body["recorded_to_results"] is True
    assert body["score"] == 2  # 4 of 6... single(0)+bool(1)+short(1)+multi(0)=2

    # 2/6 = 33.3% of a 10-mark column -> 3.33
    se = await _score_entry(ids, ids["student_ids"][0], comp_id)
    assert se is not None
    assert se.score == round((2 / 6) * 10, 2)   # 3.33


async def test_practice_cbt_does_not_touch_result_sheet(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)     # no component -> practice
    await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    sh = await _student_login(client, ids)
    attempt = (await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)).json()["attempt_id"]
    body = (await client.post(f"/api/cbt/attempts/{attempt}/submit", headers=sh,
                              json={"answers": {}})).json()
    assert body["recorded_to_results"] is False
    se = await _score_entry(ids, ids["student_ids"][0], ids["component_ids"][0])
    assert se is None


async def test_unknown_component_rejected(ctx):
    client, ids = ctx
    th = await _teacher(client)
    r = await client.post("/api/cbt/exams", headers=th, json={
        "title": "x", "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"], "component_id": "does-not-exist"})
    assert r.status_code == 422


async def test_admin_sees_results_table(ctx):
    client, ids = ctx
    th = await _teacher(client)
    exam_id = await _make_exam(client, ids, th)
    qmap = await _add_questions(client, th, exam_id)
    await client.post(f"/api/cbt/exams/{exam_id}/publish", headers=th)

    sh = await _student_login(client, ids)
    a = (await client.post(f"/api/cbt/exams/{exam_id}/start", headers=sh)).json()["attempt_id"]
    await client.post(f"/api/cbt/attempts/{a}/submit", headers=sh,
                      json={"answers": {qmap["single"]: "b"}})

    ah = await _admin(client)
    res = (await client.get(f"/api/cbt/exams/{exam_id}/results", headers=ah)).json()
    assert res["submitted"] == 1
    assert res["rows"][0]["score"] == 2 and res["rows"][0]["max_score"] == 6
    assert res["average_percent"] is not None
