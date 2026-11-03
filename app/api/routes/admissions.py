"""Online admissions.

Public (no login), addressed by the school's slug:
  GET  /api/admissions/{slug}/info        — what the apply form needs
  POST /api/admissions/{slug}/apply       — submit an application
  POST /api/admissions/{slug}/status      — check an application (credentials)
  POST /api/admissions/{slug}/test/start  — load the entrance test
  POST /api/admissions/{slug}/test/submit — submit it (auto-graded)

Admin (tenant-scoped):
  applicants list/detail, status changes, admit-to-student, and entrance-test
  authoring. Review is open to school admin and principal; admitting and
  authoring are school-admin only.
"""
from datetime import datetime, timezone
from random import shuffle
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func

from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import User, Role, School
from app.models.academics import SchoolClass, ClassArm
from app.models.student import Student
from app.models.admissions import (
    Applicant, AdmissionTest, AdmissionQuestion,
    APPLIED, SHORTLISTED, ADMITTED, REJECTED, WITHDRAWN, APPLICANT_STATUSES,
    PROPOSABLE, SRC_AUTO, SRC_MANUAL,
)
from app.schemas import (
    ApplicationIn, ApplicantCredentials, EntranceSubmitIn,
    AdmTestIn, AdmTestPatch, AdmQuestionIn, ApplicantStatusIn, AdmitIn,
    AutoReconcileIn, ManualProposeIn, ApplicantIdsIn,
)
from app.services.cbt import grade, student_view
from app.services.admissions import (
    new_access_code, next_application_number, admit_applicant,
    next_admission_number,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/api/admissions", tags=["admissions"])

ReviewRoles = Depends(require_roles(Role.SCHOOL_ADMIN, Role.PRINCIPAL))
AdmitRoles = Depends(require_roles(Role.SCHOOL_ADMIN))
# approving a proposed decision is the principal's responsibility (super admin
# can act for the platform); the registrar/admin reconciles but cannot approve.
ApproveRoles = Depends(require_roles(Role.PRINCIPAL, Role.SUPER_ADMIN))

QUESTION_TYPES = ("single", "multiple", "boolean", "short")


def _now():
    return datetime.now(timezone.utc)


# ==================================================================
# shared helpers
# ==================================================================
async def _school_by_slug(db, slug: str) -> School:
    sch = (await db.execute(select(School).where(
        School.slug == slug))).scalars().first()
    if sch is None or not sch.is_active:
        raise HTTPException(404, "School not found")
    return sch


async def _classes(db, school_id: str):
    rows = (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id,
        SchoolClass.deleted_at.is_(None)))).scalars().all()
    return sorted(rows, key=lambda c: (c.level_order, c.name))


async def _active_test_for(db, school_id: str, applying_class_id: str | None):
    """The entrance test an applicant for this class should sit, if any.

    A test targeted at the applicant's class wins; otherwise a general
    (class-less) active test applies.
    """
    tests = (await db.execute(select(AdmissionTest).where(
        AdmissionTest.school_id == school_id,
        AdmissionTest.is_active == True,                      # noqa: E712
        AdmissionTest.deleted_at.is_(None)))).scalars().all()
    targeted = next((t for t in tests if t.applying_class_id == applying_class_id), None)
    general = next((t for t in tests if t.applying_class_id is None), None)
    return targeted or general


async def _test_questions(db, school_id: str, test_id: str):
    rows = (await db.execute(select(AdmissionQuestion).where(
        AdmissionQuestion.school_id == school_id,
        AdmissionQuestion.test_id == test_id,
        AdmissionQuestion.deleted_at.is_(None)).order_by(
            AdmissionQuestion.sequence))).scalars().all()
    return list(rows)


async def _applicant_by_credentials(db, school_id: str,
                                    creds: ApplicantCredentials) -> Applicant:
    ap = (await db.execute(select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.application_number == creds.application_number.strip(),
        Applicant.deleted_at.is_(None)))).scalars().first()
    if ap is None or ap.access_code != creds.access_code.strip().upper():
        raise HTTPException(404, "No application matches that number and code")
    return ap


