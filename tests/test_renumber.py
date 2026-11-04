"""Bulk renumbering a class's admission numbers — preview, apply, conflicts, RBAC."""
from tests.conftest import headers


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def test_renumber_preview_then_apply(ctx):
    client, ids = ctx
    ah = await _admin(client)
    arm = ids["arm_id"]

    # preview does not change anything
    pv = await client.post("/api/students/renumber", headers=ah, json={
        "arm_id": arm, "year": "25", "prefix": "FAD", "start": 1, "apply": False})
    assert pv.status_code == 200
    body = pv.json()
    assert body["applied"] is False and body["count"] == 3 and body["conflicts"] == 0
    # roster is ordered by surname: Bello, Eze, Okafor
    assert [r["new"] for r in body["preview"]] == ["FAD/25/001", "FAD/25/002", "FAD/25/003"]
    assert [r["name"] for r in body["preview"]] == ["Fatima Bello", "Chinedu Eze", "Ngozi Okafor"]
    studs = (await client.get("/api/students", headers=ah)).json()
    assert all(not s["admission_number"].startswith("FAD") for s in studs)

    # apply writes the new numbers
    ap = await client.post("/api/students/renumber", headers=ah, json={
        "arm_id": arm, "year": "25", "prefix": "FAD", "start": 1, "apply": True})
    assert ap.status_code == 200 and ap.json()["applied"] is True
    studs = (await client.get("/api/students", headers=ah)).json()
    assert sorted(s["admission_number"] for s in studs) == ["FAD/25/001", "FAD/25/002", "FAD/25/003"]


async def test_renumber_defaults_prefix_and_start(ctx):
    client, ids = ctx
    ah = await _admin(client)
    # no prefix -> school initials ("GSS Ikeja" -> "GI"); start at 10
    body = (await client.post("/api/students/renumber", headers=ah, json={
        "arm_id": ids["arm_id"], "year": "26", "start": 10, "apply": False})).json()
    assert [r["new"] for r in body["preview"]] == ["GI/26/010", "GI/26/011", "GI/26/012"]


async def test_renumber_conflict_blocks_apply(ctx):
    client, ids = ctx
    ah = await _admin(client)
    # a student outside the class already holds one of the target numbers
    await client.post("/api/students", headers=ah, json={
        "admission_number": "FAD/25/002", "first_name": "Out", "last_name": "Sider",
        "gender": "male", "current_arm_id": None})
    pv = (await client.post("/api/students/renumber", headers=ah, json={
        "arm_id": ids["arm_id"], "year": "25", "prefix": "FAD", "start": 1, "apply": False})).json()
    assert pv["conflicts"] == 1
    assert any(r["conflict"] and r["new"] == "FAD/25/002" for r in pv["preview"])
    # applying is refused while a clash remains
    ap = await client.post("/api/students/renumber", headers=ah, json={
        "arm_id": ids["arm_id"], "year": "25", "prefix": "FAD", "start": 1, "apply": True})
    assert ap.status_code == 409


async def test_renumber_is_admin_only(ctx):
    client, ids = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    r = await client.post("/api/students/renumber", headers=th, json={
        "arm_id": ids["arm_id"], "year": "25", "apply": False})
    assert r.status_code == 403
