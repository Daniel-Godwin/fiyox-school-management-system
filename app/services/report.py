"""Assemble one student's terminal report into a plain dict.

Shared by the on-screen/parent JSON endpoint and the PDF generator so both
always show identical numbers.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.school import School
from app.models.student import Student
from app.models.academics import Term, ClassArm, SchoolClass, Subject, AcademicSession
from app.models.results import AssessmentComponent, SubjectResult, TermResult


def _grading_key(bands: list[dict]) -> list[dict]:
    """Turn the school's grade bands into a printable key with ranges, e.g.
    A1 75-100 Excellent, B2 70-74 Very Good, ... (highest band first)."""
    hi_low = sorted(bands, key=lambda b: b["min"], reverse=True)
    key = []
    for i, b in enumerate(hi_low):
        upper = 100 if i == 0 else hi_low[i - 1]["min"] - 1
        key.append({"grade": b["grade"], "min": b["min"], "max": upper,
                    "remark": b.get("remark", "")})
    return key


async def build_report_data(db: AsyncSession, school_id: str,
                            student_id: str, term_id: str) -> dict | None:
    student = await db.get(Student, student_id)
    if not student or student.school_id != school_id:
        return None
    tr = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.student_id == student_id,
        TermResult.term_id == term_id))).scalars().first()
    if not tr:
        return None

    school = await db.get(School, school_id)
    term = await db.get(Term, term_id)
    arm = await db.get(ClassArm, student.current_arm_id) if student.current_arm_id else None
    klass = await db.get(SchoolClass, arm.class_id) if arm else None

    components = (await db.execute(select(AssessmentComponent).where(
        AssessmentComponent.school_id == school_id).order_by(
        AssessmentComponent.sequence))).scalars().all()

    subs = (await db.execute(select(SubjectResult).where(
        SubjectResult.school_id == school_id,
        SubjectResult.student_id == student_id,
        SubjectResult.term_id == term_id))).scalars().all()

    subj_names = {s.id: (s.name, s.code) for s in (await db.execute(
        select(Subject).where(Subject.school_id == school_id))).scalars().all()}

    rows = []
    for sr in sorted(subs, key=lambda r: r.subject_position):
        name, _ = subj_names.get(sr.subject_id, ("Unknown", None))
        rows.append({
            "subject": name,
            "breakdown": sr.breakdown,
            "total": sr.total,
            "grade": sr.grade,
            "remark": sr.remark,
            "class_average": sr.class_average,
            "class_highest": sr.class_highest,
            "class_lowest": sr.class_lowest,
            "position": sr.subject_position,
        })

    # ---- cumulative session result (third term only) ----
    # On the final term's card, show how the student did across the whole
    # session: each term's average, the cumulative average, and the cumulative
    # position in the class. Computed live from the three terms' results.
    cumulative = None
    term_name = str(getattr(term.name, "value", term.name)) if term else ""
    if term and term_name == "third" and arm:
        session_terms = (await db.execute(select(Term).where(
            Term.school_id == school_id,
            Term.session_id == term.session_id))).scalars().all()
        order = {"first": 1, "second": 2, "third": 3}
        session_terms.sort(key=lambda t: order.get(
            str(getattr(t.name, "value", t.name)), 9))
        term_ids = [t.id for t in session_terms]

        # every term result in this arm for the session, grouped by student
        all_trs = (await db.execute(select(TermResult).where(
            TermResult.school_id == school_id,
            TermResult.arm_id == arm.id,
            TermResult.term_id.in_(term_ids)))).scalars().all()
        by_student: dict[str, dict[str, float]] = {}
        for r in all_trs:
            by_student.setdefault(r.student_id, {})[r.term_id] = r.average

        def cum_avg(avgs: dict[str, float]) -> float:
            vals = [avgs[t] for t in term_ids if t in avgs]
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        # rank every student in the arm by cumulative average
        ranking = sorted(((sid, cum_avg(a)) for sid, a in by_student.items()),
                         key=lambda x: x[1], reverse=True)
        position = next((i + 1 for i, (sid, _) in enumerate(ranking)
                         if sid == student_id), 0)

        mine = by_student.get(student_id, {})
        per_term = [{
            "term": str(getattr(t.name, "value", t.name)).title(),
            "average": mine.get(t.id),
        } for t in session_terms]

        # promotion outcome (Nigerian standard: promote if the year's average
        # reaches the pass mark; the student in the highest class graduates). The
        # admin's promotion run is authoritative; this is the card's statement.
        PASS_MARK = 40.0
        my_cum = cum_avg(mine)
        promotion = None
        if klass:
            ladder = sorted((await db.execute(select(SchoolClass).where(
                SchoolClass.school_id == school_id,
                SchoolClass.deleted_at.is_(None)))).scalars().all(),
                key=lambda c: (c.level_order, c.name))
            ids = [c.id for c in ladder]
            idx = ids.index(klass.id) if klass.id in ids else -1
            nxt = ladder[idx + 1] if 0 <= idx < len(ladder) - 1 else None
            if not mine:
                promotion = {"action": "pending", "label": "Awaiting complete results"}
            elif nxt is None:
                promotion = {"action": "graduate", "label": "Graduates — completed the highest class"}
            elif my_cum >= PASS_MARK:
                promotion = {"action": "promote", "label": f"Promoted to {nxt.name}"}
            else:
                promotion = {"action": "repeat", "label": f"To repeat {klass.name}"}

        cumulative = {
            "session": sessn.name if (sessn := await db.get(
                AcademicSession, term.session_id)) else "",
            "per_term": per_term,
            "cumulative_average": cum_avg(mine),
            "cumulative_position": position,
            "class_size": len(by_student),
            "promotion": promotion,
        }

    # attendance for the term — parents look for this as closely as the marks.
    # Bounded by the term's dates when the school has set them; otherwise every
    # record for the student is counted.
    from app.models.attendance import Attendance, AttendanceStatus
    att_stmt = select(Attendance).where(Attendance.school_id == school_id,
                                        Attendance.student_id == student_id)
    if term and term.start_date:
        att_stmt = att_stmt.where(Attendance.date >= term.start_date)
    if term and term.end_date:
        att_stmt = att_stmt.where(Attendance.date <= term.end_date)
    att_rows = (await db.execute(att_stmt)).scalars().all()

    counts = {s.value: 0 for s in AttendanceStatus}
    for r in att_rows:
        key = r.status.value if hasattr(r.status, "value") else str(r.status)
        counts[key] = counts.get(key, 0) + 1
    days = len(att_rows)
    present_like = counts.get("present", 0) + counts.get("late", 0)
    attendance = {
        "days_recorded": days,
        "present": counts.get("present", 0),
        "absent": counts.get("absent", 0),
        "late": counts.get("late", 0),
        "excused": counts.get("excused", 0),
        # the figure a parent actually reads
        "percentage": round(present_like / days * 100, 1) if days else None,
    }

    return {
        "school": {"name": school.name, "address": school.address,
                   "state": school.state, "color": school.primary_color,
                   "logo_url": school.logo_url,
                   "signature_url": school.signature_url,
                   "stamp_url": school.stamp_url,
                   "principal_name": school.principal_name},
        "student": {"name": f"{student.first_name} {student.last_name}",
                    "admission_number": student.admission_number,
                    "class": (klass.name if klass else "") + (f" {arm.name}" if arm else "")},
        "term": {"name": term.name if term else "",
                 "next_term_begins": str(term.next_term_begins) if term and term.next_term_begins else None},
        "components": [{"name": c.name, "max": c.max_score} for c in components],
        "grading_key": _grading_key((school.grading_config or {}).get("bands", [])),
        "subjects": rows,
        "summary": {"grand_total": tr.grand_total, "average": tr.average,
                    "subjects_count": tr.subjects_count,
                    "position": tr.overall_position, "class_size": tr.class_size,
                    "class_average": tr.class_average},
        "attendance": attendance,
        "cumulative": cumulative,
        "affective": tr.affective,
        "psychomotor": tr.psychomotor,
        "comments": {"form_teacher": tr.form_teacher_comment,
                     "principal": tr.principal_comment},
        "published": tr.is_published,
    }
