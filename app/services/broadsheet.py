"""Termly class score sheet (broadsheet).

Where the cumulative annual broadsheet (services/annual.py) stacks three terms
into one grid, this assembles a *single* term for a whole class: every student
(rows) against every subject offered that term (columns), each cell the subject
total out of 100, plus each student's grand total, average, grade and position.

It reads straight from the term snapshots the result engine already writes —
SubjectResult (per student per subject) and TermResult (the overall standing) —
so the sheet always matches the report cards for the same term. The column set
is the subjects that actually have a result in this arm this term, ordered by
name, so a class only shows the subjects it sat.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.school import School
from app.models.student import Student
from app.models.academics import Term, ClassArm, SchoolClass, Subject, AcademicSession
from app.models.results import SubjectResult, TermResult
from app.services.results import grade_for


def _term_key(t) -> str:
    return str(getattr(t.name, "value", t.name))


async def build_term_broadsheet(db: AsyncSession, school_id: str,
                                arm_id: str, term_id: str) -> dict:
    """One term's score sheet for a whole class."""
    arm = await db.get(ClassArm, arm_id)
    klass = await db.get(SchoolClass, arm.class_id) if arm else None
    term = await db.get(Term, term_id)
    session = await db.get(AcademicSession, term.session_id) if term else None
    school = await db.get(School, school_id)
    bands = (school.grading_config or {}).get("bands", []) if school else []

    students = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id == arm_id,
        Student.deleted_at.is_(None)))).scalars().all()

    # every subject result in this arm this term → grid[student][subject] = total
    subs = (await db.execute(select(SubjectResult).where(
        SubjectResult.school_id == school_id,
        SubjectResult.arm_id == arm_id,
        SubjectResult.term_id == term_id))).scalars().all()
    grid: dict[str, dict[str, float]] = defaultdict(dict)
    subject_ids: set[str] = set()
    for sr in subs:
        grid[sr.student_id][sr.subject_id] = sr.total
        subject_ids.add(sr.subject_id)

    # order the subject columns by name; short codes keep the header narrow
    subj_names = {s.id: s.name for s in (await db.execute(select(Subject).where(
        Subject.school_id == school_id,
        Subject.id.in_(subject_ids)))).scalars().all()} if subject_ids else {}
    ordered_subjects = sorted(subject_ids, key=lambda sid: subj_names.get(sid, "").lower())
    subjects = [{"id": sid, "name": subj_names.get(sid, "Unknown")} for sid in ordered_subjects]

    # the overall standing comes from the computed term result
    trs = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == arm_id,
        TermResult.term_id == term_id))).scalars().all()
    by_student = {tr.student_id: tr for tr in trs}

    rows = []
    for s in students:
        tr = by_student.get(s.id)
        cells = grid.get(s.id, {})
        grade = ""
        if tr is not None:
            grade, _ = grade_for(tr.average or 0, bands)
        rows.append({
            "student_id": s.id,
            "name": f"{s.first_name} {s.last_name}",
            "admission_number": s.admission_number,
            "scores": [cells.get(sid) for sid in ordered_subjects],
            "grand_total": tr.grand_total if tr else None,
            "average": tr.average if tr else None,
            "grade": grade,
            "position": tr.overall_position if tr else 0,
            "subjects_count": tr.subjects_count if tr else len(cells),
            "computed": tr is not None,
        })

    # computed students first, ranked by position; the rest alphabetically after
    rows.sort(key=lambda r: (not r["computed"],
                             r["position"] if r["computed"] else 0,
                             r["name"].lower()))

    # per-subject class average, lifted from any SubjectResult (the engine stores
    # the same class_average on every row for a subject) and backfilled by hand
    subj_avg: dict[str, float] = {}
    for sr in subs:
        if sr.subject_id not in subj_avg and sr.class_average:
            subj_avg[sr.subject_id] = round(sr.class_average, 1)
    for sid in ordered_subjects:
        if sid not in subj_avg:
            vals = [grid[st].get(sid) for st in grid if grid[st].get(sid) is not None]
            subj_avg[sid] = round(sum(vals) / len(vals), 1) if vals else None

    computed = [r for r in rows if r["computed"]]
    class_avg = (round(sum(r["average"] for r in computed) / len(computed), 2)
                 if computed else None)

    return {
        "school": {"name": school.name, "address": school.address,
                   "state": school.state, "color": school.primary_color,
                   "logo_url": school.logo_url},
        "class": (klass.name if klass else "") + (f" {arm.name}" if arm else ""),
        "arm_id": arm_id,
        "term": _term_key(term).title() if term else "",
        "session": session.name if session else "",
        "subjects": subjects,
        "subject_averages": [subj_avg.get(sid) for sid in ordered_subjects],
        "rows": rows,
        "class_size": len(students),
        "computed_count": len(computed),
        "class_average": class_avg,
    }