def _validate_question(p: AdmQuestionIn):
    if p.type not in QUESTION_TYPES:
        raise HTTPException(422, f"Unknown question type '{p.type}'")
    if not (p.text or "").strip():
        raise HTTPException(422, "A question needs some text")
    if p.marks <= 0:
        raise HTTPException(422, "Marks must be greater than zero")
    if p.type in ("single", "multiple"):
        ids = [str(o.get("id")) for o in p.options if o.get("id") is not None]
        if len(ids) < 2:
            raise HTTPException(422, "Give at least two options")
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "Option ids must be unique")
        if p.type == "single" and str(p.correct) not in ids:
            raise HTTPException(422, "The correct option must be one of the options")
        if p.type == "multiple":
            chosen = [str(x) for x in (p.correct or [])]
            if not chosen or any(c not in ids for c in chosen):
                raise HTTPException(422, "Correct answers must be among the options")
    elif p.type == "boolean":
        if not isinstance(p.correct, bool):
            raise HTTPException(422, "A true/false question needs a boolean answer")
    elif p.type == "short":
        if not [str(x).strip() for x in (p.correct or []) if str(x).strip()]:
            raise HTTPException(422, "Give at least one accepted answer")


# ==================================================================
# PUBLIC
# ==================================================================
@router.get("/{slug}/info")
async def public_info(slug: str, db: DbDep):
    """Everything the public apply form needs — no login."""
    sch = await _school_by_slug(db, slug)
    classes = await _classes(db, sch.id)
    return {
        "school": {"name": sch.name, "slug": sch.slug, "state": sch.state,
                   "logo_url": sch.logo_url, "primary_color": sch.primary_color},
        "classes": [{"id": c.id, "name": c.name} for c in classes],
    }


@router.post("/{slug}/apply", status_code=201)
async def apply(slug: str, payload: ApplicationIn, db: DbDep):
    """Public — submit an application to this school."""
    sch = await _school_by_slug(db, slug)
    klass = await db.get(SchoolClass, payload.applying_class_id)
    if klass is None or klass.school_id != sch.id or klass.deleted_at is not None:
        raise HTTPException(422, "Unknown class")

    app_no = await next_application_number(db, sch.id)
    code = new_access_code()
    ap = Applicant(
        school_id=sch.id, application_number=app_no, access_code=code,
        first_name=payload.first_name.strip(), last_name=payload.last_name.strip(),
        other_names=(payload.other_names or "").strip() or None,
        gender=payload.gender, date_of_birth=payload.date_of_birth,
        applying_class_id=payload.applying_class_id,
        previous_school=(payload.previous_school or "").strip() or None,
        address=(payload.address or "").strip() or None,
        guardian_name=payload.guardian_name.strip(),
        guardian_phone=payload.guardian_phone.strip(),
        guardian_email=(str(payload.guardian_email).strip().lower()
                        if payload.guardian_email else None),
        status=APPLIED, entrance_answers={})
    db.add(ap)
    await db.commit()

    test = await _active_test_for(db, sch.id, payload.applying_class_id)
    return {
        "application_number": app_no,
        "access_code": code,
        "entrance_test": None if not test else {
            "title": test.title, "duration_minutes": test.duration_minutes,
            "question_count": test.question_count},
        "message": ("Application received. Keep your application number and code "
                    "safe — you will need them to check your status"
                    + (" and to sit the entrance test." if test else ".")),
    }


@router.post("/{slug}/status")
async def check_status(slug: str, creds: ApplicantCredentials, db: DbDep):
    """Public — an applicant checks their own application."""
    sch = await _school_by_slug(db, slug)
    ap = await _applicant_by_credentials(db, sch.id, creds)
    test = await _active_test_for(db, sch.id, ap.applying_class_id)
    klass = await db.get(SchoolClass, ap.applying_class_id)
    # the entrance score is deliberately NOT returned to the applicant — only
    # whether a test is waiting or already taken. The outcome reaches them as a
    # change of status (shortlisted / admitted / not successful).
    return {
        "application_number": ap.application_number,
        "name": f"{ap.first_name} {ap.last_name}",
        "applying_class": klass.name if klass else "",
        "status": ap.status,
        "entrance_available": bool(test) and ap.entrance_taken_at is None,
        "entrance_taken": ap.entrance_taken_at is not None,
    }


