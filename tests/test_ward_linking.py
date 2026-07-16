"""Reconciling an existing parent account with a sibling admitted later.

The real case: Peter Denis already has an account linked to his first child.
His second child is admitted afterwards, into a different class. The admin must
be able to link the new ward to the *existing* account — not create a duplicate
parent — and this must work for any parent with several children in the school.
"""
from tests.conftest import headers


async def _second_arm(client, ah, ids, name="B"):
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    return (await client.post("/api/academics/arms", headers=ah,
            json={"class_id": class_id, "name": name})).json()["id"]


async def test_link_a_sibling_to_an_existing_parent(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    # Peter, already linked to his first child only
    first_child = ids["student_ids"][0]
    peter = (await client.post("/api/users", headers=ah, json={
        "email": "danspeakfuture6@gmail.com", "role": "parent",
        "first_name": "Peter", "last_name": "Denis", "password": "peter1234",
        "ward_student_ids": [first_child]})).json()["user"]["id"]

    before = (await client.get(f"/api/users/{peter}/wards", headers=ah)).json()
    assert len(before) == 1

    # a second child, admitted later into a different class
    arm_b = await _second_arm(client, ah, ids)
    second_child = (await client.post("/api/students", headers=ah, json={
        "admission_number": "GSS/26/900", "first_name": "Grace",
        "last_name": "Denis", "gender": "female",
        "current_arm_id": arm_b})).json()["id"]

    linked = await client.post(f"/api/users/{peter}/wards", headers=ah,
                               json={"student_id": second_child,
                                     "relationship": "Father"})
    assert linked.status_code == 201

    after = (await client.get(f"/api/users/{peter}/wards", headers=ah)).json()
    assert len(after) == 2
    names = {w["name"] for w in after}
    assert "Grace Denis" in names

    # and Peter himself now sees both, each in its own class
    ph = await headers(client, "danspeakfuture6@gmail.com", "peter1234")
    wards = (await client.get("/api/my/wards", headers=ph)).json()
    assert len(wards) == 2


async def test_a_ward_cannot_be_linked_to_the_same_parent_twice(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    child = ids["student_ids"][0]
    parent = (await client.post("/api/users", headers=ah, json={
        "email": "mum@x.ng", "role": "parent", "first_name": "M", "last_name": "U",
        "password": "mum12345", "ward_student_ids": [child]})).json()["user"]["id"]

    dup = await client.post(f"/api/users/{parent}/wards", headers=ah,
                            json={"student_id": child})
    assert dup.status_code == 409


async def test_unlinking_a_ward_revokes_that_parents_view(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    a, b = ids["student_ids"][0], ids["student_ids"][1]
    parent = (await client.post("/api/users", headers=ah, json={
        "email": "dad@x.ng", "role": "parent", "first_name": "D", "last_name": "A",
        "password": "dad12345", "ward_student_ids": [a, b]})).json()["user"]["id"]

    # a child was linked to the wrong parent — detach one
    r = await client.delete(f"/api/users/{parent}/wards/{b}", headers=ah)
    assert r.status_code == 200

    remaining = (await client.get(f"/api/users/{parent}/wards", headers=ah)).json()
    assert [w["student_id"] for w in remaining] == [a]

    # the student itself is untouched — still in the school roll
    roll = (await client.get("/api/students", headers=ah)).json()
    assert b in [s["id"] for s in roll]

    # unlinking something not linked is a clean 404, not a 500
    again = await client.delete(f"/api/users/{parent}/wards/{b}", headers=ah)
    assert again.status_code == 404


async def test_ward_management_is_admin_only(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    child = ids["student_ids"][0]
    parent = (await client.post("/api/users", headers=ah, json={
        "email": "p2@x.ng", "role": "parent", "first_name": "P", "last_name": "2",
        "password": "par12345", "ward_student_ids": [child]})).json()["user"]["id"]

    # a teacher may not read or change another family's ward links
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get(f"/api/users/{parent}/wards", headers=th)).status_code == 403
    assert (await client.post(f"/api/users/{parent}/wards", headers=th,
            json={"student_id": child})).status_code == 403
