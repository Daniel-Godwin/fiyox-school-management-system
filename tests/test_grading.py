"""Custom grading systems — a school keeps WAEC bands or defines its own."""
from tests.conftest import headers


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def _enter(client, h, ids, student_id, totals):
    c = ids["component_ids"]
    await client.post("/api/scores", headers=h, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"], "term_id": ids["term_id"],
        "rows": [{"student_id": student_id, "scores": {
            c[0]: totals[0], c[1]: totals[1], c[2]: totals[2], c[3]: totals[3]}}]})


async def test_grading_defaults_to_waec(ctx):
    client, ids = ctx
    h = await _admin(client)
    g = (await client.get("/api/schools/me/grading", headers=h)).json()
    assert g["is_waec"] is True
    top = g["bands"][0]
    assert top["grade"] == "A1" and top["min"] == 75 and top["max"] == 100


async def test_set_custom_grading_and_it_drives_grades(ctx):
    client, ids = ctx
    h = await _admin(client)
    # a simple A/B/C/F school scale
    custom = {"bands": [
        {"grade": "A", "min": 70, "remark": "Distinction"},
        {"grade": "B", "min": 50, "remark": "Merit"},
        {"grade": "C", "min": 40, "remark": "Pass"},
        {"grade": "F", "min": 0, "remark": "Fail"},
    ]}
    r = await client.put("/api/schools/me/grading", headers=h, json=custom)
    assert r.status_code == 200
    body = r.json()
    assert body["is_waec"] is False
    assert body["bands"][0] == {"grade": "A", "min": 70, "max": 100, "remark": "Distinction"}

    # a student scoring 80 now gets 'A', not 'A1'
    await _enter(client, h, ids, ids["student_ids"][0], (8, 8, 8, 56))   # total 80
    await client.post("/api/results/compute", headers=h,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    rep = (await client.get(f"/api/report/{ids['student_ids'][0]}", headers=h,
                            params={"term_id": ids["term_id"]})).json()
    maths = rep["subjects"][0]
    assert maths["grade"] == "A" and maths["remark"] == "Distinction"
    # the report card key reflects the custom scale
    assert rep["grading_key"][0]["grade"] == "A"


async def test_custom_grading_validation(ctx):
    client, ids = ctx
    h = await _admin(client)
    # must start at 0
    r = await client.put("/api/schools/me/grading", headers=h, json={"bands": [
        {"grade": "A", "min": 50, "remark": ""}, {"grade": "B", "min": 40, "remark": ""}]})
    assert r.status_code == 422
    # no duplicate starts
    r = await client.put("/api/schools/me/grading", headers=h, json={"bands": [
        {"grade": "A", "min": 0, "remark": ""}, {"grade": "B", "min": 0, "remark": ""}]})
    assert r.status_code == 422


async def test_reset_to_waec(ctx):
    client, ids = ctx
    h = await _admin(client)
    await client.put("/api/schools/me/grading", headers=h, json={"bands": [
        {"grade": "P", "min": 50, "remark": "Pass"}, {"grade": "F", "min": 0, "remark": "Fail"}]})
    assert (await client.get("/api/schools/me/grading", headers=h)).json()["is_waec"] is False
    r = await client.post("/api/schools/me/grading/reset", headers=h)
    assert r.status_code == 200 and r.json()["is_waec"] is True
    assert (await client.get("/api/schools/me/grading", headers=h)).json()["is_waec"] is True


async def test_grading_edit_is_admin_only(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    # a teacher may read the scale but not change it
    assert (await client.get("/api/schools/me/grading", headers=th)).status_code == 200
    r = await client.put("/api/schools/me/grading", headers=th, json={"bands": [
        {"grade": "F", "min": 0, "remark": "Fail"}]})
    assert r.status_code == 403
