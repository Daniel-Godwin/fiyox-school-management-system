"""Role-based access control."""
from tests.conftest import headers


async def test_school_admin_cannot_create_school(ctx):
    client, _ = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    r = await client.post("/api/schools", headers=h, json={
        "name": "X", "slug": "x", "admin_email": "a@x.ng", "admin_password": "pass123",
        "admin_first_name": "a", "admin_last_name": "b"})
    assert r.status_code == 403


async def test_teacher_cannot_compute_results(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    r = await client.post("/api/results/compute", headers=h,
                          json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    assert r.status_code == 403


async def test_unauthenticated_blocked(ctx):
    client, _ = ctx
    assert (await client.get("/api/students")).status_code == 401


async def test_teacher_can_enter_scores(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    comp = ids["component_ids"][0]
    r = await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"], "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp: 8}}]})
    assert r.status_code == 200
    assert r.json()["scores_written"] == 1
