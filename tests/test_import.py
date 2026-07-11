"""Bulk student import — validation, duplicates, auto-create, dry-run, xlsx."""
import io
from tests.conftest import headers

CSV = (
    "admission_number,first_name,last_name,gender,class,arm\n"
    "GSS/25/201,Blessing,Adewale,female,SS3,C\n"   # new class+arm auto-created
    "GSS/25/202,Emeka,Okonkwo,male,SS3,C\n"        # reuses SS3/C
    "GSS/25/001,Chinedu,Eze,male,JSS1,A\n"         # duplicate of seeded student
    "GSS/25/203,Bad,Gender,unknown,JSS1,A\n"       # invalid gender
    "GSS/25/204,,NoName,male,JSS1,A\n"             # missing first name
)


async def test_dry_run_writes_nothing(ctx):
    client, _ = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    before = len((await client.get("/api/students", headers=h)).json())
    res = (await client.post("/api/import/students?dry_run=true", headers=h,
           files={"file": ("s.csv", CSV, "text/csv")})).json()
    assert res["dry_run"] is True
    assert res["created"] == 2 and res["skipped"] == 1 and res["errors"] == 2
    after = len((await client.get("/api/students", headers=h)).json())
    assert before == after  # nothing persisted


async def test_real_import_counts_and_reasons(ctx):
    client, _ = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    res = (await client.post("/api/import/students", headers=h,
           files={"file": ("s.csv", CSV, "text/csv")})).json()
    assert res["created"] == 2
    assert res["skipped"] == 1
    assert res["errors"] == 2
    assert res["classes_created"] == 1  # SS3
    assert res["arms_created"] == 1     # C
    reasons = {r["status"] for r in res["results"]}
    assert {"created", "skipped", "error"} <= reasons


async def test_import_template_downloads(ctx):
    client, _ = ctx
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    r = await client.get("/api/import/students/template", headers=h)
    assert r.status_code == 200
    assert "admission_number" in r.content.decode("utf-8-sig")


async def test_xlsx_import(ctx):
    client, _ = ctx
    import openpyxl
    h = await headers(client, "admin@gss-ikeja.ng", "admin123")
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["admission_number", "first_name", "last_name", "gender", "class", "arm"])
    ws.append(["GSS/25/301", "Aisha", "Bello", "female", "JSS1", "A"])
    bio = io.BytesIO(); wb.save(bio); bio.seek(0)
    res = (await client.post("/api/import/students", headers=h, files={"file": (
        "s.xlsx", bio.read(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})).json()
    assert res["created"] == 1
