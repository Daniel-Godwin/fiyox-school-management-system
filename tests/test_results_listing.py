"""Class results listing + bulk publish (the review-and-release flow)."""
from tests.conftest import headers


async def _enter_and_compute(client, h, ids):
    comp = ids["component_ids"]
    exams = [56, 42, 28]  # totals 56/42/28 -> positions 1/2/3
    for sid, exam in zip(ids["student_ids"], exams):
        await client.post("/api/scores", headers=h, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: exam}}]})
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})


async def test_results_listing_ranked(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _enter_and_compute(client, h, ids)

    rows = (await client.get("/api/results", headers=h, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert len(rows) == 3
    assert [r["position"] for r in rows] == [1, 2, 3]
    assert rows[0]["grand_total"] == 56
    assert rows[0]["name"] == "Chinedu Eze"
    assert all(r["is_published"] is False for r in rows)
    assert all(r["class_size"] == 3 for r in rows)


async def test_bulk_publish_flips_all_and_is_idempotent(ctx):
    client, ids = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _enter_and_compute(client, h, ids)

    res = (await client.post("/api/results/publish", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert res == {"published": 3, "already_published": 0}

    rows = (await client.get("/api/results", headers=h, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert all(r["is_published"] for r in rows)

    # re-running publishes nothing new (no duplicate audit noise)
    again = (await client.post("/api/results/publish", headers=h, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert again == {"published": 0, "already_published": 3}

    logs = (await client.get("/api/audit-logs", headers=h,
            params={"table_name": "term_results"})).json()
    assert len([l for l in logs if l["action"] == "publish"]) == 3

    # teachers can view the listing but cannot publish
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/results", headers=th, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).status_code == 200
    assert (await client.post("/api/results/publish", headers=th, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).status_code == 403
