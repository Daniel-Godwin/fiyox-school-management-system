"""Termly class score sheet (broadsheet): the data builder and the PDF endpoint.

A whole class, one term, every student against every subject — the grid a school
pins up or files at term end. It must read the same term snapshots the report
cards do, so the sheet and the cards never disagree.
"""
from tests.conftest import headers
from app.services.broadsheet import build_term_broadsheet


async def _seed_term(client, ids, teacher, admin):
    """Enter marks for every student in the subject, then compute the term."""
    comp = ids["component_ids"]
    arm, subj, term = ids["arm_id"], ids["subject_id"], ids["term_id"]
    students = ids["student_ids"]
    # distinct totals so positions are unambiguous: s0 best, s2 worst
    marks = {students[0]: 10, students[1]: 7, students[2]: 4}
    rows = [{"student_id": s, "scores": {comp[0]: m, comp[1]: m, comp[2]: m, comp[3]: m}}
            for s, m in marks.items()]
    w = (await client.post("/api/scores", headers=teacher, json={
        "subject_id": subj, "arm_id": arm, "term_id": term, "rows": rows})).json()
    assert w["scores_written"] == 12
    await client.post("/api/results/compute", headers=admin,
                      json={"arm_id": arm, "term_id": term})


async def test_builder_grid_matches_the_computed_term(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    teacher = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _seed_term(client, ids, teacher, admin)

    async with ids["session_factory"]() as db:
        data = await build_term_broadsheet(db, ids["school_id"], ids["arm_id"], ids["term_id"])

    # one subject column, three students, all computed
    assert [s["id"] for s in data["subjects"]] == [ids["subject_id"]]
    assert data["class_size"] == 3 and data["computed_count"] == 3
    # ranked best-first: the student with the top marks sits at position 1
    assert data["rows"][0]["position"] == 1
    assert data["rows"][0]["student_id"] == ids["student_ids"][0]
    # each row carries one score cell (the single subject) and an overall average
    for r in data["rows"]:
        assert len(r["scores"]) == 1
        assert r["average"] is not None and r["grade"]
    # the class-average footer is present
    assert data["class_average"] is not None


async def test_score_sheet_pdf_endpoint(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    teacher = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await _seed_term(client, ids, teacher, admin)
    arm, term = ids["arm_id"], ids["term_id"]

    # a teacher may print their class's sheet
    pdf = await client.get("/api/score-sheet.pdf", headers=teacher,
                           params={"arm_id": arm, "term_id": term})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert len(pdf.content) > 1000          # a real PDF, not an empty stub


async def test_score_sheet_404_when_no_results(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    # nothing computed yet for this arm/term
    r = await client.get("/api/score-sheet.pdf", headers=admin,
                         params={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    assert r.status_code == 404
