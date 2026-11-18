"""Primary & nursery pupils are graded on a descriptive scale, not WAEC codes.

A score of 85 is "A1" on the secondary WAEC scale but "A" on the primary scale.
Compute a primary class and a secondary class with the same mark and the grades
must differ — and a school can set its own primary scale.
"""
from sqlalchemy import select

from tests.conftest import headers
from app.models.school import bands_for_category, PRIMARY_GRADING_BANDS, DEFAULT_GRADING
from app.models.academics import ClassCategory, SchoolClass, ClassArm
from app.models.results import SubjectResult


def test_bands_for_category_picks_the_right_scale():
    cfg = DEFAULT_GRADING
    assert bands_for_category(cfg, ClassCategory.PRIMARY) == PRIMARY_GRADING_BANDS
    assert bands_for_category(cfg, ClassCategory.NURSERY) == PRIMARY_GRADING_BANDS
    assert bands_for_category(cfg, "primary") == PRIMARY_GRADING_BANDS
    assert bands_for_category(cfg, ClassCategory.JUNIOR) == cfg["bands"]
    assert bands_for_category(cfg, ClassCategory.SENIOR) == cfg["bands"]
    # a custom primary scale wins for primary, never for secondary
    custom = {"bands": DEFAULT_GRADING["bands"],
              "primary_bands": [{"min": 0, "grade": "P", "remark": "x"}]}
    assert bands_for_category(custom, "primary")[0]["grade"] == "P"
    assert bands_for_category(custom, "junior") == DEFAULT_GRADING["bands"]


async def _primary_arm_with_student(ids):
    """A Primary 3 class/arm in the ctx school, with student 0 moved into it."""
    async with ids["session_factory"]() as db:
        klass = SchoolClass(school_id=ids["school_id"], name="Primary 3",
                            category=ClassCategory.PRIMARY, level_order=13)
        db.add(klass)
        await db.flush()
        arm = ClassArm(school_id=ids["school_id"], class_id=klass.id, name="A")
        db.add(arm)
        await db.flush()
        from app.models.student import Student
        st = await db.get(Student, ids["student_ids"][0])
        st.current_arm_id = arm.id
        await db.commit()
        return arm.id


async def test_primary_class_uses_the_primary_grade_scale(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    subj, term = ids["subject_id"], ids["term_id"]
    arm = await _primary_arm_with_student(ids)
    student = ids["student_ids"][0]

    # a strong mark: 85 total (sums to 85 across the four components).
    # Admin enters scores so the test isn't gated on a teaching assignment.
    await client.post("/api/scores", headers=admin, json={
        "subject_id": subj, "arm_id": arm, "term_id": term,
        "rows": [{"student_id": student,
                  "scores": {comp[0]: 10, comp[1]: 10, comp[2]: 15, comp[3]: 50}}]})
    await client.post("/api/results/compute", headers=admin,
                      json={"arm_id": arm, "term_id": term})

    async with ids["session_factory"]() as db:
        sr = (await db.execute(select(SubjectResult).where(
            SubjectResult.student_id == student,
            SubjectResult.term_id == term))).scalars().first()
    # primary scale labels this "A" (not the WAEC "A1")
    assert sr is not None and sr.total == 85
    assert sr.grade == "A"


async def test_grading_endpoint_exposes_and_sets_primary_bands(ctx):
    client, ids = ctx
    admin = await headers(client, "admin@gss-ikeja.ng", "admin123")

    g = (await client.get("/api/schools/me/grading", headers=admin)).json()
    assert g["primary_is_custom"] is False
    assert any(b["grade"] == "A" for b in g["primary_bands"])

    # set a custom primary scale, then confirm it is reported as custom
    put = (await client.put("/api/schools/me/grading/primary", headers=admin, json={
        "bands": [
            {"grade": "Dist", "min": 70, "remark": "Distinction"},
            {"grade": "Merit", "min": 50, "remark": "Merit"},
            {"grade": "Dev", "min": 0, "remark": "Developing"},
        ]})).json()
    assert put["primary_is_custom"] is True
    g2 = (await client.get("/api/schools/me/grading", headers=admin)).json()
    assert g2["primary_is_custom"] is True
    assert [b["grade"] for b in g2["primary_bands"]] == ["Dist", "Merit", "Dev"]

    # reset restores the default scale
    r = (await client.post("/api/schools/me/grading/primary/reset", headers=admin)).json()
    assert r["primary_is_custom"] is False
