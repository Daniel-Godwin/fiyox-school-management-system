"""Result approval workflow — report cards reach parents only after sign-off.

The gate: draft -> submitted (form teacher) -> approved (principal) -> publish.
Nothing a parent can see should ever have skipped the principal's approval, and
a result whose marks are recomputed must lose any approval it had.
"""
from tests.conftest import headers


async def _enable_gate(client, ids):
    """Switch the approval requirement on for the test school."""
    async with ids["session_factory"]() as db:
        from app.models.school import School
        school = await db.get(School, ids["school_id"])
        school.result_approval_required = True
        await db.commit()


async def _computed(client, ids, gate=True):
    """Enter one score for the whole arm and compute, leaving results in draft."""
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    if gate:
        await _enable_gate(client, ids)
    comp = ids["component_ids"]
    for sid in ids["student_ids"]:
        await client.post("/api/scores", headers=h, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: 55}}]})
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    return h


def _statuses(rows):
    return {(r["approval_status"], r["is_published"]) for r in rows}


async def test_with_approval_off_admin_publishes_directly(ctx):
    """Default behaviour: a school that has not switched approval on publishes
    in one step, exactly as before — the pilot school sees no change."""
    client, ids = ctx
    h = await _computed(client, ids, gate=False)   # gate stays off

    pub = (await client.post("/api/results/publish", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert pub["published"] == len(ids["student_ids"])
    assert pub["blocked_unapproved"] == 0


async def test_results_start_in_draft_and_cannot_be_published(ctx):
    client, ids = ctx
    h = await _computed(client, ids)

    rows = (await client.get("/api/results", headers=h, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert _statuses(rows) == {("draft", False)}

    # publishing a draft does nothing and says why
    r = (await client.post("/api/results/publish", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert r["published"] == 0 and r["blocked_unapproved"] == len(ids["student_ids"])
    assert "approve" in r["note"].lower()


async def test_full_happy_path_submit_approve_publish(ctx):
    client, ids = ctx
    await _computed(client, ids)
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    assert (await client.post("/api/results/submit", headers=th, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()["submitted"] \
        == len(ids["student_ids"])

    assert (await client.post("/api/results/approve", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()["approved"] \
        == len(ids["student_ids"])

    pub = (await client.post("/api/results/publish", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert pub["published"] == len(ids["student_ids"]) and pub["blocked_unapproved"] == 0

    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert _statuses(rows) == {("approved", True)}
    # the approver is recorded
    async with ids["session_factory"]() as db:
        from app.models.results import TermResult
        from sqlalchemy import select
        tr = (await db.execute(select(TermResult))).scalars().first()
        assert tr.approved_by is not None and tr.approved_at is not None


async def test_a_teacher_cannot_approve_their_own_results(ctx):
    client, ids = ctx
    await _computed(client, ids)
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await client.post("/api/results/submit", headers=th, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    # approval is the principal's authority, not the submitter's
    assert (await client.post("/api/results/approve", headers=th, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).status_code == 403


async def test_principal_can_return_results_with_a_reason(ctx):
    client, ids = ctx
    await _computed(client, ids)
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await client.post("/api/results/submit", headers=th, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    r = (await client.post(
        f"/api/results/return?arm_id={ids['arm_id']}&term_id={ids['term_id']}",
        headers=ah, json={"form_teacher_comment": "Re-check the Maths exam column"})).json()
    assert r["returned"] == len(ids["student_ids"])

    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert _statuses(rows) == {("draft", False)}
    assert rows[0]["approval_note"] == "Re-check the Maths exam column"

    # a returned result cannot be published until it goes round again
    assert (await client.post("/api/results/publish", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()["published"] == 0


async def test_edit_endpoint_cannot_bypass_the_approval_gate(ctx):
    client, ids = ctx
    await _computed(client, ids)
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    trid = rows[0]["term_result_id"]

    # trying to flip is_published directly on a draft result is refused
    r = await client.patch(f"/api/term-results/{trid}", headers=ah,
                           json={"is_published": True})
    assert r.status_code == 400
    assert "approved" in r.json()["detail"].lower()


async def test_recompute_voids_a_prior_approval(ctx):
    client, ids = ctx
    ah = await _computed(client, ids)
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    await client.post("/api/results/submit", headers=th, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    await client.post("/api/results/approve", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    await client.post("/api/results/publish", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # the marks change, so the term is recomputed — approval must not survive
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[3]: 59}}]})
    await client.post("/api/results/compute", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert _statuses(rows) == {("draft", False)}   # back to square one, correctly
