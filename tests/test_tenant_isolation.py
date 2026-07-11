"""Multi-tenant data isolation — the guarantee the whole SaaS rests on."""
from tests.conftest import headers


async def test_second_school_cannot_see_first_students(ctx):
    client, ids = ctx

    # first school's admin sees its 3 seeded students
    h1 = await headers(client, "admin@gss-ikeja.ng", "admin123")
    first = (await client.get("/api/students", headers=h1)).json()
    assert len(first) == 3

    # super admin onboards a second school
    sh = await headers(client, "owner@fiyox.ng", "owner123")
    r = await client.post("/api/schools", headers=sh, json={
        "name": "Unity College", "slug": "unity", "admin_email": "admin@unity.ng",
        "admin_password": "pass123", "admin_first_name": "Sade", "admin_last_name": "Bello"})
    assert r.status_code == 201

    # second school's admin sees zero — data is isolated
    h2 = await headers(client, "admin@unity.ng", "pass123")
    second = (await client.get("/api/students", headers=h2)).json()
    assert second == []


async def test_report_of_other_school_not_accessible(ctx):
    client, ids = ctx
    sh = await headers(client, "owner@fiyox.ng", "owner123")
    await client.post("/api/schools", headers=sh, json={
        "name": "Unity College", "slug": "unity", "admin_email": "admin@unity.ng",
        "admin_password": "pass123", "admin_first_name": "Sade", "admin_last_name": "Bello"})
    h2 = await headers(client, "admin@unity.ng", "pass123")
    # a student id from school 1 must not be reachable by school 2's admin
    other_student = ids["student_ids"][0]
    r = await client.get(f"/api/report/{other_student}",
                         headers=h2, params={"term_id": ids["term_id"]})
    assert r.status_code == 404
