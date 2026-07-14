"""Report-card comments.

Two principles:

1. **Position drives the message, not just the raw average.** A 64% that is 3rd
   in a strong class deserves praise; the same 64% that is 20th of 22 deserves a
   warning. So the comment is chosen from a blend of the student's *standing*
   (percentile in the class) and their *absolute* mark — because both matter to
   a Nigerian parent: "how did my child do" and "how did my child do compared to
   the others".

2. **One coherent voice.** The old version stapled a relative clause onto a
   band sentence and could contradict itself ("A fair performance ... Among the
   very best in the class"). Each comment is now a single composed sentence pair
   that agrees with itself.

Teacher = specific, about the child's work and what to do next.
Principal = short, institutional, and clearly weightier at the extremes.

Generated on compute; a human edit always wins (see comments_edited).
No LLM required. Phase 4 can swap one in behind generate_comments().
"""
import random

# ---------------------------------------------------------------- tiers

TOP = "top"            # 1st, or top ~10% — outstanding
UPPER = "upper"        # comfortably above the class
MIDDLE = "middle"      # around the class average
LOWER = "lower"        # below the class, but passing
BOTTOM = "bottom"      # failing and near the foot of the class


def _tier(average: float, position: int, class_size: int,
          class_average: float) -> str:
    """Blend standing with the absolute mark so the two never contradict."""
    if class_size <= 1:
        # no meaningful class to compare against — fall back to the mark alone
        if average >= 70:
            return TOP
        if average >= 60:
            return UPPER
        if average >= 50:
            return MIDDLE
        if average >= 40:
            return LOWER
        return BOTTOM

    percentile = 1 - ((position - 1) / max(class_size - 1, 1))  # 1.0 = first

    # A very low absolute mark is a warning no matter the ranking: being top of
    # a weak class is not a pass.
    if average < 40:
        return BOTTOM if percentile < 0.75 else LOWER

    if position == 1 or percentile >= 0.9:
        return TOP if average >= 60 else UPPER
    if percentile >= 0.65:
        return UPPER if average >= 50 else MIDDLE
    if percentile >= 0.35:
        return MIDDLE if average >= 45 else LOWER
    if percentile >= 0.15:
        return LOWER
    return LOWER if average >= 50 else BOTTOM


# ---------------------------------------------------------------- teacher

_TEACHER = {
    TOP: [
        "{first} has had an outstanding term. The work is consistently accurate "
        "and carefully presented, and {first} sets the standard for the class.",
        "An excellent term. {first} works with genuine care, contributes well in "
        "lessons, and should be very proud of this result.",
        "{first} has worked with real diligence this term and the results show it. "
        "Keeping to this habit will bring even better marks.",
    ],
    UPPER: [
        "A very good term. {first} works confidently and is comfortably above "
        "the class average — a little more attention to the weaker subjects "
        "would close the gap to the top.",
        "{first} has performed well and clearly understands most of the work. "
        "With more practice in the weaker areas, top marks are within reach.",
        "A strong term. {first} is dependable in class and should now aim "
        "deliberately at the subjects where marks were lowest.",
    ],
    MIDDLE: [
        "A fair term. {first} is holding around the class average and is capable "
        "of more; steadier revision and prompt assignments would lift these marks.",
        "{first} has done reasonably well but is not yet stretching. Regular "
        "study at home, rather than only before tests, would make the difference.",
        "A satisfactory performance. {first} should ask questions in class more "
        "readily and begin revising earlier in the term.",
    ],
    LOWER: [
        "{first} has fallen behind the class this term. The weaker subjects need "
        "daily attention, and {first} should see the subject teachers for help "
        "rather than waiting until examinations.",
        "A disappointing term. {first} is below the class average and must "
        "complete all assignments and revise consistently to recover.",
        "{first} is struggling in several subjects. With supervised study at home "
        "and extra help in class, these marks can improve.",
    ],
    BOTTOM: [
        "{first} has had a very poor term and is far behind the class. Urgent "
        "support is needed at home and in school, beginning with attendance and "
        "the completion of every assignment.",
        "This is a very weak result. {first} has not engaged with the work, and "
        "close daily supervision is now necessary if the next term is to be better.",
        "{first} needs immediate intervention. The parents should meet the form "
        "teacher so that a plan for recovery can be agreed.",
    ],
}

# ---------------------------------------------------------------- principal

_PRINCIPAL = {
    TOP: [
        "An excellent result. The school is proud of you — maintain this standard.",
        "Outstanding performance. Keep it up.",
        "A splendid term's work. Well done indeed.",
    ],
    UPPER: [
        "A very good result. Aim for the very top next term.",
        "Commendable. Consistency will take you higher still.",
        "Well done. Push a little harder in the weaker subjects.",
    ],
    MIDDLE: [
        "A fair result. More effort is expected of you next term.",
        "Satisfactory, but you can do considerably better.",
        "Acceptable. Work harder to improve your position.",
    ],
    LOWER: [
        "This result is below expectation. Serious improvement is required.",
        "A disappointing term. Parents are advised to supervise study closely.",
        "You must work much harder next term.",
    ],
    BOTTOM: [
        "Unacceptable. The school will invite your parents for a discussion.",
        "A very poor result. Urgent improvement is required to remain in good standing.",
        "This performance is not acceptable. Immediate action is expected of you and your parents.",
    ],
}

# ---------------------------------------------------------------- standing

def _standing(average: float, class_average: float, position: int,
              class_size: int) -> str:
    """A short factual clause, always consistent with the tier."""
    if class_size <= 1:
        return ""
    if position == 1:
        return " This is the best result in the class."
    gap = round(average - class_average, 1)
    if gap >= 10:
        return f" Well above the class average of {class_average}%."
    if gap >= 3:
        return f" Above the class average of {class_average}%."
    if gap > -3:
        return f" Around the class average of {class_average}%."
    if gap > -10:
        return f" Below the class average of {class_average}%."
    return f" Well below the class average of {class_average}%."


def generate_comments(*, first_name: str, average: float, position: int,
                      class_size: int, class_average: float,
                      seed: str | None = None) -> tuple[str, str]:
    """Return (form_teacher_comment, principal_comment) for one student."""
    rng = random.Random(seed or f"{first_name}|{average}|{position}|{class_size}")
    tier = _tier(average, position, class_size, class_average)

    teacher = rng.choice(_TEACHER[tier]).format(first=first_name)
    teacher += _standing(average, class_average, position, class_size)
    principal = rng.choice(_PRINCIPAL[tier])
    return teacher, principal
