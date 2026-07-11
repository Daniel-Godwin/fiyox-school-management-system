"""Audit trail — accountability for sensitive changes."""
from tests.conftest import headers


async def test_score_change_captured_old_to_new(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"][0]
    student = ids["student_ids"][0]

    # create then change the same score 5 -> 9
    for val in (5, 9):
        await client.post("/api/scores", headers=h, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": student, "scores": {comp: val}}]})

    logs = (await client.get("/api/audit-logs", headers=h,
            params={"table_name": "score_entries"})).json()
    updates = [l for l in logs if l["action"] == "update"]
    assert updates
    assert updates[0]["changes"]["score"] == {"old": 5.0, "new": 9.0}
    assert updates[0]["ip"] is not None


async def test_publish_is_audited(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    for sid in ids["student_ids"]:
        await client.post("/api/scores", headers=h, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: 50}}]})
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    # look up a term-result id directly, then publish it via the API
    from sqlalchemy import select
    from app.models.results import TermResult
    async with ids["session_factory"]() as db:
        tr = (await db.execute(select(TermResult).where(
            TermResult.student_id == ids["student_ids"][0]))).scalars().first()
        tr_id = tr.id

    r = await client.patch(f"/api/term-results/{tr_id}", headers=h,
                           json={"is_published": True, "form_teacher_comment": "Good term."})
    assert r.status_code == 200 and r.json()["published"] is True

    logs = (await client.get("/api/audit-logs", headers=h,
            params={"table_name": "term_results"})).json()
    assert any(l["action"] == "publish" for l in logs)


async def test_bulk_import_tagged_in_audit(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    csv_data = ("admission_number,first_name,last_name,gender,class,arm\n"
                "GSS/25/900,New,Pupil,male,JSS1,A\n")
    await client.post("/api/import/students",
                      headers=h, files={"file": ("s.csv", csv_data, "text/csv")})
    logs = (await client.get("/api/audit-logs", headers=h,
            params={"table_name": "students"})).json()
    bulk = [l for l in logs if l["changes"].get("source", {}).get("new") == "bulk_import"]
    assert len(bulk) == 1
