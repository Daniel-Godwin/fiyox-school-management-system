"""End-of-session promotion — moving a whole school up a year.

This is the single most destructive operation in a school system: it touches
every student at once. So it is built in two halves:

  1. **preview()** — computes exactly what would happen, changing nothing.
     The admin sees who is promoted, who repeats, who graduates, and why.
  2. **commit()** — applies that plan, audited student by student.

The default rule is Nigerian-standard: promote if the year's average reaches
the pass mark; otherwise repeat. The admin can override any individual student
in the preview before committing, because real decisions involve conversations
a computer never sees.

Students in the highest class (no class above them) are *graduated* rather than
promoted: they leave the roll, and their records stay intact for reference.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academics import ClassArm, SchoolClass, Term
from app.models.results import TermResult
from app.models.student import Student

PROMOTE = "promote"
REPEAT = "repeat"
GRADUATE = "graduate"


@dataclass
class Decision:
    student_id: str
    name: str
    admission_number: str
    from_arm_id: str
    from_label: str
    average: float | None
    terms_counted: int
    action: str
    to_arm_id: str | None = None
    to_label: str | None = None
    reason: str = ""


async def _class_ladder(db: AsyncSession, school_id: str) -> list[SchoolClass]:
    rows = (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id,
        SchoolClass.deleted_at.is_(None)))).scalars().all()
    return sorted(rows, key=lambda c: (c.level_order, c.name))


async def build_plan(db: AsyncSession, school_id: str, session_id: str,
                     pass_mark: float = 40.0) -> list[Decision]:
    """What would happen if we promoted now? Computes; changes nothing."""
    ladder = await _class_ladder(db, school_id)
    if not ladder:
        return []
    next_class = {c.id: ladder[i + 1] if i + 1 < len(ladder) else None
                  for i, c in enumerate(ladder)}

    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id,
        ClassArm.deleted_at.is_(None)))).scalars().all()}
    class_names = {c.id: c.name for c in ladder}

    # every arm of the class above, so we can land students somewhere sensible
    arms_by_class: dict[str, list[ClassArm]] = {}
    for a in arms.values():
        arms_by_class.setdefault(a.class_id, []).append(a)
    for lst in arms_by_class.values():
        lst.sort(key=lambda a: a.name)

    # the session's terms — the year's average is the mean of its term averages
    term_ids = [t.id for t in (await db.execute(select(Term).where(
        Term.school_id == school_id, Term.session_id == session_id,
        Term.deleted_at.is_(None)))).scalars().all()]

    results: dict[str, list[float]] = {}
    if term_ids:
        for tr in (await db.execute(select(TermResult).where(
                TermResult.school_id == school_id,
                TermResult.term_id.in_(term_ids)))).scalars().all():
            results.setdefault(tr.student_id, []).append(tr.average)

    students = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.deleted_at.is_(None),
        Student.is_active == True,          # noqa: E712
        Student.current_arm_id.is_not(None)))).scalars().all()

    plan: list[Decision] = []
    for s in students:
        arm = arms.get(s.current_arm_id)
        if not arm:
            continue
        from_label = f"{class_names.get(arm.class_id, '')} {arm.name}".strip()
        marks = results.get(s.id, [])
        average = round(sum(marks) / len(marks), 2) if marks else None

        target_class = next_class.get(arm.class_id)
        d = Decision(student_id=s.id,
                     name=f"{s.first_name} {s.last_name}",
                     admission_number=s.admission_number,
                     from_arm_id=arm.id, from_label=from_label,
                     average=average, terms_counted=len(marks),
                     action=REPEAT)

        if target_class is None:
            d.action = GRADUATE
            d.reason = "Highest class — leaves the school"
        elif average is None:
            d.action = REPEAT
            d.reason = "No results recorded this session"
        elif average >= pass_mark:
            d.action = PROMOTE
            d.reason = f"Session average {average}% ≥ pass mark {pass_mark}%"
            # keep them in the same arm letter where possible (A -> A)
            candidates = arms_by_class.get(target_class.id, [])
            chosen = next((a for a in candidates if a.name == arm.name),
                          candidates[0] if candidates else None)
            if chosen:
                d.to_arm_id = chosen.id
                d.to_label = f"{target_class.name} {chosen.name}"
            else:
                d.action = REPEAT
                d.reason = f"{target_class.name} has no arms — create one first"
        else:
            d.action = REPEAT
            d.reason = f"Session average {average}% < pass mark {pass_mark}%"

        plan.append(d)

    plan.sort(key=lambda d: (d.from_label, d.admission_number))
    return plan
