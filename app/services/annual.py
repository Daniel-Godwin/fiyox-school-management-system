"""Cumulative annual (end-of-session) results.

The termly engine (services/results.py) snapshots each term into SubjectResult
and TermResult. This assembles the three terms of a session into one cumulative
record per student: each subject's term totals and their cumulative, the
cumulative grade, the annual average, and the annual position in the class.

A subject's cumulative is the mean of the term totals it has (each already out
of 100), so it is comparable to the grading bands. The annual average is the
mean of the term averages. Positions use the same competition ranking as the
termly engine (1, 2, 2, 4).
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.school import School
from app.models.student import Student
from app.models.academics import (
    Term, ClassArm, SchoolClass, Subject, AcademicSession,
)
from app.models.results import SubjectResult, TermResult
from app.services.results import grade_for, rank

TERM_ORDER = {"first": 1, "second": 2, "third": 3}


def _term_key(t) -> str:
    return str(getattr(t.name, "value", t.name))


async def session_terms(db: AsyncSession, school_id: str, session_id: str):
    terms = (await db.execute(select(Term).where(
        Term.school_id == school_id,
        Term.session_id == session_id))).scalars().all()
    return sorted(terms, key=lambda t: TERM_ORDER.get(_term_key(t), 9))


def _mean(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


async def build_annual_broadsheet(db: AsyncSession, school_id: str,
                                  arm_id: str, session_id: str) -> dict:
    """The class's cumulative standings for a session."""
    terms = await session_terms(db, school_id, session_id)
    term_ids = [t.id for t in terms]
    arm = await db.get(ClassArm, arm_id)
    klass = await db.get(SchoolClass, arm.class_id) if arm else None
    session = await db.get(AcademicSession, session_id)

    students = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id == arm_id,
        Student.deleted_at.is_(None)))).scalars().all()

    trs = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == arm_id,
        TermResult.term_id.in_(term_ids)))).scalars().all() if term_ids else []
    by_student: dict[str, dict[str, float]] = defaultdict(dict)
    for r in trs:
        by_student[r.student_id][r.term_id] = r.average

    def cum(sid: str) -> float:
        return _mean([by_student.get(sid, {}).get(t) for t in term_ids]) or 0.0

    # rank only students who have at least one term computed
    rankable = [(s.id, cum(s.id)) for s in students
                if any(t in by_student.get(s.id, {}) for t in term_ids)]
    positions = rank(rankable)

    rows = []
    for s in students:
        avgs = by_student.get(s.id, {})
        counted = [t for t in term_ids if t in avgs]
        rows.append({
            "student_id": s.id,
            "name": f"{s.first_name} {s.last_name}",
            "admission_number": s.admission_number,
            "per_term": [avgs.get(t) for t in term_ids],
            "cumulative_average": cum(s.id) if counted else None,
            "terms_counted": len(counted),
            "position": positions.get(s.id, 0),
            "computed": bool(counted),
        })
    # best cumulative first, uncomputed students last
    rows.sort(key=lambda r: (r["cumulative_average"] is None,
                             -(r["cumulative_average"] or 0)))

    return {
        "session": session.name if session else "",
        "session_id": session_id,
        "class": (klass.name if klass else "") + (f" {arm.name}" if arm else ""),
        "arm_id": arm_id,
        "terms": [_term_key(t).title() for t in terms],
        "terms_in_session": len(terms),
        "class_size": len(students),
        "rows": rows,
    }