@router.post("/{slug}/test/start")
async def start_test(slug: str, creds: ApplicantCredentials, db: DbDep):
    """Public — load the entrance test for this applicant."""
    sch = await _school_by_slug(db, slug)
    ap = await _applicant_by_credentials(db, sch.id, creds)
    if ap.entrance_taken_at is not None:
        raise HTTPException(409, "You have already taken the entrance test")
    test = await _active_test_for(db, sch.id, ap.applying_class_id)
    if test is None:
        raise HTTPException(404, "No entrance test is set for your class")
    qs = await _test_questions(db, sch.id, test.id)
    if not qs:
        raise HTTPException(409, "The entrance test has no questions yet")
    view = [student_view(q) for q in qs]
    if test.shuffle_questions:
        shuffle(view)
    return {
        "title": test.title, "instructions": test.instructions,
        "duration_minutes": test.duration_minutes,
        "total_marks": test.total_marks, "questions": view,
        "server_now": _now(),
    }


@router.post("/{slug}/test/submit")
async def submit_test(slug: str, payload: EntranceSubmitIn, db: DbDep):
    """Public — submit the entrance test; auto-graded, score saved on the applicant."""
    sch = await _school_by_slug(db, slug)
    ap = await _applicant_by_credentials(db, sch.id, payload)
    if ap.entrance_taken_at is not None:
        raise HTTPException(409, "You have already taken the entrance test")
    test = await _active_test_for(db, sch.id, ap.applying_class_id)
    if test is None:
        raise HTTPException(404, "No entrance test is set for your class")
    qs = await _test_questions(db, sch.id, test.id)

    score, max_score, _ = grade(qs, payload.answers or {})
    # the score is recorded for the school, but is never shown to the applicant:
    # the outcome is the school's decision, released through the portal status.
    ap.entrance_score = score
    ap.entrance_max = max_score
    ap.entrance_answers = payload.answers or {}
    ap.entrance_taken_at = _now()
    await db.commit()
    return {
        "submitted": True,
        "message": ("Your entrance test has been submitted successfully. "
                    "Please keep checking your application portal — the school "
                    "will update your status once the results are ready."),
    }


# ==================================================================
# ADMIN — review & admit
# ==================================================================
async def _applicant_row(db, ap: Applicant, class_names: dict) -> dict:
    return {
        "id": ap.id,
        "application_number": ap.application_number,
        "name": f"{ap.first_name} {ap.last_name}",
        "gender": ap.gender,
        "applying_class": class_names.get(ap.applying_class_id, ""),
        "applying_class_id": ap.applying_class_id,
        "guardian_name": ap.guardian_name,
        "guardian_phone": ap.guardian_phone,
        "guardian_email": ap.guardian_email,
        "previous_school": ap.previous_school,
        "status": ap.status,
        "status_note": ap.status_note,
        "proposed_status": ap.proposed_status,
        "proposal_source": ap.proposal_source,
        "decided_at": str(ap.decided_at)[:16] if ap.decided_at else None,
        "entrance_score": ap.entrance_score,
        "entrance_max": ap.entrance_max,
        "entrance_percent": (round(ap.entrance_score / ap.entrance_max * 100)
                             if ap.entrance_max else None),
        "entrance_taken": ap.entrance_taken_at is not None,
        "admitted_student_id": ap.admitted_student_id,
        "created_at": str(ap.created_at)[:16],
    }


