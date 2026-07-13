"""Result computation — the core the whole product's credibility rests on.

Given raw score entries for an arm + term, it computes each subject's total,
grade, class average and subject position, then each student's grand total,
average and overall position. Uses competition ranking (1, 2, 2, 4) for ties.
"""
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.school import School
from app.models.student import Student
from app.models.results import (
    AssessmentComponent, ScoreEntry, SubjectResult, TermResult,
)


def grade_for(total: float, bands: list[dict]) -> tuple[str, str]:
    """Return (grade, remark) for a total, using bands sorted high-to-low by min."""
    for band in sorted(bands, key=lambda b: b["min"], reverse=True):
        if total >= band["min"]:
            return band["grade"], band["remark"]
    return "F9", "Fail"


def rank(pairs: list[tuple[str, float]]) -> dict[str, int]:
    """Competition ranking. pairs = [(id, score)]. Higher score = better position."""
    ordered = sorted(pairs, key=lambda p: p[1], reverse=True)
    positions: dict[str, int] = {}
    last_score = None
    last_pos = 0
    for idx, (key, score) in enumerate(ordered, start=1):
        if score != last_score:
            last_pos = idx
            last_score = score
        positions[key] = last_pos
    return positions


async def compute_term(db: AsyncSession, school_id: str, arm_id: str, term_id: str) -> dict:
    school = await db.get(School, school_id)
    bands = (school.grading_config or {}).get("bands", [])

    # component id -> name, for the report-card breakdown
    comps = (await db.execute(
        select(AssessmentComponent).where(AssessmentComponent.school_id == school_id)
    )).scalars().all()
    comp_name = {c.id: c.name for c in comps}

    # students in this arm
    students = (await db.execute(
        select(Student).where(Student.school_id == school_id,
                              Student.current_arm_id == arm_id,
                              Student.deleted_at.is_(None),
                              Student.is_active == True)  # noqa: E712
    )).scalars().all()
    student_ids = [s.id for s in students]
    if not student_ids:
        return {"students": 0, "subjects": 0}

    # all raw scores for this arm + term
    entries = (await db.execute(
        select(ScoreEntry).where(ScoreEntry.school_id == school_id,
                                 ScoreEntry.arm_id == arm_id,
                                 ScoreEntry.term_id == term_id)
    )).scalars().all()

    # aggregate: totals[student][subject] = sum; breakdown[student][subject] = {comp: score}
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    breakdown: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    subjects: set[str] = set()
    for e in entries:
        totals[e.student_id][e.subject_id] += e.score
        breakdown[e.student_id][e.subject_id][comp_name.get(e.component_id, "?")] = e.score
        subjects.add(e.subject_id)

    # subject position + class average per subject
    subj_positions: dict[str, dict[str, int]] = {}
    subj_average: dict[str, float] = {}
    for subj in subjects:
        pairs = [(sid, totals[sid].get(subj, 0.0)) for sid in student_ids
                 if subj in totals[sid]]
        subj_positions[subj] = rank(pairs)
        subj_average[subj] = round(sum(p[1] for p in pairs) / len(pairs), 2) if pairs else 0.0

    # remember any human-written comments before wiping — recomputing a term
    # must never destroy what a form teacher or principal actually wrote
    previous_comments: dict[str, tuple[str, str]] = {}
    existing_trs = (await db.execute(
        select(TermResult).where(TermResult.school_id == school_id,
                                 TermResult.arm_id == arm_id,
                                 TermResult.term_id == term_id)
    )).scalars().all()
    for tr in existing_trs:
        if tr.comments_edited:
            previous_comments[tr.student_id] = (tr.form_teacher_comment,
                                                tr.principal_comment)

    # wipe old computed rows for this arm+term, then rewrite
    for model in (SubjectResult, TermResult):
        old = (await db.execute(
            select(model).where(model.school_id == school_id,
                                model.arm_id == arm_id, model.term_id == term_id)
        )).scalars().all()
        for row in old:
            await db.delete(row)
    await db.flush()

    # per-student grand totals for overall ranking
    grand = {sid: sum(totals[sid].values()) for sid in student_ids if sid in totals}
    overall_positions = rank(list(grand.items()))
    term_results: dict[str, TermResult] = {}

    for sid in student_ids:
        if sid not in totals:
            continue
        subj_count = 0
        for subj, tot in totals[sid].items():
            g, remark = grade_for(tot, bands)
            db.add(SubjectResult(
                school_id=school_id, student_id=sid, subject_id=subj,
                arm_id=arm_id, term_id=term_id, total=round(tot, 2),
                grade=g, remark=remark,
                subject_position=subj_positions[subj].get(sid, 0),
                class_average=subj_average[subj],
                breakdown=breakdown[sid][subj],
            ))
            subj_count += 1

        gt = round(grand[sid], 2)
        term_results[sid] = TermResult(
            school_id=school_id, student_id=sid, arm_id=arm_id, term_id=term_id,
            grand_total=gt,
            average=round(gt / subj_count, 2) if subj_count else 0.0,
            subjects_count=subj_count, class_size=len(grand),
            overall_position=overall_positions.get(sid, 0),
        )
        db.add(term_results[sid])

    # ---- auto-generated comments (class-relative) ----
    # Preserve any comment a human already wrote for this student+term.
    from app.services.comments import generate_comments
    from app.models.student import Student as _Student

    averages = [tr.average for tr in term_results.values()]
    class_avg = round(sum(averages) / len(averages), 2) if averages else 0.0

    for sid, tr in term_results.items():
        prior = previous_comments.get(sid, ("", ""))
        student = await db.get(_Student, sid)
        first = student.first_name if student else "The student"
        auto_teacher, auto_principal = generate_comments(
            first_name=first, average=tr.average,
            position=tr.overall_position, class_size=tr.class_size,
            class_average=class_avg)
        # human edits win; blanks get the generated text
        tr.form_teacher_comment = prior[0] or auto_teacher
        tr.principal_comment = prior[1] or auto_principal
        tr.comments_edited = bool(prior[0] or prior[1])
        tr.class_average = class_avg

    await db.commit()
    return {"students": len(grand), "subjects": len(subjects),
            "class_average": class_avg}
