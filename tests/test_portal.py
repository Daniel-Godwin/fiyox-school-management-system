"""Family portal — a parent sees exactly their own wards, nothing else."""
from tests.conftest import headers


async def _make_parent(ids, email, student_index):
    from app.models.school import User, Role
    from app.models.student import Guardian
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        parent = User(school_id=ids["school_id"], email=email,
                      hashed_password=hash_password("parent123"),
                      role=Role.PARENT, first_name="P", last_name="Arent")
        db.add(parent)
        await db.flush()
        db.add(Guardian(school_id=ids["school_id"], parent_user_id=parent.id,
                        student_id=ids["student_ids"][student_index],
                        relationship="Guardian"))
        await db.commit()


async def test_my_wards_scoped_to_guardian_links(ctx):
    client, ids = ctx
    await _make_parent(ids, "p@x.ng", 0)
    ph = await headers(client, "p@x.ng", "parent123")

    wards = (await client.get("/api/my/wards", headers=ph)).json()
    assert len(wards) == 1
    assert wards[0]["name"] == "Chinedu Eze"
    assert wards[0]["class_label"] == "JSS1 A"

    # staff roles are rejected on portal endpoints
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    # school_admin passes require_roles via super override? No: require_roles allows
    # SUPER_ADMIN implicitly; SCHOOL_ADMIN is not in PortalRoles -> 403
    assert (await client.get("/api/my/wards", headers=ah)).status_code == 403


async def test_my_fees_shows_only_own_wards_invoice(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    await _make_parent(ids, "p@x.ng", 0)

    # bill the arm: one category+structure of 15000
    cat = (await client.post("/api/fees/categories", headers=ah,
           json={"name": "School Fees"})).json()
    from app.models.academics import ClassArm
    async with ids["session_factory"]() as db:
        arm = await db.get(ClassArm, ids["arm_id"])
        class_id = arm.class_id
    await client.post("/api/fees/structures", headers=ah, json={
        "class_id": class_id, "term_id": ids["term_id"],
        "category_id": cat["id"], "amount": 15000})
    await client.post("/api/fees/invoices/generate", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    ph = await headers(client, "p@x.ng", "parent123")
    fees = (await client.get("/api/my/fees", headers=ph,
            params={"term_id": ids["term_id"]})).json()
    assert len(fees) == 1                       # only their ward, not all 3 invoices
    assert fees[0]["student_id"] == ids["student_ids"][0]
    assert fees[0]["balance"] == 15000
    assert fees[0]["status"] == "unpaid"
