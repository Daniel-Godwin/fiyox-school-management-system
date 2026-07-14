"""The AI layer — assistive, and never load-bearing.

The invariant: a school must be able to run *entirely* without an AI key. Every
test here runs with no ANTHROPIC_API_KEY configured, which is exactly how Fiyox
ships by default.
"""
from app.services.ai import assess_risk
from tests.conftest import headers


async def _computed(client, ah, ids, marks=(70, 55, 30)):
    comp = ids["component_ids"]
    for sid, m in zip(ids["student_ids"], marks):
        await client.post("/api/scores", headers=ah, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: m}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})


# ---------------------------------------------------------------- comments

async def test_comments_still_work_with_no_ai_key(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _computed(client, ah, ids)

    status = (await client.get("/api/ai/status", headers=ah)).json()
    assert status["llm_configured"] is False

    res = (await client.post("/api/ai/comments/regenerate", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    # fell back to the built-in engine for everyone — nothing failed
    assert res["ai_written"] == 0
    assert res["rules_written"] == 3
    assert "not configured" in res["note"]

    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert all(r["form_teacher_comment"] for r in rows)


async def test_regenerating_never_destroys_a_teachers_own_words(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _computed(client, ah, ids)

    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    trid = rows[0]["term_result_id"]
    mine = "Chinedu led the debate team with distinction this term."
    await client.patch(f"/api/term-results/{trid}", headers=ah,
                       json={"form_teacher_comment": mine})

    res = (await client.post("/api/ai/comments/regenerate", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert res["kept_human_edits"] == 1

    after = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    kept = next(r for r in after if r["term_result_id"] == trid)
    assert kept["form_teacher_comment"] == mine


# ---------------------------------------------------------------- at-risk

def test_risk_rules_are_transparent_and_proportionate():
    safe = assess_risk(average=78, class_average=60, failing_subjects=0,
                       subjects_count=4, attendance_pct=96,
                       previous_average=75, owes_fees=False)
    assert safe["level"] == "none" and safe["reasons"] == []

    failing = assess_risk(average=32, class_average=58, failing_subjects=3,
                          subjects_count=4, attendance_pct=61,
                          previous_average=48, owes_fees=True)
    assert failing["level"] == "high"
    joined = " ".join(failing["reasons"]).lower()
    assert "below the pass mark" in joined
    assert "failing 3 of 4" in joined
    assert "attendance is only 61" in joined
    assert "fees are outstanding" in joined
    assert "parents" in failing["recommended_action"].lower()

    # a sharp fall matters even from a decent mark
    falling = assess_risk(average=54, class_average=55, failing_subjects=0,
                          subjects_count=4, attendance_pct=92,
                          previous_average=71, owes_fees=False)
    assert falling["level"] in ("watch", "moderate")
    assert any("fallen" in r for r in falling["reasons"])


async def test_at_risk_register_flags_the_struggling_student(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _computed(client, ah, ids, marks=(75, 60, 25))   # third student failing

    register = (await client.get("/api/ai/at-risk", headers=ah,
                params={"term_id": ids["term_id"]})).json()

    names = [r["name"] for r in register]
    assert "Ngozi Okafor" in names          # the 25% student
    flagged = next(r for r in register if r["name"] == "Ngozi Okafor")
    assert flagged["level"] in ("high", "moderate")
    assert flagged["reasons"], "a flag with no reason is a black box"
    assert flagged["recommended_action"]

    # the strong student is not flagged at all
    assert "Chinedu Eze" not in names


async def test_at_risk_is_staff_only(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _computed(client, ah, ids)

    from app.models.school import User, Role
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        db.add(User(school_id=ids["school_id"], email="mum@ai.ng",
                    hashed_password=hash_password("mum12345"),
                    role=Role.PARENT, first_name="M", last_name="Um"))
        await db.commit()
    ph = await headers(client, "mum@ai.ng", "mum12345")
    r = await client.get("/api/ai/at-risk", headers=ph,
                         params={"term_id": ids["term_id"]})
    assert r.status_code == 403
