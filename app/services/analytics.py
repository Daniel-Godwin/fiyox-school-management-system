"""School analytics — one aggregated overview for the dashboard.

build_overview() rolls up four areas for a term in a single pass:

  * enrolment  — how many students, by class and by gender
  * academics  — computed results, overall average, pass rate, grade spread,
                 top students, and how many sit below the pass mark
  * finance    — expected vs collected fees, outstanding, debtor count
  * cbt        — published tests, sittings, submissions, average score

It takes a list of school_ids so the same code serves a single school (admin /
principal) and a platform-wide roll-up (super admin: every school combined).
Queries are batched — no per-row round trips — so the whole overview is one
cheap call.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student
from app.models.academics import ClassArm, SchoolClass
from app.models.results import TermResult, SubjectResult
from app.models.fees import Invoice, Payment
from app.models.cbt import CBTExam, CBTAttempt, EXAM_PUBLISHED, ATTEMPT_SUBMITTED

# Nigerian standard: an average at or above this is a pass.
PASS_MARK = 40.0
# WAEC-style band order, so grade distribution reads best -> worst.
GRADE_ORDER = ["A1", "B2", "B3", "C4", "C5", "C6", "D7", "E8", "F9"]


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


async def build_overview(db: AsyncSession, school_ids: list[str],
                         term_id: str | None) -> dict:
    if not school_ids:
        school_ids = []

    # ---------- enrolment ----------
    students = list((await db.execute(select(Student).where(
        Student.school_id.in_(school_ids),
        Student.deleted_at.is_(None)))).scalars().all())
    active = [s for s in students if s.is_active]

    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id.in_(school_ids)))).scalars().all()}
    classes = {c.id: c for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id.in_(school_ids)))).scalars().all()}

    by_gender = {"male": 0, "female": 0}
    class_counts: dict[str, dict] = {}          # class name -> {count, order}
    for s in active:
        g = str(s.gender).split(".")[-1].lower()
        if g in by_gender:
            by_gender[g] += 1
        arm = arms.get(s.current_arm_id) if s.current_arm_id else None
        klass = classes.get(arm.class_id) if arm else None
        name = klass.name if klass else "Unassigned"
        order = klass.level_order if klass else 999
        slot = class_counts.setdefault(name, {"count": 0, "order": order})
        slot["count"] += 1
    by_class = [{"class": n, "count": v["count"]}
                for n, v in sorted(class_counts.items(), key=lambda kv: (kv[1]["order"], kv[0]))]

    enrolment = {
        "total_students": len(students),
        "active": len(active),
        "by_gender": by_gender,
        "by_class": by_class,
    }

    # ---------- academics (needs a term) ----------
    academics = {
        "computed_results": 0, "overall_average": None, "pass_rate": None,
        "below_pass": 0, "grade_distribution": [], "top_students": [],
    }
    if term_id:
        trs = list((await db.execute(select(TermResult).where(
            TermResult.school_id.in_(school_ids),
            TermResult.term_id == term_id))).scalars().all())
        averages = [t.average for t in trs if t.average is not None]
        passed = [a for a in averages if a >= PASS_MARK]
        academics["computed_results"] = len(trs)
        academics["overall_average"] = _mean(averages)
        academics["pass_rate"] = round(len(passed) / len(averages) * 100, 1) if averages else None
        academics["below_pass"] = len(averages) - len(passed)

        # grade spread across every subject result this term
        grade_rows = (await db.execute(
            select(SubjectResult.grade, func.count()).where(
                SubjectResult.school_id.in_(school_ids),
                SubjectResult.term_id == term_id).group_by(SubjectResult.grade))).all()
        counts = {g: n for g, n in grade_rows if g}
        academics["grade_distribution"] = [
            {"grade": g, "count": counts.get(g, 0)}
            for g in GRADE_ORDER if counts.get(g, 0)]

        # top students by overall average
        names = {s.id: s for s in students}
        top = sorted(trs, key=lambda t: (t.average or 0), reverse=True)[:5]
        top_out = []
        for t in top:
            st = names.get(t.student_id)
            arm = arms.get(t.arm_id)
            klass = classes.get(arm.class_id) if arm else None
            label = f"{klass.name} {arm.name}".strip() if (klass and arm) else ""
            top_out.append({
                "name": f"{st.first_name} {st.last_name}" if st else "Unknown",
                "average": t.average, "class_label": label})
        academics["top_students"] = top_out

    # ---------- finance (needs a term) ----------
    finance = {"expected": 0.0, "collected": 0.0, "collection_rate": None,
               "outstanding": 0.0, "debtors": 0}
    if term_id:
        invoices = list((await db.execute(select(Invoice).where(
            Invoice.school_id.in_(school_ids), Invoice.term_id == term_id,
            Invoice.deleted_at.is_(None)))).scalars().all())
        inv_ids = [i.id for i in invoices]
        paid_by_inv: dict[str, float] = {}
        if inv_ids:
            for iid, total in (await db.execute(
                    select(Payment.invoice_id, func.sum(Payment.amount)).where(
                        Payment.invoice_id.in_(inv_ids),
                        Payment.deleted_at.is_(None)).group_by(Payment.invoice_id))).all():
                paid_by_inv[iid] = float(total or 0)

        expected = collected = outstanding = 0.0
        debtors = 0
        for inv in invoices:
            due = inv.amount - inv.discount
            paid = paid_by_inv.get(inv.id, 0.0)
            expected += due
            collected += (min(paid, due) if due > 0 else paid)
            balance = round(due - paid, 2)
            if balance > 0:
                outstanding += balance
                debtors += 1
        finance = {
            "expected": round(expected, 2), "collected": round(collected, 2),
            "collection_rate": round(collected / expected * 100, 1) if expected else None,
            "outstanding": round(outstanding, 2), "debtors": debtors,
        }

    # ---------- CBT ----------
    cbt = {"published_tests": 0, "sittings": 0, "submitted": 0, "average_percent": None}
    exam_filter = [CBTExam.school_id.in_(school_ids), CBTExam.deleted_at.is_(None)]
    if term_id:
        exam_filter.append(CBTExam.term_id == term_id)
    exams = list((await db.execute(select(CBTExam).where(*exam_filter))).scalars().all())
    published = [e for e in exams if e.status == EXAM_PUBLISHED]
    exam_ids = [e.id for e in exams]
    if exam_ids:
        attempts = list((await db.execute(select(CBTAttempt).where(
            CBTAttempt.exam_id.in_(exam_ids)))).scalars().all())
        submitted = [a for a in attempts if a.status == ATTEMPT_SUBMITTED and a.max_score]
        pct = [a.score / a.max_score * 100 for a in submitted]
        cbt = {
            "published_tests": len(published),
            "sittings": len(attempts),
            "submitted": len(submitted),
            "average_percent": _mean(pct),
        }

    return {
        "enrolment": enrolment,
        "academics": academics,
        "finance": finance,
        "cbt": cbt,
    }