async def build_annual_report_data(db: AsyncSession, school_id: str,
                                   student_id: str, session_id: str) -> dict | None:
    """One student's full cumulative annual report."""
    student = await db.get(Student, student_id)
    if not student or student.school_id != school_id:
        return None
    arm = await db.get(ClassArm, student.current_arm_id) if student.current_arm_id else None
    if not arm:
        return None
    klass = await db.get(SchoolClass, arm.class_id)
    school = await db.get(School, school_id)
    session = await db.get(AcademicSession, session_id)
    bands = (school.grading_config or {}).get("bands", [])

    terms = await session_terms(db, school_id, session_id)
    term_ids = [t.id for t in terms]
    if not term_ids:
        return None

    subj_names = {s.id: s.name for s in (await db.execute(select(Subject).where(
        Subject.school_id == school_id))).scalars().all()}

    # every subject result in the arm for the session -> grid[student][subject][term] = total
    subs = (await db.execute(select(SubjectResult).where(
        SubjectResult.school_id == school_id,
        SubjectResult.arm_id == arm.id,
        SubjectResult.term_id.in_(term_ids)))).scalars().all()
    grid: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for sr in subs:
        grid[sr.student_id][sr.subject_id][sr.term_id] = sr.total

    def subj_cum(termmap: dict[str, float]) -> float | None:
        return _mean([termmap.get(t) for t in term_ids])

    subject_rows = []
    for subj_id, termmap in grid.get(student_id, {}).items():
        # rank this subject across every student who sat it
        pairs = []
        for sid, smap in grid.items():
            if subj_id in smap:
                c = subj_cum(smap[subj_id])
                if c is not None:
                    pairs.append((sid, c))
        pos = rank(pairs)
        my_cum = subj_cum(termmap)
        grade, remark = grade_for(my_cum or 0, bands)
        subject_rows.append({
            "subject": subj_names.get(subj_id, "Unknown"),
            "per_term": [termmap.get(t) for t in term_ids],
            "cumulative": my_cum,
            "grade": grade,
            "remark": remark,
            "position": pos.get(student_id, 0),
        })
    subject_rows.sort(key=lambda r: r["subject"])

    # overall: term averages, cumulative average, annual position
    trs = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == arm.id,
        TermResult.term_id.in_(term_ids)))).scalars().all()
    by_student: dict[str, dict[str, float]] = defaultdict(dict)
    comments_by_term: dict[str, TermResult] = {}
    for r in trs:
        by_student[r.student_id][r.term_id] = r.average
        if r.student_id == student_id:
            comments_by_term[r.term_id] = r

    def cum_avg(sid: str) -> float:
        return _mean([by_student.get(sid, {}).get(t) for t in term_ids]) or 0.0

    rankable = [(sid, cum_avg(sid)) for sid in by_student
                if any(t in by_student[sid] for t in term_ids)]
    positions = rank(rankable)
    mine = by_student.get(student_id, {})
    counted = [t for t in term_ids if t in mine]
    annual_avg = cum_avg(student_id) if counted else None
    annual_grade, annual_remark = grade_for(annual_avg or 0, bands) if counted else ("", "")

    # the final term's comments stand as the session's closing remarks
    last_tr = None
    for t in reversed(terms):
        if t.id in comments_by_term:
            last_tr = comments_by_term[t.id]
            break

    return {
        "school": {"name": school.name, "address": school.address,
                   "state": school.state, "color": school.primary_color,
                   "logo_url": school.logo_url, "signature_url": school.signature_url,
                   "stamp_url": school.stamp_url, "principal_name": school.principal_name},
        "student": {"name": f"{student.first_name} {student.last_name}",
                    "admission_number": student.admission_number,
                    "class": (klass.name if klass else "") + (f" {arm.name}" if arm else "")},
        "session": session.name if session else "",
        "terms": [_term_key(t).title() for t in terms],
        "subjects": subject_rows,
        "summary": {
            "cumulative_average": annual_avg,
            "grade": annual_grade,
            "remark": annual_remark,
            "position": positions.get(student_id, 0),
            "class_size": len(by_student),
            "terms_counted": len(counted),
            "terms_in_session": len(terms),
            "per_term_average": [mine.get(t) for t in term_ids],
        },
        "comments": {
            "form_teacher": last_tr.form_teacher_comment if last_tr else "",
            "principal": last_tr.principal_comment if last_tr else "",
        },
    }
