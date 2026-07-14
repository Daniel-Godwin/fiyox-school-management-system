"""The AI layer.

Two capabilities, both designed so the school is never *dependent* on them:

1. **LLM-written report comments.** The deterministic engine in
   `services/comments.py` remains the default and the fallback — it is free,
   instant, and always available. When ANTHROPIC_API_KEY is configured, the
   admin can ask for a richer, more individual comment that reasons over the
   student's *subject-by-subject* profile ("strong in the sciences, but English
   is holding the average down") rather than the average alone. If the API is
   slow, down, or unfunded, Fiyox silently falls back to the deterministic
   comment: a school must never be unable to print report cards because a
   third-party API had a bad day.

2. **At-risk detection.** Deliberately NOT an LLM. It is a transparent rule
   engine over signals the school already collects — falling average, poor
   attendance, unpaid fees, failing multiple subjects. Every flag carries its
   reasons in plain words, because a head teacher must be able to interrogate
   "why is this child flagged?" and act on it. A black-box risk score would be
   worse than useless here; it would be unaccountable.
"""
import json
import os

import httpx

from app.services.comments import generate_comments

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"


def llm_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------- comments

def _prompt(*, first_name: str, subjects: list[dict], average: float,
            position: int, class_size: int, class_average: float) -> str:
    lines = [f"- {s['subject']}: {s['total']}/100 ({s['grade']}), "
             f"class average {s['class_average']}" for s in subjects]
    return (
        "You are an experienced Nigerian secondary-school form teacher writing "
        "the comment on a student's termly report card.\n\n"
        f"Student's first name: {first_name}\n"
        f"Overall average: {average}%  (class average {class_average}%)\n"
        f"Position: {position} of {class_size}\n"
        "Subject results:\n" + "\n".join(lines) + "\n\n"
        "Write TWO comments as JSON with exactly these keys:\n"
        '  "form_teacher": 2 sentences, max 45 words. Address the specific '
        "pattern across subjects — name a real strength and the subject most "
        "holding them back, and give one concrete instruction. Warm but honest. "
        "Refer to the student by first name.\n"
        '  "principal": 1 short sentence, max 15 words, institutional in tone, '
        "proportionate to the result.\n\n"
        "Be truthful: do not praise a weak result or scold a strong one. "
        "Return ONLY the JSON object, no preamble, no markdown."
    )


async def llm_comments(*, first_name: str, subjects: list[dict], average: float,
                       position: int, class_size: int,
                       class_average: float) -> tuple[str, str, str]:
    """Return (form_teacher, principal, source).

    source is "ai" or "rules" — the caller can tell the admin which they got,
    and the deterministic engine is always the fallback.
    """
    fallback_t, fallback_p = generate_comments(
        first_name=first_name, average=average, position=position,
        class_size=class_size, class_average=class_average)

    if not llm_configured() or not subjects:
        return fallback_t, fallback_p, "rules"

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": _prompt(
                        first_name=first_name, subjects=subjects, average=average,
                        position=position, class_size=class_size,
                        class_average=class_average)}],
                })
        if r.status_code != 200:
            return fallback_t, fallback_p, "rules"

        text = "".join(block.get("text", "")
                       for block in r.json().get("content", [])
                       if block.get("type") == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        teacher = str(data["form_teacher"]).strip()
        principal = str(data["principal"]).strip()
        if not teacher or not principal:
            raise ValueError("empty comment")
        return teacher[:500], principal[:500], "ai"
    except Exception:
        # a school must never be unable to print report cards because an API
        # was slow, down, or out of credit
        return fallback_t, fallback_p, "rules"


# ---------------------------------------------------------------- at-risk

def assess_risk(*, average: float, class_average: float, failing_subjects: int,
                subjects_count: int, attendance_pct: float | None,
                previous_average: float | None,
                owes_fees: bool) -> dict:
    """Which students actually need a teacher's attention?

    Calibration matters more than cleverness here. A register that flags
    everybody is worthless — the head teacher stops reading it, and the child
    who really is drowning gets lost in the noise. So:

    * **The trigger must be academic or attendance.** Unpaid fees alone are NOT
      a reason to flag a child. Early in every term nobody has paid; a top
      student whose father is a week late with the cheque is not "at risk", and
      saying so insults the family and wastes the teacher's time. Fees are
      *context* — they are added to an existing flag (they help explain why a
      child is struggling, and they matter for dropout), but they never raise
      one on their own. The bursar chases debt; this register is for teachers.

    * **A student performing well is not flagged, full stop.** Whatever else is
      true, if a child is passing comfortably and attending, they do not belong
      on a list of children who need intervention.

    * **The bar is a real concern, not a technicality.** "Watch" now means
      something a form teacher would actually act on.
    """
    reasons: list[str] = []
    score = 0

    # ---- academic signals -------------------------------------------------
    if average < 40:
        score += 4
        reasons.append(f"Average of {average}% is below the pass mark")
    elif average < 50:
        score += 2
        reasons.append(f"Average of {average}% is weak")

    if subjects_count and failing_subjects >= max(2, subjects_count // 3):
        score += 2
        reasons.append(f"Failing {failing_subjects} of {subjects_count} subjects")
    elif failing_subjects == 1 and subjects_count:
        # one weak subject is worth a mention, not an alarm
        score += 1
        reasons.append("Failing one subject")

    if class_average and average < class_average - 20:
        score += 1
        reasons.append(
            f"{round(class_average - average, 1)} points below the class average")

    if previous_average is not None:
        drop = round(previous_average - average, 1)
        if drop >= 15:
            score += 3
            reasons.append(f"Average has fallen sharply — down {drop} points since last term")
        elif drop >= 8:
            score += 2
            reasons.append(f"Average has fallen {drop} points since last term")

    # ---- attendance -------------------------------------------------------
    if attendance_pct is not None:
        if attendance_pct < 60:
            score += 4
            reasons.append(f"Attendance is only {attendance_pct}% — the child is barely in school")
        elif attendance_pct < 75:
            score += 3
            reasons.append(f"Attendance is poor at {attendance_pct}%")
        elif attendance_pct < 85:
            score += 1
            reasons.append(f"Attendance of {attendance_pct}% needs watching")

    # A child who is doing fine academically and turning up is not "at risk",
    # whatever the ledger says. Leave them alone.
    if not reasons:
        return {"level": "none", "score": 0, "reasons": [],
                "recommended_action": "", "fees_note": None}

    # ---- fees: context for an existing concern, never a trigger -----------
    fees_note = None
    if owes_fees:
        fees_note = ("Fees are also outstanding — this may be part of the picture, "
                     "and should be raised gently with the parents.")

    if score >= 6:
        level = "high"
    elif score >= 3:
        level = "moderate"
    else:
        level = "watch"

    actions = {
        "high": "Invite the parents this week; agree a written recovery plan.",
        "moderate": "Speak to the student and inform the parents at the next PTA.",
        "watch": "Keep an eye on this student; check in with subject teachers.",
    }

    return {"level": level, "score": score, "reasons": reasons,
            "recommended_action": actions[level], "fees_note": fees_note}
