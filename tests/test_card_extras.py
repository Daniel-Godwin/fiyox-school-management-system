"""Report-card additions: grading key and third-term promotion outcome."""
from tests.conftest import headers
from app.models.academics import Term, TermName, SchoolClass, ClassArm, ClassCategory

ORDER = {"first": 1, "second": 2, "third": 3}


async def _enter(client, h, ids, term_id, student_id, totals):
    c = ids["component_ids"]
    await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"], "term_id": term_id,
        "rows": [{"student_id": student_id, "scores": {
            c[0]: totals[0], c[1]: totals[1], c[2]: totals[2], c[3]: totals[3]}}]})


async def _session_with_next_class(ids):
    """Add second/third terms and a JSS2 class above JSS1; return the term ids."""
    TS = ids["session_factory"]
    async with TS() as db:
        first = await db.get(Term, ids["term_id"])
        sid = first.session_id
        db.add(Term(school_id=ids["school_id"], session_id=sid, name=TermName.SECOND))
        db.add(Term(school_id=ids["school_id"], session_id=sid, name=TermName.THIRD))
        jss2 = SchoolClass(school_id=ids["school_id"], name="JSS2",
                           category=ClassCategory.JUNIOR, level_order=2)
        db.add(jss2)
        await db.flush()
        db.add(ClassArm(school_id=ids["school_id"], class_id=jss2.id, name="A"))
        from sqlalchemy import select
        terms = (await db.execute(select(Term).where(Term.session_id == sid))).scalars().all()
        terms.sort(key=lambda t: ORDER.get(str(getattr(t.name, "value", t.name)), 9))
        out = {"session_id": sid, "terms": [t.id for t in terms]}
        await db.commit()
    return out


async def test_report_carries_grading_key(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _enter(client, h, ids, ids["term_id"], ids["student_ids"][0], (8, 8, 8, 56))
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    rep = (await client.get(f"/api/report/{ids['student_ids'][0]}", headers=h,
                            params={"term_id": ids["term_id"]})).json()
    key = rep["grading_key"]
    assert key and key[0]["max"] == 100            # highest band tops out at 100
    assert all({"grade", "min", "max", "remark"} <= set(k) for k in key)


async def test_third_term_promotion_outcome(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    info = await _session_with_next_class(ids)
    s = ids["student_ids"]
    for term_id in info["terms"]:
        await _enter(client, h, ids, term_id, s[0], (8, 8, 8, 56))    # 80 -> promote
        await _enter(client, h, ids, term_id, s[1], (2, 2, 2, 10))    # 16 -> repeat
        await client.post("/api/results/compute", headers=h,
                          json={"arm_id": ids["arm_id"], "term_id": term_id})
    third = info["terms"][2]

    top = (await client.get(f"/api/report/{s[0]}", headers=h, params={"term_id": third})).json()
    assert top["cumulative"]["promotion"]["action"] == "promote"
    assert top["cumulative"]["promotion"]["label"] == "Promoted to JSS2"

    low = (await client.get(f"/api/report/{s[1]}", headers=h, params={"term_id": third})).json()
    assert low["cumulative"]["promotion"]["action"] == "repeat"
    assert "repeat" in low["cumulative"]["promotion"]["label"].lower()

    # the first-term card carries no cumulative/promotion block
    first = (await client.get(f"/api/report/{s[0]}", headers=h,
                              params={"term_id": info["terms"][0]})).json()
    assert first["cumulative"] is None