@router.get("/applicants")
async def list_applicants(db: DbDep, user: Annotated[User, ReviewRoles],
                          status: str | None = Query(None),
                          class_id: str | None = Query(None)):
    school_id = tenant_scope(user)
    stmt = select(Applicant).where(Applicant.school_id == school_id,
                                   Applicant.deleted_at.is_(None))
    if status == "pending":
        # applicants with a proposed decision awaiting the principal
        stmt = stmt.where(Applicant.proposed_status.is_not(None))
    elif status:
        stmt = stmt.where(Applicant.status == status)
    if class_id:
        stmt = stmt.where(Applicant.applying_class_id == class_id)
    rows = (await db.execute(stmt)).scalars().all()
    rows = sorted(rows, key=lambda a: str(a.created_at), reverse=True)
    class_names = {c.id: c.name for c in await _classes(db, school_id)}

    counts: dict[str, int] = {s: 0 for s in APPLICANT_STATUSES}
    pending = 0
    allrows = (await db.execute(select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.deleted_at.is_(None)))).scalars().all()
    for a in allrows:
        counts[a.status] = counts.get(a.status, 0) + 1
        if a.proposed_status:
            pending += 1
    counts["pending"] = pending

    return {
        "counts": counts, "total": len(allrows), "pending": pending,
        "applicants": [await _applicant_row(db, a, class_names) for a in rows],
    }


@router.get("/applicants/{applicant_id}")
async def applicant_detail(applicant_id: str, db: DbDep,
                           user: Annotated[User, ReviewRoles]):
    school_id = tenant_scope(user)
    ap = await db.get(Applicant, applicant_id)
    if ap is None or ap.school_id != school_id or ap.deleted_at:
        raise HTTPException(404, "Applicant not found")
    class_names = {c.id: c.name for c in await _classes(db, school_id)}
    row = await _applicant_row(db, ap, class_names)
    row["date_of_birth"] = str(ap.date_of_birth) if ap.date_of_birth else None
    row["address"] = ap.address
    row["other_names"] = ap.other_names
    return row


@router.patch("/applicants/{applicant_id}/status")
async def set_status(applicant_id: str, payload: ApplicantStatusIn, request: Request,
                     db: DbDep, user: Annotated[User, ReviewRoles]):
    school_id = tenant_scope(user)
    ap = await db.get(Applicant, applicant_id)
    if ap is None or ap.school_id != school_id or ap.deleted_at:
        raise HTTPException(404, "Applicant not found")
    # shortlist / admit / reject are decisions — they go through the proposal +
    # principal-approval path, not this endpoint. This one handles the two
    # administrative resets only.
    if payload.status not in (APPLIED, WITHDRAWN):
        raise HTTPException(422, "Shortlist, admit and reject go through review and principal approval")
    ap.status = payload.status
    if payload.status == APPLIED:
        # returning to the pool clears any pending or past decision
        ap.proposed_status = None
        ap.proposal_source = None
        ap.decided_by_id = None
        ap.decided_at = None
    if payload.note is not None:
        ap.status_note = payload.note.strip()[:300]
    ap.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="applicants", record_id=ap.id,
                       changes={"status": {"new": payload.status}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"id": ap.id, "status": ap.status}


# ------------------------------------------------------------------
# Reconciliation — produce *proposed* decisions (nothing the applicant
# sees changes until the principal approves).
# ------------------------------------------------------------------
async def _open_applicants(db, school_id: str, class_id: str | None = None):
    """Applicants still in play — not already admitted or withdrawn."""
    stmt = select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.deleted_at.is_(None),
        Applicant.status.notin_((ADMITTED, WITHDRAWN)))
    if class_id:
        stmt = stmt.where(Applicant.applying_class_id == class_id)
    return (await db.execute(stmt)).scalars().all()


