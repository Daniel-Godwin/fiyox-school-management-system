"""End-to-end pilot dry-run: one full term through every module that matters.

Enrol (seeded) -> CBT sitting -> score entry -> preview -> attendance ->
approval workflow (submit -> reject -> fix -> resubmit -> approve -> publish)
-> report card + PDF -> fees (invoice -> payment -> receipt). This is the
integration guard for the whole pilot flow.
"""
from tests.conftest import headers
from tests.test_cbt import _teacher, _student_login, _make_exam


async def test_full_term_flow(ctx):
    client, ids = ctx
    comp = ids["component_ids"]                      # [Test1, Test2, Assignment, Exam]
    arm, subj, term = ids["arm_id"], ids["subject_id"], ids["term_id"]
    students = ids["student_ids"]
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    teacher = await headers(client, "teacher@gss-ikeja.ng", "teach123")

    # 1) CBT test tied to the Exam column; student 0 scores 100%
    exam = await _make_exam(client, ids, teacher, component_id=comp[3])
    await client.post(f"/api/cbt/exams/{exam}/questions", headers=teacher, json={
        "type": "single", "text": "2+2?", "marks": 1,
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}], "correct": "b"})
    assert (await client.post(f"/api/cbt/exams/{exam}/publish", headers=teacher)).status_code == 200
    shdr = await _student_login(client, ids, 0)
    start = (await client.post(f"/api/cbt/exams/{exam}/start", headers=shdr)).json()
    sub = (await client.post(f"/api/cbt/attempts/{start['attempt_id']}/submit", headers=shdr,
           json={"answers": {start["questions"][0]["id"]: "b"}})).json()
    assert sub["recorded_to_results"] is True

    # 2) manual marks (Test 1/2/Assignment) for every student
    rows = [{"student_id": s, "scores": {comp[0]: 8, comp[1]: 7, comp[2]: 9}} for s in students]
    w = (await client.post("/api/scores", headers=teacher, json={
        "subject_id": subj, "arm_id": arm, "term_id": term, "rows": rows})).json()
    assert w["scores_written"] == 9                 # 3 students x 3 components

    # 3) preview/verify: student 0 has the CBT Exam mark + 3 manual, nothing missing
    prev = (await client.get("/api/scores/preview", headers=teacher, params={
        "arm_id": arm, "subject_id": subj, "term_id": term})).json()
    s0 = next(s for s in prev["students"] if s["student_id"] == students[0])
    assert s0["scores"][comp[3]] == 70 and s0["total"] == 94 and not s0["missing"]

    # 4) attendance for the day
    att = (await client.post("/api/attendance/mark", headers=teacher, json={
        "arm_id": arm, "date": "2026-10-20",
        "records": [{"student_id": s, "status": "present"} for s in students]})).json()
    assert att

    # 5) approval workflow: enable the gate, compute, submit -> reject -> fix -> resubmit -> approve -> publish
    await client.patch("/api/schools/me", headers=admin, json={"result_approval_required": True})
    await client.post("/api/results/compute", headers=admin, json={"arm_id": arm, "term_id": term})
    assert (await client.post("/api/results/submit", headers=teacher, json={
        "arm_id": arm, "term_id": term})).json()["submitted"] == 3
    await client.post(f"/api/results/return?arm_id={arm}&term_id={term}", headers=admin,
                      json={"form_teacher_comment": "Recheck the Assignment column"})
    # rejected result is NOT locked — teacher corrects a mark
    fix = (await client.post("/api/scores", headers=teacher, json={
        "subject_id": subj, "arm_id": arm, "term_id": term,
        "rows": [{"student_id": students[0], "scores": {comp[2]: 10}}]})).json()
    assert fix["scores_written"] == 1
    await client.post("/api/results/compute", headers=admin, json={"arm_id": arm, "term_id": term})
    assert (await client.post("/api/results/submit", headers=teacher, json={
        "arm_id": arm, "term_id": term})).json()["submitted"] == 3
    assert (await client.post("/api/results/approve", headers=admin, json={
        "arm_id": arm, "term_id": term})).json()["approved"] == 3
    pub = (await client.post("/api/results/publish", headers=admin, json={
        "arm_id": arm, "term_id": term})).json()
    assert pub["published"] == 3 and pub["blocked_unapproved"] == 0

    # 6) post-approval lock: the teacher can no longer change an approved mark
    locked = (await client.post("/api/scores", headers=teacher, json={
        "subject_id": subj, "arm_id": arm, "term_id": term,
        "rows": [{"student_id": students[0], "scores": {comp[0]: 5}}]})).json()
    assert locked["scores_written"] == 0 and locked.get("locked_skipped") == 1

    # 7) report card + PDF reflect the final marks (70 + 8 + 7 + 10 = 95)
    rep = (await client.get(f"/api/report/{students[0]}", headers=admin,
                            params={"term_id": term})).json()
    assert rep["summary"]["grand_total"] == 95
    pdf = await client.get(f"/api/report/{students[0]}/pdf", headers=admin,
                           params={"term_id": term})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert len(pdf.content) > 1000                  # a real PDF, not an empty stub

    # 8) fees: structure -> invoice -> payment -> receipt
    cat = (await client.post("/api/fees/categories", headers=admin,
                             json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        class_id = (await db.get(ClassArm, arm)).class_id
    await client.post("/api/fees/structures", headers=admin, json={
        "class_id": class_id, "term_id": term, "category_id": cat["id"], "amount": 30000})
    gen = (await client.post("/api/fees/invoices/generate", headers=admin, json={
        "arm_id": arm, "term_id": term})).json()
    assert gen["created"] == 3
    inv = (await client.get("/api/fees/invoices", headers=admin,
                            params={"student_id": students[0]})).json()[0]
    pay = (await client.post("/api/fees/payments", headers=admin, json={
        "invoice_id": inv["id"], "method": "cash", "reference": "E2E-1",
        "amount": 30000})).json()
    assert pay["invoice"]["status"] == "paid"
    pid = pay.get("payment_id") or pay.get("id")
    receipt = await client.get(f"/api/fees/payments/{pid}/receipt", headers=admin)
    assert receipt.status_code == 200
