"""Report card — auto comments (class-relative), human overrides, branding."""
import base64
import io
from app.services.comments import generate_comments
from tests.conftest import headers


def _png_bytes(color=(11, 79, 108), size=(60, 60)) -> bytes:
    from PIL import Image
    img = Image.new("RGB", size, color)
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def _big_jpeg_bytes() -> bytes:
    """A realistic photo-sized logo: base64 of this is tens of thousands of
    characters, which is what broke production (varchar(400) columns)."""
    from PIL import Image
    import random
    img = Image.new("RGB", (400, 400))
    px = img.load()
    rnd = random.Random(7)
    for x in range(400):          # noise defeats JPEG compression -> big payload
        for y in range(400):
            px[x, y] = (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=85)
    return b.getvalue()


def test_every_student_in_a_class_gets_a_different_comment():
    """The whole point: a top student and a failing student must not receive
    the same words. (Bug report: 'comments go the same to all students'.)"""
    class_avg = 55.0
    roll = [("Fatima", 88, 1), ("Chinedu", 74, 2), ("Ngozi", 64, 3),
            ("Ibrahim", 57, 5), ("Tunde", 50, 8), ("Musa", 46, 10),
            ("Sani", 24, 12)]
    teacher, principal = [], []
    for name, avg, pos in roll:
        t, p = generate_comments(first_name=name, average=float(avg),
                                 position=pos, class_size=12,
                                 class_average=class_avg)
        teacher.append(t)
        principal.append(p)

    # the top and the bottom of the class must read completely differently
    assert teacher[0] != teacher[-1]
    assert principal[0] != principal[-1]
    assert "outstanding" in teacher[0].lower()
    assert any(w in teacher[-1].lower() for w in ("poor", "intervention", "behind"))
    assert any(w in principal[-1].lower() for w in ("unacceptable", "not acceptable",
                                                    "very poor"))
    # a healthy spread, not one comment repeated
    assert len(set(teacher)) >= 5, "teacher comments are not varying by performance"
    assert len(set(principal)) >= 3, "principal comments are not varying by performance"


def test_comment_is_internally_consistent():
    """A comment must never praise and scold in the same breath — the old
    version could say 'A fair performance ... Among the very best in the class'."""
    t, _ = generate_comments(first_name="Ngozi", average=64, position=3,
                             class_size=12, class_average=55)
    positive = any(w in t.lower() for w in ("strong", "very good", "well",
                                            "confidently", "understands"))
    negative = any(w in t.lower() for w in ("weak term", "disappointing",
                                            "struggling", "very poor"))
    assert positive and not negative


def test_standing_reflects_the_class_not_just_the_mark():
    # the same 62% means different things in different classes
    in_strong_class, _ = generate_comments(first_name="Bola", average=62,
                                           position=18, class_size=20,
                                           class_average=78)
    in_weak_class, _ = generate_comments(first_name="Bola", average=62,
                                         position=1, class_size=20,
                                         class_average=41)
    assert "below the class average" in in_strong_class.lower()
    assert "best result in the class" in in_weak_class.lower()


def test_a_failing_mark_is_never_praised_even_at_the_top_of_a_weak_class():
    """Being first in a class that is failing is not a pass."""
    t, p = generate_comments(first_name="Zainab", average=34, position=1,
                             class_size=20, class_average=28)
    assert "outstanding" not in t.lower()
    assert not any(w in p.lower() for w in ("excellent", "splendid"))


