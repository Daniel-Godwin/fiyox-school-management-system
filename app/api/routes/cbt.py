"""Computer-Based Testing endpoints.

Three audiences share this router:

* **Authors** (teacher of the subject+arm, or school admin) create an exam,
  add questions, then publish it. Once published, questions are frozen.
* **Students** in the exam's arm sit it within its open window. A sitting is
  graded automatically on submit.
* **Oversight** (school admin, principal) read exams and their result tables
  but never author or sit them.

Teachers are held to the same assignment rule as score entry: they may only
author/manage a CBT for a (subject, arm) pair they actually teach.
"""
from datetime import datetime, timedelta, timezone
from random import shuffle
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func

from app.core.deps import DbDep, CurrentUser, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.student import Student
from app.models.academics import ClassArm, SchoolClass, Subject
from app.models.cbt import (
    CBTExam, CBTQuestion, CBTAttempt,
    EXAM_DRAFT, EXAM_PUBLISHED, EXAM_CLOSED,
    Q_SINGLE, Q_MULTIPLE, Q_BOOLEAN, Q_SHORT, QUESTION_TYPES,
    ATTEMPT_IN_PROGRESS, ATTEMPT_SUBMITTED,
)
from app.schemas import (
    QuestionIn, QuestionOut, ExamIn, ExamPatch, ExamOut, ExamDetailOut, SubmitIn,
)
from app.services.cbt import grade, student_view
from app.services.teaching import teaches
from app.services.audit import record_audit

router = APIRouter(prefix="/api/cbt", tags=["cbt"])

AuthorRoles = Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))
ViewRoles = Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN, Role.PRINCIPAL))
StudentRole = Depends(require_roles(Role.STUDENT))


def _utc(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive DB datetime to an aware UTC one for comparison."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _exam(db, school_id: str, exam_id: str) -> CBTExam:
    ex = await db.get(CBTExam, exam_id)
    if ex is None or ex.school_id != school_id or ex.deleted_at is not None:
        raise HTTPException(404, "Exam not found")
    return ex


async def _assert_can_manage(db, user: User, school_id: str, ex: CBTExam) -> None:
    """Author/manage rights: admin passes; a teacher must teach this subject+arm."""
    if user.role in (Role.SCHOOL_ADMIN, Role.SUPER_ADMIN):
        return
    if user.role == Role.TEACHER and await teaches(
            db, school_id, user.id, ex.subject_id, ex.arm_id):
        return
    raise HTTPException(403, "You can only manage tests for classes you teach")


async def _questions(db, school_id: str, exam_id: str) -> list[CBTQuestion]:
    rows = (await db.execute(select(CBTQuestion).where(
        CBTQuestion.school_id == school_id,
        CBTQuestion.exam_id == exam_id,
        CBTQuestion.deleted_at.is_(None)).order_by(CBTQuestion.sequence))).scalars().all()
    return list(rows)


def _validate_question(p: QuestionIn) -> None:
    if p.type not in QUESTION_TYPES:
        raise HTTPException(422, f"Unknown question type '{p.type}'")
    if not (p.text or "").strip():
        raise HTTPException(422, "A question needs some text")
    if p.marks <= 0:
        raise HTTPException(422, "Marks must be greater than zero")

    if p.type in (Q_SINGLE, Q_MULTIPLE):
        ids = [str(o.get("id")) for o in p.options if o.get("id") is not None]
        if len(ids) < 2:
            raise HTTPException(422, "Give at least two options")
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "Option ids must be unique")
        if p.type == Q_SINGLE:
            if str(p.correct) not in ids:
                raise HTTPException(422, "The correct option must be one of the options")
        else:
            chosen = [str(x) for x in (p.correct or [])]
            if not chosen or any(c not in ids for c in chosen):
                raise HTTPException(422, "Correct answers must be among the options")
    elif p.type == Q_BOOLEAN:
        if not isinstance(p.correct, bool):
            raise HTTPException(422, "A true/false question needs a boolean answer")
    elif p.type == Q_SHORT:
        accepted = [str(x).strip() for x in (p.correct or []) if str(x).strip()]
        if not accepted:
            raise HTTPException(422, "Give at least one accepted answer")


