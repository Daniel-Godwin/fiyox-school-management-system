"""Nursery & primary class levels.

The class ladder must now span pre-primary → primary → JSS → SS, so a primary
school (or a full nursery-through-secondary school) categorises its classes
correctly and the promotion order sorts across levels.
"""
from sqlalchemy import select

from tests.conftest import headers
from app.models.academics import ClassCategory, SchoolClass, infer_level


def test_infer_level_covers_nigerian_namings():
    C = ClassCategory
    cases = {
        "Creche": C.NURSERY, "Pre-Nursery": C.NURSERY, "Nursery 1": C.NURSERY,
        "KG1": C.NURSERY, "Reception": C.NURSERY,
        "Primary 1": C.PRIMARY, "Pry 6": C.PRIMARY, "Basic 3": C.PRIMARY,
        "Grade 2": C.PRIMARY,
        "Basic 8": C.JUNIOR, "JSS1": C.JUNIOR, "JS 3": C.JUNIOR,
        "SS1": C.SENIOR, "SSS 3": C.SENIOR, "Senior Secondary 2": C.SENIOR,
    }
    for name, cat in cases.items():
        assert infer_level(name)[0] == cat, f"{name} -> {infer_level(name)}"


def test_level_order_is_monotonic_across_the_ladder():
    ladder = ["Nursery 1", "KG2", "Primary 1", "Primary 6",
              "JSS1", "JSS3", "SS1", "SS3"]
    orders = [infer_level(n)[1] for n in ladder]
    assert orders == sorted(orders), orders
    assert len(set(orders)) == len(orders), "orders must be distinct and increasing"
    # bands stay separated: primary below junior, junior below senior
    assert infer_level("Primary 6")[1] < infer_level("JSS1")[1]
    assert infer_level("JSS3")[1] < infer_level("SS1")[1]


def test_unknown_name_falls_back_to_junior():
    cat, _ = infer_level("Special Class")
    assert cat == ClassCategory.JUNIOR          # preserves the prior default


async def test_quick_setup_categorises_a_primary_school(ctx):
    """A fresh primary school configured in one call gets primary classes in a
    correct promotion order — not everything lumped as 'junior'."""
    client, ids = ctx
    # ctx already seeded a school+session via conftest; make a second school so
    # quick-setup (which refuses a school that already has a session) can run.
    from app.models.school import School, User, Role
    from app.core.security import hash_password
    async with ids["session_factory"]() as db:
        s2 = School(name="Little Stars Academy", slug="little-stars", state="Lagos")
        db.add(s2)
        await db.flush()
        db.add(User(school_id=s2.id, email="admin@littlestars.ng",
                    hashed_password=hash_password("admin123"),
                    role=Role.SCHOOL_ADMIN, first_name="Ad", last_name="Min"))
        await db.commit()
        s2_id = s2.id
    admin = await headers(client, "admin@littlestars.ng", "admin123")

    r = await client.post("/api/academics/quick-setup", headers=admin, json={
        "session_name": "2025/2026", "term": "first",
        "classes": ["Nursery 1", "Nursery 2", "Primary 1", "Primary 2",
                    "Primary 3", "Primary 4", "Primary 5", "Primary 6"],
        "arms": ["A"], "subjects": ["Mathematics", "English", "Phonics"],
    })
    assert r.status_code == 201

    async with ids["session_factory"]() as db:
        classes = (await db.execute(select(SchoolClass).where(
            SchoolClass.school_id == s2_id))).scalars().all()
    by_name = {c.name: c for c in classes}
    assert by_name["Nursery 1"].category == ClassCategory.NURSERY
    assert by_name["Primary 1"].category == ClassCategory.PRIMARY
    # promotion ladder is strictly increasing in the order configured
    ladder = ["Nursery 1", "Nursery 2", "Primary 1", "Primary 2",
              "Primary 3", "Primary 4", "Primary 5", "Primary 6"]
    orders = [by_name[n].level_order for n in ladder]
    assert orders == sorted(orders) and len(set(orders)) == len(orders)