@router.post("/reconcile/auto")
async def reconcile_auto(payload: AutoReconcileIn, request: Request,
                         db: DbDep, user: Annotated[User, ReviewRoles]):
    """Propose decisions from entrance-test scores.

    Only applicants who have sat the test are decided. With a seats cap, the
    highest scorers (at or above the pass mark) in each class are proposed for
    admission and the rest above the mark for shortlisting; everyone below the
    mark is proposed as not successful.
    """
    school_id = tenant_scope(user)
    applicants = await _open_applicants(db, school_id, payload.class_id)

    tested = [a for a in applicants if a.entrance_max]
    untested = len(applicants) - len(tested)

    def percent(a: Applicant) -> float:
        return (a.entrance_score or 0) / a.entrance_max * 100 if a.entrance_max else 0

    # rank within each applying class, highest first
    by_class: dict[str, list[Applicant]] = {}
    for a in tested:
        by_class.setdefault(a.applying_class_id, []).append(a)

    proposed = {SHORTLISTED: 0, ADMITTED: 0, REJECTED: 0}
    for cls_applicants in by_class.values():
        cls_applicants.sort(key=percent, reverse=True)
        seats_left = payload.seats_per_class
        for a in cls_applicants:
            if percent(a) < payload.pass_mark:
                decision = REJECTED
            elif seats_left is None:
                decision = ADMITTED
            elif seats_left > 0:
                decision = ADMITTED
                seats_left -= 1
            else:
                decision = SHORTLISTED      # above the mark but out of seats
            a.proposed_status = decision
            a.proposal_source = SRC_AUTO
            a.updated_by = user.id
            proposed[decision] += 1

    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="applicants", record_id="auto-reconcile",
                       changes={"pass_mark": {"new": payload.pass_mark},
                                "proposed": {"new": sum(proposed.values())}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"proposed": proposed, "proposed_total": sum(proposed.values()),
            "not_tested": untested}


@router.post("/reconcile/manual")
async def reconcile_manual(payload: ManualProposeIn, request: Request,
                           db: DbDep, user: Annotated[User, ReviewRoles]):
    """Propose one decision for a batch of selected applicants."""
    school_id = tenant_scope(user)
    if payload.proposed_status not in PROPOSABLE:
        raise HTTPException(422, "Decision must be shortlisted, admitted or rejected")
    rows = (await db.execute(select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.id.in_(payload.applicant_ids),
        Applicant.deleted_at.is_(None),
        Applicant.status.notin_((ADMITTED, WITHDRAWN))))).scalars().all()
    for a in rows:
        a.proposed_status = payload.proposed_status
        a.proposal_source = SRC_MANUAL
        a.updated_by = user.id
    await db.commit()
    return {"proposed": len(rows), "proposed_status": payload.proposed_status}


@router.post("/proposals/clear")
async def clear_proposals(payload: ApplicantIdsIn, db: DbDep,
                          user: Annotated[User, ReviewRoles]):
    """Drop pending proposals (return them to review). No ids = clear all."""
    school_id = tenant_scope(user)
    stmt = select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.deleted_at.is_(None),
        Applicant.proposed_status.is_not(None))
    if payload.applicant_ids is not None:
        stmt = stmt.where(Applicant.id.in_(payload.applicant_ids))
    rows = (await db.execute(stmt)).scalars().all()
    for a in rows:
        a.proposed_status = None
        a.proposal_source = None
        a.updated_by = user.id
    await db.commit()
    return {"cleared": len(rows)}


@router.get("/proposals/summary")
async def proposals_summary(db: DbDep, user: Annotated[User, ReviewRoles]):
    """A tally of what is waiting for the principal, by proposed decision."""
    school_id = tenant_scope(user)
    rows = (await db.execute(select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.deleted_at.is_(None),
        Applicant.proposed_status.is_not(None)))).scalars().all()
    tally = {SHORTLISTED: 0, ADMITTED: 0, REJECTED: 0}
    for a in rows:
        tally[a.proposed_status] = tally.get(a.proposed_status, 0) + 1
    return {"pending": len(rows), "by_decision": tally}