# ---------- label helpers ----------
async def _label_maps(db, school_id: str):
    subjects = {s.id: s.name for s in (await db.execute(select(Subject).where(
        Subject.school_id == school_id))).scalars().all()}
    arms = {a.id: a for a in (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id))).scalars().all()}
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id))).scalars().all()}

    def arm_label(arm_id: str) -> str:
        a = arms.get(arm_id)
        if not a:
            return ""
        return f"{classes.get(a.class_id, '')} {a.name}".strip()

    return subjects, arm_label


def _exam_out(ex: CBTExam, subjects: dict, arm_label) -> ExamOut:
    o = ExamOut.model_validate(ex)
    o.subject_name = subjects.get(ex.subject_id)
    o.class_label = arm_label(ex.arm_id)
    return o


# ==================================================================
# Authoring
# ==================================================================
@router.post("/exams", response_model=ExamDetailOut, status_code=201)
async def create_exam(payload: ExamIn, request: Request, db: DbDep,
                      user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    # validate the subject/arm/term belong to this school
    for model, _id, label in ((Subject, payload.subject_id, "subject"),
                              (ClassArm, payload.arm_id, "class"),):
        row = await db.get(model, _id)
        if row is None or row.school_id != school_id:
            raise HTTPException(422, f"Unknown {label}")
    # teacher may only create for a subject+arm they teach
    if user.role == Role.TEACHER and not await teaches(
            db, school_id, user.id, payload.subject_id, payload.arm_id):
        raise HTTPException(403, "You can only create tests for classes you teach")

    ex = CBTExam(school_id=school_id, status=EXAM_DRAFT,
                 created_by=user.id, updated_by=user.id,
                 **payload.model_dump())
    db.add(ex)
    await record_audit(db, school_id=school_id, user_id=user.id, action="create",
                       table_name="cbt_exams", record_id=None,
                       changes={"title": payload.title},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(ex)
    subjects, arm_label = await _label_maps(db, school_id)
    out = ExamDetailOut.model_validate(_exam_out(ex, subjects, arm_label))
    out.instructions = ex.instructions
    out.questions = []
    return out


@router.get("/exams", response_model=list[ExamOut])
async def list_exams(db: DbDep, user: Annotated[User, ViewRoles]):
    """Exams this staff member may see.

    Admin/principal: the whole school. Teacher: exams for the (subject, arm)
    pairs they teach, plus any they created themselves.
    """
    school_id = tenant_scope(user)
    rows = (await db.execute(select(CBTExam).where(
        CBTExam.school_id == school_id,
        CBTExam.deleted_at.is_(None)).order_by(CBTExam.created_at.desc()))).scalars().all()

    if user.role == Role.TEACHER:
        from app.services.teaching import assignments_for
        pairs = {(a.subject_id, a.arm_id)
                 for a in await assignments_for(db, school_id, user.id)}
        rows = [e for e in rows
                if (e.subject_id, e.arm_id) in pairs or e.created_by == user.id]

    subjects, arm_label = await _label_maps(db, school_id)
    return [_exam_out(e, subjects, arm_label) for e in rows]


@router.get("/exams/{exam_id}", response_model=ExamDetailOut)
async def get_exam(exam_id: str, db: DbDep, user: Annotated[User, ViewRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    # a teacher may only open the detail of exams they manage
    if user.role == Role.TEACHER:
        await _assert_can_manage(db, user, school_id, ex)
    subjects, arm_label = await _label_maps(db, school_id)
    out = ExamDetailOut.model_validate(_exam_out(ex, subjects, arm_label))
    out.instructions = ex.instructions
    out.questions = [QuestionOut.model_validate(q)
                     for q in await _questions(db, school_id, exam_id)]
    return out


@router.patch("/exams/{exam_id}", response_model=ExamOut)
async def update_exam(exam_id: str, payload: ExamPatch, db: DbDep,
                      user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    if ex.status == EXAM_PUBLISHED:
        raise HTTPException(409, "Close or unpublish the test before editing its settings")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(ex, k, v)
    ex.updated_by = user.id
    await db.commit()
    await db.refresh(ex)
    subjects, arm_label = await _label_maps(db, school_id)
    return _exam_out(ex, subjects, arm_label)


@router.delete("/exams/{exam_id}", status_code=204)
async def delete_exam(exam_id: str, db: DbDep, user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    ex.deleted_at = _now()
    ex.updated_by = user.id
    await db.commit()


# ---------- questions ----------
@router.post("/exams/{exam_id}/questions", response_model=QuestionOut, status_code=201)
async def add_question(exam_id: str, payload: QuestionIn, db: DbDep,
                       user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    if ex.status == EXAM_PUBLISHED:
        raise HTTPException(409, "This test is live — close it before changing questions")
    _validate_question(payload)
    # default the sequence to the end of the paper
    seq = payload.sequence
    if not seq:
        count = (await db.execute(select(func.count()).select_from(CBTQuestion).where(
            CBTQuestion.exam_id == exam_id,
            CBTQuestion.deleted_at.is_(None)))).scalar() or 0
        seq = count + 1
    q = CBTQuestion(school_id=school_id, exam_id=exam_id, created_by=user.id,
                    updated_by=user.id,
                    type=payload.type, text=payload.text, options=payload.options,
                    correct=payload.correct, marks=payload.marks, sequence=seq)
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


@router.patch("/exams/{exam_id}/questions/{qid}", response_model=QuestionOut)
async def update_question(exam_id: str, qid: str, payload: QuestionIn, db: DbDep,
                          user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    if ex.status == EXAM_PUBLISHED:
        raise HTTPException(409, "This test is live — close it before changing questions")
    q = await db.get(CBTQuestion, qid)
    if q is None or q.exam_id != exam_id or q.school_id != school_id or q.deleted_at:
        raise HTTPException(404, "Question not found")
    _validate_question(payload)
    q.type, q.text, q.options = payload.type, payload.text, payload.options
    q.correct, q.marks = payload.correct, payload.marks
    if payload.sequence:
        q.sequence = payload.sequence
    q.updated_by = user.id
    await db.commit()
    await db.refresh(q)
    return q


@router.delete("/exams/{exam_id}/questions/{qid}", status_code=204)
async def delete_question(exam_id: str, qid: str, db: DbDep,
                          user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    if ex.status == EXAM_PUBLISHED:
        raise HTTPException(409, "This test is live — close it before changing questions")
    q = await db.get(CBTQuestion, qid)
    if q is None or q.exam_id != exam_id or q.school_id != school_id or q.deleted_at:
        raise HTTPException(404, "Question not found")
    q.deleted_at = _now()
    await db.commit()


@router.post("/exams/{exam_id}/publish", response_model=ExamOut)
async def publish_exam(exam_id: str, request: Request, db: DbDep,
                       user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    qs = await _questions(db, school_id, exam_id)
    if not qs:
        raise HTTPException(409, "Add at least one question before publishing")
    ex.status = EXAM_PUBLISHED
    ex.total_marks = sum(q.marks for q in qs)
    ex.question_count = len(qs)
    ex.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="publish",
                       table_name="cbt_exams", record_id=ex.id,
                       changes={"questions": len(qs), "total_marks": ex.total_marks},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(ex)
    subjects, arm_label = await _label_maps(db, school_id)
    return _exam_out(ex, subjects, arm_label)


@router.post("/exams/{exam_id}/close", response_model=ExamOut)
async def close_exam(exam_id: str, db: DbDep, user: Annotated[User, AuthorRoles]):
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    await _assert_can_manage(db, user, school_id, ex)
    ex.status = EXAM_CLOSED
    ex.updated_by = user.id
    await db.commit()
    await db.refresh(ex)
    subjects, arm_label = await _label_maps(db, school_id)
    return _exam_out(ex, subjects, arm_label)


@router.get("/exams/{exam_id}/results")
async def exam_results(exam_id: str, db: DbDep, user: Annotated[User, ViewRoles]):
    """Every sitting of this exam, with student name and score. Oversight view."""
    school_id = tenant_scope(user)
    ex = await _exam(db, school_id, exam_id)
    if user.role == Role.TEACHER:
        await _assert_can_manage(db, user, school_id, ex)
    attempts = (await db.execute(select(CBTAttempt).where(
        CBTAttempt.school_id == school_id,
        CBTAttempt.exam_id == exam_id).order_by(CBTAttempt.started_at))).scalars().all()
    names = {s.id: f"{s.first_name} {s.last_name}" for s in (await db.execute(
        select(Student).where(Student.school_id == school_id))).scalars().all()}
    rows = [{
        "attempt_id": a.id,
        "student_id": a.student_id,
        "student_name": names.get(a.student_id, "—"),
        "attempt_no": a.attempt_no,
        "status": a.status,
        "score": a.score,
        "max_score": a.max_score,
        "percent": round((a.score / a.max_score) * 100) if a.max_score else 0,
        "submitted_at": a.submitted_at,
        "auto_submitted": a.auto_submitted,
    } for a in attempts]
    submitted = [r for r in rows if r["status"] == ATTEMPT_SUBMITTED]
    avg = round(sum(r["percent"] for r in submitted) / len(submitted), 1) if submitted else None
    return {
        "exam_id": ex.id, "title": ex.title, "total_marks": ex.total_marks,
        "status": ex.status, "sittings": len(rows), "submitted": len(submitted),
        "average_percent": avg, "rows": rows,
    }


# ==================================================================
# Sitting (student)
# ==================================================================
async def _my_student(db, user: User, school_id: str) -> Student:
    st = (await db.execute(select(Student).where(
        Student.school_id == school_id, Student.user_id == user.id,
        Student.deleted_at.is_(None)))).scalars().first()
    if st is None:
        raise HTTPException(403, "No student record is linked to your account")
    return st


def _open_now(ex: CBTExam, now: datetime) -> bool:
    if ex.status != EXAM_PUBLISHED:
        return False
    if ex.opens_at and now < _utc(ex.opens_at):
        return False
    if ex.closes_at and now > _utc(ex.closes_at):
        return False
    return True


@router.get("/available")
async def available_exams(db: DbDep, user: Annotated[User, StudentRole]):
    """Published exams for the student's current arm, with their attempt status."""
    school_id = tenant_scope(user)
    st = await _my_student(db, user, school_id)
    now = _now()
    exams = (await db.execute(select(CBTExam).where(
        CBTExam.school_id == school_id,
        CBTExam.arm_id == st.current_arm_id,
        CBTExam.status == EXAM_PUBLISHED,
        CBTExam.deleted_at.is_(None)).order_by(CBTExam.created_at.desc()))).scalars().all()
    subjects, _ = await _label_maps(db, school_id)

    out = []
    for ex in exams:
        attempts = (await db.execute(select(CBTAttempt).where(
            CBTAttempt.school_id == school_id, CBTAttempt.exam_id == ex.id,
            CBTAttempt.student_id == st.id).order_by(CBTAttempt.attempt_no))).scalars().all()
        in_progress = next((a for a in attempts if a.status == ATTEMPT_IN_PROGRESS), None)
        used = len(attempts)
        last = attempts[-1] if attempts else None
        out.append({
            "id": ex.id, "title": ex.title,
            "subject_name": subjects.get(ex.subject_id),
            "duration_minutes": ex.duration_minutes,
            "question_count": ex.question_count, "total_marks": ex.total_marks,
            "opens_at": ex.opens_at, "closes_at": ex.closes_at,
            "open_now": _open_now(ex, now),
            "attempts_used": used, "max_attempts": ex.max_attempts,
            "can_start": _open_now(ex, now) and (in_progress is not None or used < ex.max_attempts),
            "in_progress_attempt": in_progress.id if in_progress else None,
            "last_attempt_id": last.id if last else None,
            "last_status": last.status if last else None,
            "show_results": ex.show_results_immediately,
        })
    return out


@router.post("/exams/{exam_id}/start")
async def start_exam(exam_id: str, db: DbDep, user: Annotated[User, StudentRole]):
    school_id = tenant_scope(user)
    st = await _my_student(db, user, school_id)
    ex = await _exam(db, school_id, exam_id)
    now = _now()
    if ex.arm_id != st.current_arm_id:
        raise HTTPException(403, "This test is not for your class")
    if not _open_now(ex, now):
        raise HTTPException(409, "This test is not open right now")

    attempts = (await db.execute(select(CBTAttempt).where(
        CBTAttempt.school_id == school_id, CBTAttempt.exam_id == ex.id,
        CBTAttempt.student_id == st.id).order_by(CBTAttempt.attempt_no))).scalars().all()
    attempt = next((a for a in attempts if a.status == ATTEMPT_IN_PROGRESS), None)

    if attempt is None:
        if len(attempts) >= ex.max_attempts:
            raise HTTPException(409, "You have used all your attempts for this test")
        deadline = now + timedelta(minutes=ex.duration_minutes)
        if ex.closes_at and _utc(ex.closes_at) < deadline:
            deadline = _utc(ex.closes_at)
        attempt = CBTAttempt(
            school_id=school_id, exam_id=ex.id, student_id=st.id,
            attempt_no=len(attempts) + 1, started_at=now, deadline_at=deadline,
            status=ATTEMPT_IN_PROGRESS, answers={})
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)

    qs = await _questions(db, school_id, ex.id)
    view = [student_view(q) for q in qs]
    if ex.shuffle_questions:
        shuffle(view)
    return {
        "attempt_id": attempt.id,
        "exam": {"id": ex.id, "title": ex.title, "instructions": ex.instructions,
                 "duration_minutes": ex.duration_minutes,
                 "total_marks": ex.total_marks},
        "deadline_at": attempt.deadline_at,
        "server_now": now,
        "saved_answers": attempt.answers or {},
        "questions": view,
    }


@router.post("/attempts/{attempt_id}/answer")
async def save_answers(attempt_id: str, payload: SubmitIn, db: DbDep,
                       user: Annotated[User, StudentRole]):
    """Autosave partial answers so a dropped connection never loses work."""
    school_id = tenant_scope(user)
    st = await _my_student(db, user, school_id)
    a = await db.get(CBTAttempt, attempt_id)
    if a is None or a.school_id != school_id or a.student_id != st.id:
        raise HTTPException(404, "Attempt not found")
    if a.status != ATTEMPT_IN_PROGRESS:
        raise HTTPException(409, "This attempt is already submitted")
    merged = dict(a.answers or {})
    merged.update(payload.answers or {})
    a.answers = merged
    await db.commit()
    return {"saved": True}


@router.post("/attempts/{attempt_id}/submit")
async def submit_attempt(attempt_id: str, payload: SubmitIn, db: DbDep,
                         user: Annotated[User, StudentRole]):
    school_id = tenant_scope(user)
    st = await _my_student(db, user, school_id)
    a = await db.get(CBTAttempt, attempt_id)
    if a is None or a.school_id != school_id or a.student_id != st.id:
        raise HTTPException(404, "Attempt not found")
    if a.status != ATTEMPT_IN_PROGRESS:
        raise HTTPException(409, "This attempt is already submitted")

    ex = await _exam(db, school_id, a.exam_id)
    qs = await _questions(db, school_id, a.exam_id)
    answers = dict(a.answers or {})
    answers.update(payload.answers or {})

    score, max_score, breakdown = grade(qs, answers)
    a.answers = answers
    a.breakdown = breakdown
    a.score = score
    a.max_score = max_score
    a.submitted_at = _now()
    a.status = ATTEMPT_SUBMITTED
    a.auto_submitted = bool(payload.auto)
    await db.commit()

    result = {"attempt_id": a.id, "status": a.status,
              "show_results": ex.show_results_immediately}
    if ex.show_results_immediately:
        result.update({"score": score, "max_score": max_score,
                       "percent": round((score / max_score) * 100) if max_score else 0})
    return result


@router.get("/attempts/{attempt_id}")
async def my_attempt(attempt_id: str, db: DbDep, user: Annotated[User, StudentRole]):
    """A student reviews their own finished sitting."""
    school_id = tenant_scope(user)
    st = await _my_student(db, user, school_id)
    a = await db.get(CBTAttempt, attempt_id)
    if a is None or a.school_id != school_id or a.student_id != st.id:
        raise HTTPException(404, "Attempt not found")
    ex = await _exam(db, school_id, a.exam_id)
    out = {"attempt_id": a.id, "exam_title": ex.title, "status": a.status,
           "submitted_at": a.submitted_at,
           "show_results": ex.show_results_immediately}
    if a.status == ATTEMPT_SUBMITTED and ex.show_results_immediately:
        qs = {q.id: q for q in await _questions(db, school_id, a.exam_id)}
        out.update({
            "score": a.score, "max_score": a.max_score,
            "percent": round((a.score / a.max_score) * 100) if a.max_score else 0,
            "review": [{
                "question": qs[qid].text if qid in qs else "",
                "your_answer": a.answers.get(qid),
                "correct": info.get("correct"),
                "marks": info.get("marks"), "max": info.get("max"),
            } for qid, info in (a.breakdown or {}).items()],
        })
    return out
