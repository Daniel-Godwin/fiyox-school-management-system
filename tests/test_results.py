"""Result engine — the correctness the product's credibility depends on.

Scores are chosen so totals are exact and known: 80, 60, 40 across three
students, letting us assert grades and positions precisely.
"""
from tests.conftest import headers


async def _enter(client, h, ids, student_id, totals):
    """totals = (test1, test2, assignment, exam)."""
    t1, t2, asg, exam = totals
    comp = ids["component_ids"]  # order: Test 1, Test 2, Assignment, Exam
    scores = {comp[0]: t1, comp[1]: t2, comp[2]: asg, comp[3]: exam}
    r = await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": student_id, "scores": scores}]})
    assert r.status_code == 200


async def _seed_scores(client, h, ids):
    s = ids["student_ids"]
    await _enter(client, h, ids, s[0], (8, 8, 8, 56))    # total 80
    await _enter(client, h, ids, s[1], (6, 6, 6, 42))    # total 60
    await _enter(client, h, ids, s[2], (4, 4, 4, 28))    # total 40


async def test_compute_totals_grades_positions(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _seed_scores(client, h, ids)

    res = (await client.post("/api/results/compute", headers=h,
           json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert res["students"] == 3 and res["subjects"] == 1
    assert "class_average" in res      # compute now also reports the class mean

    # top student: total 80 -> A1, position 1
    top = (await client.get(f"/api/report/{ids['student_ids'][0]}",
           headers=h, params={"term_id": ids["term_id"]})).json()
    assert top["summary"]["grand_total"] == 80
    assert top["summary"]["position"] == 1
    assert top["summary"]["class_size"] == 3
    assert top["subjects"][0]["grade"] == "A1"

    # middle student: total 60 -> C4, position 2
    mid = (await client.get(f"/api/report/{ids['student_ids'][1]}",
           headers=h, params={"term_id": ids["term_id"]})).json()
    assert mid["summary"]["grand_total"] == 60
    assert mid["summary"]["position"] == 2
    assert mid["subjects"][0]["grade"] == "C4"

    # class average for the subject = (80+60+40)/3 = 60
    assert top["subjects"][0]["class_average"] == 60.0


async def test_publish_gate_hides_from_parent_until_published(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _seed_scores(client, h, ids)
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    rep = (await client.get(f"/api/report/{ids['student_ids'][0]}",
           headers=h, params={"term_id": ids["term_id"]})).json()
    # freshly computed results start unpublished
    assert rep["published"] is False


async def test_report_pdf_downloads(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _seed_scores(client, h, ids)
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    r = await client.get(f"/api/report/{ids['student_ids'][0]}/pdf",
                         headers=h, params={"term_id": ids["term_id"]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
