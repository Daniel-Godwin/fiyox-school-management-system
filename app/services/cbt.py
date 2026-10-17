"""CBT auto-grading.

Every supported question type is objective, so a sitting is graded the instant
it is submitted — no human marking step. Grading is all-or-nothing per question:
a multi-select question awards its marks only when the chosen set matches the key
exactly. Short answers are matched case- and whitespace-insensitively against a
list of accepted strings.
"""
from app.models.cbt import (
    CBTQuestion, Q_SINGLE, Q_MULTIPLE, Q_BOOLEAN, Q_SHORT,
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
