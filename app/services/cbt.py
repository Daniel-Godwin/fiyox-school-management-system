"""CBT auto-grading.

Every supported question type is objective, so a sitting is graded the instant
it is submitted — no human marking step. Grading is all-or-nothing per question:
a multi-select question awards its marks only when the chosen set matches the key
exactly. Short answers are matched case- and whitespace-insensitively against a
list of accepted strings.
"""
import random

from app.models.cbt import (
    CBTQuestion, Q_SINGLE, Q_MULTIPLE, Q_BOOLEAN, Q_SHORT,
    DIFFICULTIES, DEFAULT_DIFFICULTY_RATIO,
)


def _norm(s) -> str:
    """Normalise a short answer: trim, lower-case, collapse inner whitespace."""
    return " ".join(str(s).strip().lower().split())


def is_correct(q: CBTQuestion, answer) -> bool:
    """Did `answer` (a student's response) match this question's key?"""
    key = q.correct
    if answer is None:
        return False

    if q.type == Q_SINGLE:
        return str(answer) == str(key)

    if q.type == Q_MULTIPLE:
        if not isinstance(answer, (list, tuple)):
            return False
        return set(map(str, answer)) == set(map(str, key or []))

    if q.type == Q_BOOLEAN:
        # accept real bools and the strings "true"/"false"
        a = answer if isinstance(answer, bool) else _norm(answer) in ("true", "1", "yes")
        return bool(a) == bool(key)

    if q.type == Q_SHORT:
        accepted = {_norm(x) for x in (key or [])}
        return _norm(answer) in accepted

    return False


def grade(questions: list[CBTQuestion], answers: dict) -> tuple[float, float, dict]:
    """Return (score, max_score, breakdown).

    breakdown maps question_id -> {"correct": bool, "marks": awarded, "max": q.marks}.
    Unanswered questions score 0 but still appear, so the breakdown always covers
    the whole paper.
    """
    score = 0.0
    max_score = 0.0
    breakdown: dict = {}
    for q in questions:
        max_score += q.marks
        ok = is_correct(q, answers.get(q.id))
        awarded = q.marks if ok else 0.0
        score += awarded
        breakdown[q.id] = {"correct": ok, "marks": awarded, "max": q.marks}
    return score, max_score, breakdown


def student_view(q: CBTQuestion) -> dict:
    """A question as a sitting student may see it — never includes the answer key.

    Boolean questions carry no stored options, so synthesise True/False choices
    the front end can render uniformly with the other choice types.
    """
    options = q.options or []
    if q.type == Q_BOOLEAN:
        options = [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}]
    return {
        "id": q.id,
        "type": q.type,
        "text": q.text,
        "marks": q.marks,
        "options": [{"id": o.get("id"), "text": o.get("text")} for o in options],
    }


# --------------------------------------------------------------------------
# question-bank selection + difficulty balancing
# --------------------------------------------------------------------------
def difficulty_counts(pool_size: int, ratio: dict | None) -> dict:
    """Split pool_size across easy/medium/hard by percentage, using
    largest-remainder rounding so the parts always sum exactly to pool_size."""
    r = ratio or DEFAULT_DIFFICULTY_RATIO
    total = sum(float(r.get(d, 0)) for d in DIFFICULTIES) or 1.0
    raw = {d: pool_size * float(r.get(d, 0)) / total for d in DIFFICULTIES}
    base = {d: int(raw[d]) for d in DIFFICULTIES}
    leftover = pool_size - sum(base.values())
    # hand the remaining slots to the largest fractional parts
    order = sorted(DIFFICULTIES, key=lambda d: raw[d] - base[d], reverse=True)
    for d in order[:leftover]:
        base[d] += 1
    return base


def bank_can_fill(counts_by_diff: dict, pool_size: int, ratio: dict | None) -> tuple[bool, str]:
    """Publish-time guard. The per-sitting draw (select_balanced) backfills
    across difficulties, so a pool can be filled whenever the bank holds at
    least pool_size active questions overall. An uneven difficulty mix is
    balanced as far as it can be and then topped up from the rest — it does
    not block publishing."""
    if pool_size <= 0:
        return False, "Set how many questions each sitting should draw."
    total = sum(int(counts_by_diff.get(d, 0)) for d in DIFFICULTIES)
    if total < pool_size:
        need = pool_size - total
        return False, (f"The bank has {total} question(s) for this subject but "
                       f"the exam needs {pool_size}. Add {need} more.")
    return True, ""


def select_balanced(bank: list, pool_size: int, ratio: dict | None, rng=None) -> list:
    """Draw a balanced, randomly-shuffled subset of bank questions for one
    sitting. If a difficulty bucket is short it backfills from the rest, so a
    student always receives pool_size questions even on imperfect banks."""
    rng = rng or random
    want = difficulty_counts(pool_size, ratio)
    buckets = {d: [q for q in bank if getattr(q, "difficulty", None) == d]
               for d in DIFFICULTIES}
    chosen: list = []
    shortfall = 0
    for d in DIFFICULTIES:
        take = min(want[d], len(buckets[d]))
        chosen.extend(rng.sample(buckets[d], take))
        shortfall += want[d] - take
    if shortfall > 0:
        picked = {q.id for q in chosen}
        leftover = [q for q in bank if q.id not in picked]
        rng.shuffle(leftover)
        chosen.extend(leftover[:shortfall])
    rng.shuffle(chosen)
    return chosen
