"""Report-card upgrades: class spread, cumulative session result, comment
bank, and configurable affective traits."""
from tests.conftest import headers


async def _enter(client, h, ids, student_id, exam):
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": student_id, "scores": {comp[3]: exam}}]})


# ------------------------------------------------ highest / lowest per subject

async def test_class_highest_and_lowest_are_computed_and_on_the_report(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    s = ids["student_ids"]
    await _enter(client, h, ids, s[0], 80)
    await _enter(client, h, ids, s[1], 60)
    await _enter(client, h, ids, s[2], 40)
    await client.post("/api/results/compute", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # publish so we can read the report for the top student
    await client.post("/api/results/publish", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    rep = (await client.get(f"/api/report/{s[1]}", headers=h,
           params={"term_id": ids["term_id"]})).json()
    maths = rep["subjects"][0]
    assert maths["class_highest"] == 80
    assert maths["class_lowest"] == 40

    # the PDF still builds with the new columns
    pdf = await client.get(f"/api/report/{s[1]}/pdf", headers=h,
                           params={"term_id": ids["term_id"]})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


# ------------------------------------------------ cumulative session result

async def test_third_term_card_shows_cumulative_session_result(ctx):
    from app.models.academics import Term, TermName
    from sqlalchemy import select

    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # find the session, add second and third terms to it
    async with ids["session_factory"]() as db:
        first = await db.get(Term, ids["term_id"])
        session_id = first.session_id
        t2 = Term(school_id=ids["school_id"], session_id=session_id,
                  name=TermName.SECOND)
        t3 = Term(school_id=ids["school_id"], session_id=session_id,
                  name=TermName.THIRD)
        db.add_all([t2, t3])
        await db.flush()
        t2id, t3id = t2.id, t3.id
        await db.commit()

    s = ids["student_ids"]
    # term 1 and 2 and 3 scores for the top student (and others so a class exists)
    for term_id, exam in ((ids["term_id"], 70), (t2id, 80), (t3id, 90)):
        comp = ids["component_ids"]
        for sid, e in zip(s, (exam, exam - 20, exam - 30)):
            await client.post("/api/scores", headers=h, json={
                "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
                "term_id": term_id, "rows": [{"student_id": sid,
                "scores": {comp[3]: max(e, 0)}}]})
        await client.post("/api/results/compute", headers=h, json={
            "arm_id": ids["arm_id"], "term_id": term_id})
        await client.post("/api/results/publish", headers=h, json={
            "arm_id": ids["arm_id"], "term_id": term_id})

    rep = (await client.get(f"/api/report/{s[0]}", headers=h,
           params={"term_id": t3id})).json()
    cum = rep["cumulative"]
    assert cum is not None
    assert [t["term"] for t in cum["per_term"]] == ["First", "Second", "Third"]
    # the three term averages for the top student average out to the cumulative
    avgs = [t["average"] for t in cum["per_term"]]
    assert cum["cumulative_average"] == round(sum(avgs) / 3, 2)
    assert cum["cumulative_position"] == 1          # top student every term

    # a first-term card has no cumulative block
    rep1 = (await client.get(f"/api/report/{s[0]}", headers=h,
            params={"term_id": ids["term_id"]})).json()
    assert rep1["cumulative"] is None


# ------------------------------------------------ comment bank

async def test_comment_bank_create_suggest_delete(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")

    low = (await client.post("/api/comment-bank", headers=h, json={
        "text": "Needs to work harder next term.",
        "min_average": 0, "max_average": 49, "audience": "form_teacher"})).json()["id"]
    await client.post("/api/comment-bank", headers=h, json={
        "text": "An excellent and consistent performance.",
        "min_average": 70, "max_average": 100, "audience": "form_teacher"})

    # a struggling student's average suggests only the low-band comment
    sug = (await client.get("/api/comment-bank/suggest", headers=h,
           params={"average": 35, "audience": "form_teacher"})).json()
    assert len(sug) == 1 and "harder" in sug[0]["text"]

    # a strong average suggests the high-band one
    sug2 = (await client.get("/api/comment-bank/suggest", headers=h,
            params={"average": 85, "audience": "form_teacher"})).json()
    assert len(sug2) == 1 and "excellent" in sug2[0]["text"].lower()

    # list shows both; delete removes one
    assert len((await client.get("/api/comment-bank", headers=h)).json()) == 2
    await client.delete(f"/api/comment-bank/{low}", headers=h)
    assert len((await client.get("/api/comment-bank", headers=h)).json()) == 1


# ------------------------------------------------ affective traits

async def test_affective_traits_configure_and_rate_a_class(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # configure the school's trait list
    await client.patch("/api/schools/me", headers=h, json={
        "affective_traits": ["Punctuality", "Neatness", "Cooperation"]})

    # compute so term results exist to attach ratings to
    await _enter(client, h, ids, ids["student_ids"][0], 55)
    await client.post("/api/results/compute", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # the grid reports the trait list and empty ratings
    grid = (await client.get("/api/results/affective", headers=h, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert grid["traits"] == ["Punctuality", "Neatness", "Cooperation"]

    sid = ids["student_ids"][0]
    r = (await client.post("/api/results/affective", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"],
        "ratings": {sid: {"Punctuality": 5, "Neatness": 4,
                          "Unknown trait": 3, "Cooperation": 9}}})).json()
    assert r["saved"] == 1

    # only known traits in 1-5 are kept (Unknown dropped, 9 clamped out)
    grid2 = (await client.get("/api/results/affective", headers=h, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    mine = next(x for x in grid2["students"] if x["student_id"] == sid)
    assert mine["ratings"] == {"Punctuality": 5, "Neatness": 4}
