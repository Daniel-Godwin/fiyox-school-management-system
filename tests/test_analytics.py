"""Analytics overview — the aggregated dashboard read."""
from tests.conftest import headers


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def _compute_results(client, h, ids):
    """Give the 3 seeded students exam marks and compute the term."""
    comp = ids["component_ids"]
    marks = [56, 42, 28]  # all >= pass mark (40 is pass; 28 < 40 fails)
    for sid, m in zip(ids["student_ids"], marks):
        await client.post("/api/scores", headers=h, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: m}}]})
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})


async def test_overview_enrolment(ctx):
    client, ids = ctx
    h = await _admin(client)
    data = (await client.get("/api/analytics/overview", headers=h,
                             params={"term_id": ids["term_id"]})).json()
    assert data["scope"] == "school"
    en = data["enrolment"]
    assert en["total_students"] == 3 and en["active"] == 3
    assert en["by_gender"] == {"male": 1, "female": 2}
    assert en["by_class"] == [{"class": "JSS1", "count": 3}]


async def test_overview_academics_after_compute(ctx):
    client, ids = ctx
    h = await _admin(client)
    await _compute_results(client, h, ids)
    data = (await client.get("/api/analytics/overview", headers=h,
                             params={"term_id": ids["term_id"]})).json()
    ac = data["academics"]
    assert ac["computed_results"] == 3
    assert ac["overall_average"] is not None
    assert ac["pass_rate"] is not None
    # one student scored 28 (below the 40 pass mark)
    assert ac["below_pass"] == 1
    assert len(ac["grade_distribution"]) > 0
    assert ac["top_students"][0]["average"] >= ac["top_students"][-1]["average"]


async def test_overview_without_term_still_gives_enrolment(ctx):
    client, ids = ctx
    h = await _admin(client)
    data = (await client.get("/api/analytics/overview", headers=h)).json()
    assert data["term"] is None
    assert data["enrolment"]["total_students"] == 3
    assert data["academics"]["computed_results"] == 0
    assert data["finance"]["expected"] == 0.0


async def test_overview_rbac(ctx):
    client, ids = ctx
    # teacher may not open analytics
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/analytics/overview", headers=th,
                             params={"term_id": ids["term_id"]})).status_code == 403
    # super admin sees a platform roll-up
    oh = await headers(client, "owner@fiyox.ng", "owner123")
    data = (await client.get("/api/analytics/overview", headers=oh,
                             params={"term_id": ids["term_id"]})).json()
    assert data["scope"] == "platform"
    assert data["enrolment"]["total_students"] == 3   # the one seeded school