async def test_compute_generates_comments_and_class_average(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    for sid, mark in zip(ids["student_ids"], [65, 50, 35]):
        await client.post("/api/scores", headers=ah, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: mark}}]})
    res = (await client.post("/api/results/compute", headers=ah, json={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    assert res["class_average"] == 50.0   # (65+50+35)/3

    report = (await client.get(f"/api/report/{ids['student_ids'][0]}", headers=ah,
              params={"term_id": ids["term_id"]})).json()
    assert report["summary"]["class_average"] == 50.0
    assert report["comments"]["form_teacher"]           # generated, not blank
    assert report["comments"]["principal"]
    assert "Chinedu" in report["comments"]["form_teacher"]


async def test_human_comment_survives_recompute(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")
    comp = ids["component_ids"]
    for sid, mark in zip(ids["student_ids"], [65, 50, 35]):
        await client.post("/api/scores", headers=ah, json={
            "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
            "term_id": ids["term_id"],
            "rows": [{"student_id": sid, "scores": {comp[3]: mark}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    rows = (await client.get("/api/results", headers=ah, params={
        "arm_id": ids["arm_id"], "term_id": ids["term_id"]})).json()
    trid = rows[0]["term_result_id"]
    mine = "A pleasure to teach. Chinedu should lead the science club next term."
    await client.patch(f"/api/term-results/{trid}", headers=ah,
                       json={"form_teacher_comment": mine})

    # a score correction forces a recompute — the teacher's words must survive
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[0]: 9}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})

    report = (await client.get(f"/api/report/{ids['student_ids'][0]}", headers=ah,
              params={"term_id": ids["term_id"]})).json()
    assert report["comments"]["form_teacher"] == mine     # not overwritten
    assert report["comments"]["principal"]                # still auto-filled


async def test_branding_upload_and_appears_on_pdf(ctx):
    client, ids = ctx
    ah = await headers(client, "admin@gss-ikeja.ng", "admin123")

    for asset in ("logo", "signature", "stamp"):
        r = await client.post(f"/api/schools/me/branding/{asset}", headers=ah,
                              files={"file": (f"{asset}.png", _png_bytes(), "image/png")})
        assert r.status_code == 200 and r.json()["saved"] is True

    settings = (await client.get("/api/schools/me", headers=ah)).json()
    assert settings["has_logo"] and settings["has_signature"] and settings["has_stamp"]

    await client.patch("/api/schools/me", headers=ah,
                       json={"principal_name": "Rev. J. A. Danjuma"})

    # produce a real PDF with the branding embedded
    comp = ids["component_ids"]
    await client.post("/api/scores", headers=ah, json={
        "subject_id": ids["subject_id"], "arm_id": ids["arm_id"],
        "term_id": ids["term_id"],
        "rows": [{"student_id": ids["student_ids"][0], "scores": {comp[3]: 60}}]})
    await client.post("/api/results/compute", headers=ah,
                      json={"arm_id": ids["arm_id"], "term_id": ids["term_id"]})
    pdf = await client.get(f"/api/report/{ids['student_ids'][0]}/pdf", headers=ah,
                           params={"term_id": ids["term_id"]})
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 3000        # images actually embedded

    # a realistic image must actually PERSIST — the stored data URI runs to tens
    # of thousands of characters, so the column must be TEXT, not VARCHAR(400).
    # (Production rejected exactly this with StringDataRightTruncation.)
    big = _big_jpeg_bytes()
    r = await client.post("/api/schools/me/branding/logo", headers=ah,
                          files={"file": ("photo.jpg", big, "image/jpeg")})
    assert r.status_code == 200
    from app.models.school import School
    async with ids["session_factory"]() as db:
        school = await db.get(School, ids["school_id"])
        assert school.logo_url and len(school.logo_url) > 20_000, (
            "the image did not persist in full")

    # a PNG mislabelled by the browser (very common on Windows) is still accepted:
    # the format is decided by the file's magic bytes, not the label
    odd = await client.post("/api/schools/me/branding/logo", headers=ah,
                            files={"file": ("logo.png", _png_bytes(),
                                            "application/octet-stream")})
    assert odd.status_code == 200

    # but a non-image is rejected even if it claims to be a PNG
    bad = await client.post("/api/schools/me/branding/logo", headers=ah,
                            files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    denied = await client.post("/api/schools/me/branding/logo", headers=th,
                               files={"file": ("l.png", _png_bytes(), "image/png")})
    assert denied.status_code == 403
