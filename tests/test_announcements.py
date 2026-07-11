"""Announcements — creation, role-targeted visibility, drafts."""
from tests.conftest import headers


async def _post(client, h, title, target, publish=True):
    r = await client.post("/api/announcements", headers=h, json={
        "title": title, "message": f"{title} body", "target": target,
        "publish": publish})
    assert r.status_code == 201
    return r.json()


async def test_role_targeted_visibility(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _post(client, ah, "PTA Meeting", "parents")
    await _post(client, ah, "Staff Briefing", "teachers")
    await _post(client, ah, "Resumption Date", "all")

    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    titles = {a["title"] for a in (await client.get("/api/announcements",
                                                    headers=th)).json()}
    assert titles == {"Staff Briefing", "Resumption Date"}
    assert "PTA Meeting" not in titles

    # admin sees everything
    admin_titles = {a["title"] for a in (await client.get("/api/announcements",
                                                          headers=ah)).json()}
    assert admin_titles == {"PTA Meeting", "Staff Briefing", "Resumption Date"}


async def test_drafts_hidden_from_non_admin(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _post(client, ah, "Fee Increase (draft)", "all", publish=False)
    await _post(client, ah, "Midterm Break", "all", publish=True)

    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    titles = {a["title"] for a in (await client.get("/api/announcements",
                                                    headers=th)).json()}
    assert titles == {"Midterm Break"}

    # draft still visible to admin, and audited
    admin_titles = {a["title"] for a in (await client.get("/api/announcements",
                                                          headers=ah)).json()}
    assert "Fee Increase (draft)" in admin_titles
    logs = (await client.get("/api/audit-logs", headers=ah,
            params={"table_name": "announcements"})).json()
    assert len(logs) == 2


async def test_teacher_cannot_create(ctx):
    client, _ = ctx
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    r = await client.post("/api/announcements", headers=th, json={
        "title": "x", "message": "y", "target": "all"})
    assert r.status_code == 403