@router.post("/proposals/approve")
async def approve_proposals(payload: ApplicantIdsIn, request: Request,
                            db: DbDep, user: Annotated[User, ApproveRoles]):
    """Principal signs off pending decisions — this is when they take effect
    and first become visible to the applicant. No ids = approve all pending."""
    school_id = tenant_scope(user)
    stmt = select(Applicant).where(
        Applicant.school_id == school_id,
        Applicant.deleted_at.is_(None),
        Applicant.proposed_status.is_not(None))
    if payload.applicant_ids is not None:
        stmt = stmt.where(Applicant.id.in_(payload.applicant_ids))
    rows = (await db.execute(stmt)).scalars().all()

    approved = {SHORTLISTED: 0, ADMITTED: 0, REJECTED: 0}
    for a in rows:
        decision = a.proposed_status
        a.status = decision
        a.proposed_status = None
        a.decided_by_id = user.id
        a.decided_at = _now()
        a.updated_by = user.id
        approved[decision] = approved.get(decision, 0) + 1
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="applicants", record_id="approve-proposals",
                       changes={"approved": {"new": sum(approved.values())}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"approved": approved, "approved_total": sum(approved.values())}


@router.post("/applicants/{applicant_id}/admit")
async def admit(applicant_id: str, payload: AdmitIn, request: Request,
                db: DbDep, user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    ap = await db.get(Applicant, applicant_id)
    if ap is None or ap.school_id != school_id or ap.deleted_at:
        raise HTTPException(404, "Applicant not found")
    # enrolment follows the admission decision: only an approved-admitted
    # applicant can be turned into a student.
    if ap.status != ADMITTED:
        raise HTTPException(409, "Admission must be approved by the principal before enrolment")
    school = await db.get(School, school_id)
    # the number is generated from the school's pattern unless one is given
    manual = (payload.admission_number or "").strip()
    admission_number = manual or await next_admission_number(db, school)
    # admission numbers are unique within a school
    clash = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.admission_number == admission_number,
        Student.deleted_at.is_(None)))).scalars().first()
    if clash is not None:
        raise HTTPException(409, "That admission number is already in use")
    if payload.arm_id:
        arm = await db.get(ClassArm, payload.arm_id)
        if arm is None or arm.school_id != school_id:
            raise HTTPException(422, "Unknown class/arm")

    student = await admit_applicant(
        db, ap, admission_number=admission_number,
        arm_id=payload.arm_id, actor_id=user.id)
    await record_audit(db, school_id=school_id, user_id=user.id, action="create",
                       table_name="students", record_id=student.id,
                       changes={"admitted_from_applicant": ap.application_number},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"applicant_id": ap.id, "student_id": student.id,
            "admission_number": student.admission_number, "status": ap.status}


# ==================================================================
# ADMIN — entrance test authoring
# ==================================================================
def _test_out(t: AdmissionTest, class_names: dict) -> dict:
    return {
        "id": t.id, "title": t.title, "instructions": t.instructions,
        "applying_class_id": t.applying_class_id,
        "applying_class": class_names.get(t.applying_class_id) if t.applying_class_id else None,
        "duration_minutes": t.duration_minutes, "shuffle_questions": t.shuffle_questions,
        "total_marks": t.total_marks, "question_count": t.question_count,
        "is_active": t.is_active,
    }


