"""Cumulative annual report — three terms combined into one session result."""
from tests.conftest import headers
from app.models.academics import Term, TermName


async def _enter(client, h, ids, term_id, student_id, totals):
    t1, t2, asg, exam = totals
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"], "term_id": term_id,
        "rows": [{"student_id": student_id, "scores": {
            comp[0]: t1, comp[1]: t2, comp[2]: asg, comp[3]: exam}}]})


async def _make_session(client, ids):
    """Add second and third terms to the seeded session; return the 3 term ids."""
    TestSession = ids["session_factory"]
    async with TestSession() as db:
        first = await db.get(Term, ids["term_id"])
        session_id = first.session_id
        t2 = Term(school_id=ids["school_id"], session_id=session_id, name=TermName.SECOND)
        t3 = Term(school_id=ids["school_id"], session_id=session_id, name=TermName.THIRD)
        db.add(t2); db.add(t3)
        await db.flush()
        ids2 = {"session_id": session_id, "terms": [ids["term_id"], t2.id, t3.id]}
        await db.commit()
    return ids2


async def _full_session(client, h, ids):
    info = await _make_session(client, ids)
    s = ids["student_ids"]
    for term_id in info["terms"]:
        # same totals every term: 80 / 60 / 40 -> averages stay 80 / 60 / 40
        await _enter(client, h, ids, term_id, s[0], (8, 8, 8, 56))   # 80
        await _enter(client, h, ids, term_id, s[1], (6, 6, 6, 42))   # 60
        await _enter(client, h, ids, term_id, s[2], (4, 4, 4, 28))   # 40
        await client.post("/api/results/compute", headers=h,
                          json={"arm_id": ids["arm_id"], "term_id": term_id})
    return info


async def test_annual_broadsheet_cumulative_and_position(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    info = await _full_session(client, h, ids)

    bs = (await client.get("/api/results/annual", headers=h, params={
        "arm_id": ids["arm_id"], "session_id": info["session_id"]})).json()
    assert bs["terms"] == ["First", "Second", "Third"]
    assert bs["class_size"] == 3
    # ordered best-first: 80, 60, 40
    rows = bs["rows"]
    assert [r["cumulative_average"] for r in rows] == [80, 60, 40]
    assert [r["position"] for r in rows] == [1, 2, 3]
    assert rows[0]["per_term"] == [80, 80, 80] and rows[0]["terms_counted"] == 3


async def test_annual_report_json_and_pdf(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    info = await _full_session(client, h, ids)
    top = ids["student_ids"][0]

    rep = (await client.get(f"/api/results/annual/{top}", headers=h, params={
        "session_id": info["session_id"]})).json()
    assert rep["summary"]["cumulative_average"] == 80
    assert rep["summary"]["position"] == 1 and rep["summary"]["class_size"] == 3
    assert rep["summary"]["terms_counted"] == 3
    maths = next(s for s in rep["subjects"] if s["subject"] == "Mathematics")
    assert maths["per_term"] == [80, 80, 80] and maths["cumulative"] == 80
    assert maths["position"] == 1 and maths["grade"]

    pdf = await client.get(f"/api/results/annual/{top}/pdf", headers=h, params={
        "session_id": info["session_id"]})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"


async def test_annual_handles_a_missing_term(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    info = await _make_session(client, ids)
    s = ids["student_ids"]
    # only the first two terms are computed; the third is never entered
    for term_id in info["terms"][:2]:
        await _enter(client, h, ids, term_id, s[0], (8, 8, 8, 56))   # 80 both terms
        await client.post("/api/results/compute", headers=h,
                          json={"arm_id": ids["arm_id"], "term_id": term_id})

    rep = (await client.get(f"/api/results/annual/{s[0]}", headers=h, params={
        "session_id": info["session_id"]})).json()
    # cumulative is the mean of the terms that exist, and the gap shows as null
    assert rep["summary"]["cumulative_average"] == 80
    assert rep["summary"]["terms_counted"] == 2
    assert rep["summary"]["per_term_average"][2] is None


async def test_annual_requires_academic_staff(ctx):
    client, ids = ctx
    # a bursar handles fees, not results — the annual endpoints are closed to them
    oh = await headers(client, "owner@fiyox.ng", "owner123")
    made = await client.post(f"/api/schools/{ids['school_id']}/accounts", headers=oh, json={
        "role": "bursar", "email": "bursar@gss-ikeja.ng", "first_name": "Chika", "last_name": "N"})
    assert made.status_code == 201, made.text
    bh = await headers(client, "bursar@gss-ikeja.ng", made.json()["password"])
    r = await client.get("/api/results/annual", headers=bh, params={
        "arm_id": ids["arm_id"], "session_id": "x"})
    assert r.status_code == 403
