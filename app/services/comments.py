"""Report-card comments.

Comments are generated from the student's own performance *relative to their
class* — an average of 62 means something different in a class averaging 45
than in one averaging 75. Generated text is a starting point: it is written to
the TermResult once (on compute) and any human edit is preserved thereafter.

No LLM is required here — these are deterministic, professional, and free.
Phase 4 can swap in an AI generator behind the same function signature.
"""
import random

# Bands are on the student's own average.
_TEACHER_BANDS = [
    (75, [
        "An excellent term. {first} works with real care and consistency.",
        "{first} has had an outstanding term and sets a fine example in class.",
        "Excellent results. {first} shows genuine command of the work.",
    ]),
    (65, [
        "A very good term. {first} is working confidently and steadily.",
        "{first} has performed very well and contributes readily in class.",
        "A strong term's work. {first} should aim for the very top next term.",
    ]),
    (50, [
        "A satisfactory term. {first} is capable of more with steadier effort.",
        "{first} has done fairly well; more consistent study will lift these marks.",
        "A fair performance. {first} should seek help early in weaker subjects.",
    ]),
    (40, [
        "{first} has struggled this term and needs closer support at home.",
        "A weak term. {first} must attend all lessons and complete assignments.",
        "{first} is falling behind and should see subject teachers for extra help.",
    ]),
    (0, [
        "A very poor term. {first} needs urgent intervention and daily supervision.",
        "{first} has not engaged with the work this term. Immediate support is needed.",
    ]),
]

_PRINCIPAL_BANDS = [
    (75, ["An excellent result. Keep it up.",
          "Outstanding. The school is proud of this performance.",
          "A splendid term's work. Well done."]),
    (65, ["A very good result. Aim higher still.",
          "Commendable performance. Continue the good work.",
          "Well done. Consistency will take you to the top."]),
    (50, ["A fair result. More effort is expected next term.",
          "Satisfactory, but there is clear room for improvement.",
          "Acceptable. Work harder for a better position."]),
    (40, ["This result is below expectation. Serious improvement is required.",
          "A disappointing term. Parents should monitor study closely."]),
    (0, ["Unacceptable. Urgent action is required by the student and parents.",
         "This performance is very poor. The school will contact the parents."]),
]


def _band(bands, average: float) -> list[str]:
    for threshold, options in bands:
        if average >= threshold:
            return options
    return bands[-1][1]


def _relative_note(average: float, class_average: float, position: int,
                   class_size: int) -> str:
    """One clause placing the student against their class."""
    if class_size <= 1:
        return ""
    gap = round(average - class_average, 1)
    if position == 1:
        return " The best result in the class."
    if position <= max(3, class_size // 10):
        return " Among the very best in the class."
    if gap >= 8:
        return " Comfortably above the class average."
    if gap >= 2:
        return " A little above the class average."
    if gap <= -8:
        return " Well below the class average."
    if gap <= -2:
        return " A little below the class average."
    return " Around the class average."


def generate_comments(*, first_name: str, average: float, position: int,
                      class_size: int, class_average: float,
                      seed: str | None = None) -> tuple[str, str]:
    """Return (form_teacher_comment, principal_comment)."""
    rng = random.Random(seed or f"{first_name}{average}{position}")
    teacher = rng.choice(_band(_TEACHER_BANDS, average)).format(first=first_name)
    teacher += _relative_note(average, class_average, position, class_size)
    principal = rng.choice(_band(_PRINCIPAL_BANDS, average))
    return teacher, principal