@router.get("/tests")
async def list_tests(db: DbDep, user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    rows = (await db.execute(select(AdmissionTest).where(
        AdmissionTest.school_id == school_id,
        AdmissionTest.deleted_at.is_(None)).order_by(
            AdmissionTest.created_at.desc()))).scalars().all()
    class_names = {c.id: c.name for c in await _classes(db, school_id)}
    return [_test_out(t, class_names) for t in rows]


@router.post("/tests", status_code=201)
async def create_test(payload: AdmTestIn, db: DbDep,
                      user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    if payload.applying_class_id:
        k = await db.get(SchoolClass, payload.applying_class_id)
        if k is None or k.school_id != school_id:
            raise HTTPException(422, "Unknown class")
    t = AdmissionTest(school_id=school_id, created_by=user.id, updated_by=user.id,
                      title=payload.title, instructions=payload.instructions,
                      applying_class_id=payload.applying_class_id,
                      duration_minutes=payload.duration_minutes,
                      shuffle_questions=payload.shuffle_questions)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    class_names = {c.id: c.name for c in await _classes(db, school_id)}
    return _test_out(t, class_names)


async def _get_test(db, school_id: str, test_id: str) -> AdmissionTest:
    t = await db.get(AdmissionTest, test_id)
    if t is None or t.school_id != school_id or t.deleted_at:
        raise HTTPException(404, "Test not found")
    return t


async def _recount(db, school_id: str, t: AdmissionTest):
    qs = await _test_questions(db, school_id, t.id)
    t.question_count = len(qs)
    t.total_marks = sum(q.marks for q in qs)


@router.get("/tests/{test_id}")
async def get_test(test_id: str, db: DbDep, user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    t = await _get_test(db, school_id, test_id)
    class_names = {c.id: c.name for c in await _classes(db, school_id)}
    out = _test_out(t, class_names)
    out["questions"] = [{
        "id": q.id, "type": q.type, "text": q.text, "options": q.options,
        "correct": q.correct, "marks": q.marks, "sequence": q.sequence,
    } for q in await _test_questions(db, school_id, test_id)]
    return out


@router.patch("/tests/{test_id}")
async def update_test(test_id: str, payload: AdmTestPatch, db: DbDep,
                      user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    t = await _get_test(db, school_id, test_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_active"):
        qs = await _test_questions(db, school_id, test_id)
        if not qs:
            raise HTTPException(409, "Add at least one question before activating")
    for k, v in data.items():
        setattr(t, k, v)
    t.updated_by = user.id
    await db.commit()
    await db.refresh(t)
    class_names = {c.id: c.name for c in await _classes(db, school_id)}
    return _test_out(t, class_names)


@router.delete("/tests/{test_id}", status_code=204)
async def delete_test(test_id: str, db: DbDep, user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    t = await _get_test(db, school_id, test_id)
    t.deleted_at = _now()
    await db.commit()


@router.post("/tests/{test_id}/questions", status_code=201)
async def add_question(test_id: str, payload: AdmQuestionIn, db: DbDep,
                       user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    t = await _get_test(db, school_id, test_id)
    _validate_question(payload)
    seq = payload.sequence
    if not seq:
        seq = (await db.execute(select(func.count()).select_from(AdmissionQuestion).where(
            AdmissionQuestion.test_id == test_id,
            AdmissionQuestion.deleted_at.is_(None)))).scalar() or 0
        seq += 1
    q = AdmissionQuestion(school_id=school_id, test_id=test_id, created_by=user.id,
                          type=payload.type, text=payload.text, options=payload.options,
                          correct=payload.correct, marks=payload.marks, sequence=seq)
    db.add(q)
    await db.flush()
    await _recount(db, school_id, t)
    await db.commit()
    await db.refresh(q)
    return {"id": q.id, "type": q.type, "text": q.text, "options": q.options,
            "correct": q.correct, "marks": q.marks, "sequence": q.sequence}


@router.delete("/tests/{test_id}/questions/{qid}", status_code=204)
async def delete_question(test_id: str, qid: str, db: DbDep,
                          user: Annotated[User, AdmitRoles]):
    school_id = tenant_scope(user)
    t = await _get_test(db, school_id, test_id)
    q = await db.get(AdmissionQuestion, qid)
    if q is None or q.test_id != test_id or q.school_id != school_id or q.deleted_at:
        raise HTTPException(404, "Question not found")
    q.deleted_at = _now()
    await db.flush()
    await _recount(db, school_id, t)
    if t.question_count == 0:
        t.is_active = False
    await db.commit()


@router.get("/link")
async def admissions_link(db: DbDep, user: Annotated[User, ReviewRoles]):
    """The school's public apply path, to share on WhatsApp or the school site."""
    school_id = tenant_scope(user)
    sch = await db.get(School, school_id)
    return {"slug": sch.slug if sch else None,
            "apply_path": f"/apply/{sch.slug}" if sch else None}
