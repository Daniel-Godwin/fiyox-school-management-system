"""Bulk student onboarding — the migration on-ramp from paper/Excel to Fiyox.

Accepts a CSV or XLSX upload, validates each row, resolves (or optionally
auto-creates) the class + arm, and inserts students with authorship + audit.
Returns a per-row report so an admin can fix a spreadsheet and re-upload.
Supports dry_run to preview without writing anything.
"""
import csv
import io
from datetime import date, datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.academics import SchoolClass, ClassArm, ClassCategory
from app.models.student import Student, Gender
from app.services.audit import record_audit

REQUIRED = ["admission_number", "first_name", "last_name", "gender"]
TEMPLATE_HEADERS = [
    "admission_number", "first_name", "last_name", "other_names",
    "gender", "class", "arm", "date_of_birth", "date_admitted",
]


def _normalize(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_")


def parse_upload(filename: str, content: bytes) -> list[dict]:
    """Return a list of row dicts keyed by normalized headers, for CSV or XLSX."""
    name = (filename or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return [{_normalize(k): (v.strip() if isinstance(v, str) else v)
                 for k, v in row.items()} for row in reader]
    if name.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_normalize(str(h)) for h in rows[0]]
        out = []
        for r in rows[1:]:
            if all(c is None for c in r):
                continue
            out.append({headers[i]: (str(v).strip() if v is not None else "")
                        for i, v in enumerate(r) if i < len(headers)})
        return out
    raise ValueError("Unsupported file type — upload a .csv or .xlsx")


def _gender(raw: str) -> Gender | None:
    v = (raw or "").strip().lower()
    if v in ("m", "male"):
        return Gender.MALE
    if v in ("f", "female"):
        return Gender.FEMALE
    return None


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _infer_category(class_name: str) -> tuple[ClassCategory, int]:
    """Guess junior/senior and a level order from a Nigerian class name."""
    up = class_name.upper().replace(" ", "")
    digit = next((int(c) for c in up if c.isdigit()), 0)
    if up.startswith("JSS") or up.startswith("JS"):
        return ClassCategory.JUNIOR, digit
    if up.startswith("SSS") or up.startswith("SS"):
        return ClassCategory.SENIOR, 3 + digit
    return ClassCategory.JUNIOR, digit


async def _resolve_arm(db, school_id, class_name, arm_name, auto_create, cache):
    """Return (arm_id, error, created_class, created_arm)."""
    class_name = (class_name or "").strip()
    arm_name = (arm_name or "").strip() or "A"
    if not class_name:
        return None, "missing class", False, False

    key = (class_name.lower(), arm_name.lower())
    if key in cache:
        return cache[key], None, False, False

    klass = (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id,
        func.lower(SchoolClass.name) == class_name.lower()))).scalars().first()
    created_class = False
    if not klass:
        if not auto_create:
            return None, f"class '{class_name}' not found", False, False
        cat, order = _infer_category(class_name)
        klass = SchoolClass(school_id=school_id, name=class_name,
                            category=cat, level_order=order)
        db.add(klass)
        await db.flush()
        created_class = True

    arm = (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id, ClassArm.class_id == klass.id,
        func.lower(ClassArm.name) == arm_name.lower()))).scalars().first()
    created_arm = False
    if not arm:
        if not auto_create:
            return None, f"arm '{arm_name}' not found in {class_name}", False, False
        arm = ClassArm(school_id=school_id, class_id=klass.id, name=arm_name)
        db.add(arm)
        await db.flush()
        created_arm = True

    cache[key] = arm.id
    return arm.id, None, created_class, created_arm


async def import_students(db: AsyncSession, school_id: str, user_id: str,
                          rows: list[dict], *, auto_create: bool = True,
                          dry_run: bool = False, ip: str | None = None) -> dict:
    # existing admission numbers for duplicate detection
    existing = set((await db.execute(select(Student.admission_number).where(
        Student.school_id == school_id))).scalars().all())

    results = []
    created = skipped = errored = 0
    created_classes = created_arms = 0
    arm_cache: dict = {}
    seen_in_file: set = set()

    for i, row in enumerate(rows, start=2):  # row 1 = header
        adm = (row.get("admission_number") or "").strip()
        missing = [f for f in REQUIRED if not (row.get(f) or "").strip()]
        if missing:
            errored += 1
            results.append({"row": i, "admission_number": adm,
                            "status": "error", "reason": f"missing: {', '.join(missing)}"})
            continue

        gender = _gender(row.get("gender"))
        if gender is None:
            errored += 1
            results.append({"row": i, "admission_number": adm,
                            "status": "error", "reason": "gender must be male/female"})
            continue

        if adm in existing or adm in seen_in_file:
            skipped += 1
            results.append({"row": i, "admission_number": adm,
                            "status": "skipped", "reason": "duplicate admission_number"})
            continue

        arm_id, err, cc, ca = await _resolve_arm(
            db, school_id, row.get("class"), row.get("arm"), auto_create, arm_cache)
        if err:
            errored += 1
            results.append({"row": i, "admission_number": adm,
                            "status": "error", "reason": err})
            continue
        created_classes += int(cc)
        created_arms += int(ca)

        seen_in_file.add(adm)
        if not dry_run:
            student = Student(
                school_id=school_id, admission_number=adm,
                first_name=row["first_name"].strip(), last_name=row["last_name"].strip(),
                other_names=(row.get("other_names") or "").strip() or None,
                gender=gender, current_arm_id=arm_id,
                date_of_birth=_parse_date(row.get("date_of_birth")),
                date_admitted=_parse_date(row.get("date_admitted")),
                created_by=user_id)
            db.add(student)
            await db.flush()
            await record_audit(db, school_id=school_id, user_id=user_id, action="create",
                               table_name="students", record_id=student.id,
                               changes={"source": {"old": None, "new": "bulk_import"},
                                        "admission_number": {"old": None, "new": adm}},
                               ip_address=ip)
        created += 1
        results.append({"row": i, "admission_number": adm, "status": "created"})

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    return {
        "dry_run": dry_run,
        "total_rows": len(rows),
        "created": created, "skipped": skipped, "errors": errored,
        "classes_created": created_classes, "arms_created": created_arms,
        "results": results,
    }


def template_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEADERS)
    w.writerow(["GSS/25/101", "Blessing", "Adewale", "", "female",
                "JSS1", "A", "2012-05-14", "2025-09-15"])
    w.writerow(["GSS/25/102", "Emeka", "Okonkwo", "Chidi", "male",
                "SS2", "B", "2009-11-02", "2025-09-15"])
    return buf.getvalue()
