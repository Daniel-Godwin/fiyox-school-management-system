"""Academics selectors + score prefill (the endpoints behind the entry grid)."""
from tests.conftest import headers


async def test_selectors_return_seeded_structure(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")

    terms = (await client.get("/api/academics/terms", headers=h)).json()
    assert len(terms) == 1
    assert terms[0]["name"] == "first" and terms[0]["is_current"] is True
    assert terms[0]["session"] == "2025/2026"

    arms = (await client.get("/api/academics/arms", headers=h)).json()
    assert len(arms) == 1
    assert arms[0]["label"] == "JSS1 A"

    subjects = (await client.get("/api/academics/subjects", headers=h)).json()
    assert [s["name"] for s in subjects] == ["Mathematics"]


async def test_selectors_are_tenant_scoped(ctx):
    client, ids = ctx
    sh = await headers(client, "owner@fiyox.ng", "owner123")
    await client.post("/api/schools", headers=sh, json={
        "name": "Unity College", "slug": "unity", "admin_email": "admin@unity.ng",
        "admin_password": "pass123", "admin_first_name": "Sade",
        "admin_last_name": "Bello"})
    h2 = await headers(client, "admin@unity.ng", "pass123")
    assert (await client.get("/api/academics/arms", headers=h2)).json() == []
    assert (await client.get("/api/academics/subjects", headers=h2)).json() == []


async def test_score_prefill_roundtrip(ctx):
    client, ids = ctx
    h = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0],
                  "scores": {comp[0]: 7, comp[3]: 55}}]})

    got = (await client.get("/api/scores", headers=h, params={
        "arm_id": ids["arm_id"], "subject_id": ids["subject_id"],
        "term_id": ids["term_id"]})).json()
    assert len(got) == 2
    by_comp = {g["component_id"]: g["score"] for g in got}
    assert by_comp[comp[0]] == 7 and by_comp[comp[3]] == 55
    assert all(g["student_id"] == ids["student_ids"][0] for g in got)
