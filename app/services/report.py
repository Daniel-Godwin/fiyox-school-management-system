"""Assemble one student's terminal report into a plain dict.

Shared by the on-screen/parent JSON endpoint and the PDF generator so both
always show identical numbers.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.school import School
from app.models.student import Student
from app.models.academics import Term, ClassArm, SchoolClass, Subject
from app.models.results import AssessmentComponent, SubjectResult, TermResult


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
            "position": sr.subject_position,
        })

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
        "subjects": rows,
        "summary": {"grand_total": tr.grand_total, "average": tr.average,
                    "subjects_count": tr.subjects_count,
                    "position": tr.overall_position, "class_size": tr.class_size,
                    "class_average": tr.class_average},
        "affective": tr.affective,
        "comments": {"form_teacher": tr.form_teacher_comment,
                     "principal": tr.principal_comment},
        "published": tr.is_published,
    }
