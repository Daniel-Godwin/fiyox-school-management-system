"""Result-engine endpoints: configure components, enter scores, compute, view/print."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser, require_roles, tenant_scope
from app.models.school import User, Role
from app.models.student import Student, Guardian
from app.models.results import (
    AssessmentComponent, ScoreEntry, TermResult, CommentBankEntry,
)
from pydantic import BaseModel, Field
from app.schemas import (
    ComponentIn, ComponentOut, BulkScoresIn, ComputeIn, TermResultUpdate,
)
from app.services.results import compute_term
from app.services.report import build_report_data
from app.services.report_pdf import build_report_pdf
from app.services.audit import record_audit
from app.services.teaching import assert_may_touch_scores

router = APIRouter(prefix="/api")


# ---------- Assessment components (school admin) ----------
@router.post("/assessment-components", response_model=ComponentOut,
             status_code=status.HTTP_201_CREATED, tags=["results"])
async def add_component(
    payload: ComponentIn, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    comp = AssessmentComponent(school_id=school_id, **payload.model_dump())
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@router.get("/assessment-components", response_model=list[ComponentOut], tags=["results"])
async def list_components(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    res = await db.execute(select(AssessmentComponent).where(
        AssessmentComponent.school_id == school_id).order_by(AssessmentComponent.sequence))
    return list(res.scalars().all())


# ---------- Score entry (teacher / admin) ----------
@router.get("/scores", tags=["results"])
async def get_scores(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
    arm_id: str = Query(...),
    subject_id: str = Query(...),
    term_id: str = Query(...),
):
    """Existing raw scores for one arm+subject+term — used to prefill the entry grid.

    Scores are looked up by the students *currently* in the arm, never by the
    arm_id stamped on the score row. A student who moves class keeps their marks:
    filtering on the stored arm_id would strand them (they would silently vanish
    from the sheet while still sitting in the database).
    """
    school_id = tenant_scope(user)
    # a teacher may only see the sheets they actually teach
    await assert_may_touch_scores(db, user, school_id, subject_id, arm_id)

    student_ids = [s.id for s in (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id == arm_id,
        Student.deleted_at.is_(None)))).scalars().all()]
    if not student_ids:
        return []

    rows = (await db.execute(select(ScoreEntry).where(
        ScoreEntry.school_id == school_id,
        ScoreEntry.student_id.in_(student_ids),
        ScoreEntry.subject_id == subject_id,
        ScoreEntry.term_id == term_id))).scalars().all()
    return [{"student_id": r.student_id, "component_id": r.component_id,
             "score": r.score} for r in rows]


@router.post("/scores", tags=["results"])
async def enter_scores(
    payload: BulkScoresIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    # THE GUARD: a teacher may only write scores for a subject+arm they teach.
    # Without this, any teacher could alter any other teacher's marks.
    await assert_may_touch_scores(db, user, school_id,
                                  payload.subject_id, payload.arm_id)
    ip = request.client.host if request.client else None
    written = 0
    for row in payload.rows:
        for component_id, score in row.scores.items():
            existing = (await db.execute(select(ScoreEntry).where(
                ScoreEntry.school_id == school_id,
                ScoreEntry.student_id == row.student_id,
                ScoreEntry.subject_id == payload.subject_id,
                ScoreEntry.term_id == payload.term_id,
                ScoreEntry.component_id == component_id))).scalars().first()
            if existing:
                # the student may have changed arm since this row was written;
                # keep the stamp current so reports and exports stay coherent
                if existing.arm_id != payload.arm_id:
                    existing.arm_id = payload.arm_id
                if existing.score != score:
                    # capture old -> new for the audit trail
                    await record_audit(
                        db, school_id=school_id, user_id=user.id, action="update",
                        table_name="score_entries", record_id=existing.id,
                        changes={"score": {"old": existing.score, "new": score}},
                        ip_address=ip)
                    existing.score = score
                    existing.updated_by = user.id
            else:
                entry = ScoreEntry(
                    school_id=school_id, student_id=row.student_id,
                    subject_id=payload.subject_id, arm_id=payload.arm_id,
                    term_id=payload.term_id, component_id=component_id, score=score,
                    created_by=user.id)
                db.add(entry)
                await db.flush()
                await record_audit(
                    db, school_id=school_id, user_id=user.id, action="create",
                    table_name="score_entries", record_id=entry.id,
                    changes={"score": {"old": None, "new": score}}, ip_address=ip)
            written += 1
    await db.commit()
    return {"scores_written": written}


# ---------- Compute (school admin) ----------
@router.post("/results/compute", tags=["results"])
async def compute(
    payload: ComputeIn, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    return await compute_term(db, school_id, payload.arm_id, payload.term_id)


# ---------- Class results listing (broadsheet-lite) ----------
@router.get("/results", tags=["results"])
async def list_results(
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
    arm_id: str = Query(...),
    term_id: str = Query(...),
):
    """Computed term results for one arm, ranked — what a form teacher reviews
    before publishing."""
    school_id = tenant_scope(user)
    results = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == arm_id,
        TermResult.term_id == term_id))).scalars().all()
    students = {s.id: s for s in (await db.execute(select(Student).where(
        Student.school_id == school_id))).scalars().all()}
    rows = []
    for tr in results:
        st = students.get(tr.student_id)
        rows.append({
            "term_result_id": tr.id,
            "student_id": tr.student_id,
            "admission_number": st.admission_number if st else "",
            "name": f"{st.first_name} {st.last_name}" if st else "Unknown",
            "subjects_count": tr.subjects_count,
            "grand_total": tr.grand_total,
            "average": tr.average,
            "position": tr.overall_position,
            "class_size": tr.class_size,
            "is_published": tr.is_published,
            "approval_status": tr.approval_status,
            "approval_note": tr.approval_note,
            "form_teacher_comment": tr.form_teacher_comment,
            "principal_comment": tr.principal_comment,
        })
    return sorted(rows, key=lambda r: r["position"])


async def _arm_term_results(db, school_id: str, arm_id: str, term_id: str):
    return (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == arm_id,
        TermResult.term_id == term_id))).scalars().all()


# ---------- Approval workflow ----------
# The release of a report card now passes through an explicit gate:
#   draft  --submit-->  submitted  --approve-->  approved  --publish-->  parents
# A form teacher prepares and submits; the principal approves (or returns with a
# reason); only approved results can be published. Recomputing a term rewrites
# these rows, so changed marks always return the result to draft.

@router.post("/results/submit", tags=["results"])
async def submit_results(
    payload: ComputeIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
):
    """Form teacher (or admin) submits an arm's computed results for approval."""
    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None
    results = await _arm_term_results(db, school_id, payload.arm_id, payload.term_id)
    if not results:
        raise HTTPException(status_code=404, detail="No computed results to submit")
    submitted = 0
    for tr in results:
        if tr.approval_status == "draft":
            tr.approval_status = "submitted"
            tr.approval_note = ""
            tr.updated_by = user.id
            submitted += 1
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="term_results", record_id=payload.arm_id,
                       changes={"submitted_for_approval": {"old": None, "new": submitted}},
                       ip_address=ip)
    await db.commit()
    return {"submitted": submitted, "note": "Results sent to the principal for approval."}


@router.post("/results/approve", tags=["results"])
async def approve_results(
    payload: ComputeIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Principal approves submitted results; they become publishable."""
    from datetime import datetime, timezone

    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None
    results = await _arm_term_results(db, school_id, payload.arm_id, payload.term_id)
    now = datetime.now(timezone.utc)
    approved = 0
    for tr in results:
        if tr.approval_status == "submitted":
            tr.approval_status = "approved"
            tr.approved_by = user.id
            tr.approved_at = now
            tr.approval_note = ""
            tr.updated_by = user.id
            approved += 1
    if not approved:
        raise HTTPException(
            status_code=400,
            detail="Nothing to approve — results must be submitted for approval first")
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="term_results", record_id=payload.arm_id,
                       changes={"approved": {"old": None, "new": approved}},
                       ip_address=ip)
    await db.commit()
    return {"approved": approved, "note": "Approved. These results can now be published."}


@router.post("/results/return", tags=["results"])
async def return_results(
    payload: TermResultUpdate, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
    arm_id: str = Query(...), term_id: str = Query(...),
):
    """Principal returns submitted results to the form teacher, with a reason."""
    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None
    note = (payload.form_teacher_comment or "").strip()[:300]
    results = await _arm_term_results(db, school_id, arm_id, term_id)
    returned = 0
    for tr in results:
        if tr.approval_status == "submitted":
            tr.approval_status = "draft"
            tr.approval_note = note
            tr.updated_by = user.id
            returned += 1
    if not returned:
        raise HTTPException(
            status_code=400, detail="Nothing to return — no results are awaiting approval")
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="term_results", record_id=arm_id,
                       changes={"returned_for_revision": {"old": None, "new": note or returned}},
                       ip_address=ip)
    await db.commit()
    return {"returned": returned, "note": "Returned to the form teacher for revision."}


# ---------- Bulk publish (school admin) — only approved results ----------
@router.post("/results/publish", tags=["results"])
async def publish_results(
    payload: ComputeIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Publish an arm+term's results to parents — only those that are approved.

    A result that has not been approved is left unpublished and reported back,
    so nothing reaches parents without passing the approval gate.
    """
    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None
    # the approval gate only applies when the school has switched it on;
    # otherwise an admin publishes directly, exactly as before
    from app.models.school import School as _School
    school = await db.get(_School, school_id)
    gate_on = bool(school and school.result_approval_required)

    results = await _arm_term_results(db, school_id, payload.arm_id, payload.term_id)
    published = already = blocked = 0
    for tr in results:
        if tr.is_published:
            already += 1
            continue
        if gate_on and tr.approval_status != "approved":
            blocked += 1
            continue
        await record_audit(db, school_id=school_id, user_id=user.id,
                           action="publish", table_name="term_results",
                           record_id=tr.id,
                           changes={"is_published": {"old": False, "new": True}},
                           ip_address=ip)
        tr.is_published = True
        tr.updated_by = user.id
        published += 1
    await db.commit()
    result = {"published": published, "already_published": already,
              "blocked_unapproved": blocked}
    if blocked and not published:
        result["note"] = ("These results are not approved yet. The principal must "
                          "approve them before they can be published.")
    return result


# ---------- Edit term result: affective, comments, publish ----------
@router.patch("/term-results/{term_result_id}", tags=["results"])
async def update_term_result(
    term_result_id: str, payload: TermResultUpdate, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
):
    school_id = tenant_scope(user)
    tr = await db.get(TermResult, term_result_id)
    if not tr or tr.school_id != school_id:
        raise HTTPException(status_code=404, detail="Term result not found")
    fields = payload.model_dump(exclude_none=True)
    # when the school requires approval, a single result cannot be published
    # here unless it has been approved — the gate is not bypassable via edit
    if fields.get("is_published") and tr.approval_status != "approved":
        from app.models.school import School as _School
        school = await db.get(_School, school_id)
        if school and school.result_approval_required:
            raise HTTPException(
                status_code=400,
                detail="This result must be approved before it can be published")
    changes = {}
    for field, value in fields.items():
        old = getattr(tr, field)
        if old != value:
            changes[field] = {"old": old, "new": value}
            setattr(tr, field, value)
    # a human has spoken: recomputing the term must not overwrite their words
    if changes.keys() & {"form_teacher_comment", "principal_comment"}:
        tr.comments_edited = True
    tr.updated_by = user.id
    action = "publish" if fields.get("is_published") else "update"
    await record_audit(db, school_id=school_id, user_id=user.id, action=action,
                       table_name="term_results", record_id=tr.id, changes=changes,
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"updated": True, "published": tr.is_published}


# ---------- View a report card (scoped by who's asking) ----------
async def _can_view(db, user: User, student: Student) -> bool:
    if user.role in (Role.SUPER_ADMIN, Role.SCHOOL_ADMIN, Role.TEACHER, Role.BURSAR):
        return True
    if user.role == Role.STUDENT:
        return student.user_id == user.id
    if user.role == Role.PARENT:
        link = (await db.execute(select(Guardian).where(
            Guardian.parent_user_id == user.id,
            Guardian.student_id == student.id))).scalars().first()
        return link is not None
    return False


@router.get("/report/{student_id}", tags=["results"])
async def report_json(student_id: str, db: DbDep, user: CurrentUser,
                      term_id: str = Query(...)):
    school_id = tenant_scope(user)
    student = await db.get(Student, student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(status_code=404, detail="Student not found")
    if not await _can_view(db, user, student):
        raise HTTPException(status_code=403, detail="Not allowed to view this report")
    data = await build_report_data(db, school_id, student_id, term_id)
    if not data:
        raise HTTPException(status_code=404, detail="No computed result for this term")
    # parents/students only see published results
    if user.role in (Role.PARENT, Role.STUDENT) and not data["published"]:
        raise HTTPException(status_code=403, detail="Result not yet published")
    await _enforce_debt_gate(db, user, school_id, student_id, term_id)
    return data


async def _enforce_debt_gate(db, user: User, school_id: str,
                             student_id: str, term_id: str) -> None:
    """If the school withholds results on debt, block parents/students whose
    invoice for this term still has a positive balance. Staff are never blocked."""
    if user.role not in (Role.PARENT, Role.STUDENT):
        return
    from app.models.school import School
    from app.services.fees import has_outstanding_debt
    school = await db.get(School, school_id)
    if school and school.withhold_results_on_debt:
        if await has_outstanding_debt(db, school_id, student_id, term_id):
            raise HTTPException(
                status_code=402,
                detail="Result withheld: outstanding school fees for this term")


@router.get("/report/{student_id}/pdf", tags=["results"])
async def report_pdf(student_id: str, db: DbDep, user: CurrentUser,
                     term_id: str = Query(...)):
    school_id = tenant_scope(user)
    student = await db.get(Student, student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(status_code=404, detail="Student not found")
    if not await _can_view(db, user, student):
        raise HTTPException(status_code=403, detail="Not allowed to view this report")
    data = await build_report_data(db, school_id, student_id, term_id)
    if not data:
        raise HTTPException(status_code=404, detail="No computed result for this term")
    if user.role in (Role.PARENT, Role.STUDENT) and not data["published"]:
        raise HTTPException(status_code=403, detail="Result not yet published")
    await _enforce_debt_gate(db, user, school_id, student_id, term_id)
    pdf = build_report_pdf(data)
    fname = f"report_{student.admission_number.replace('/', '-')}_{data['term']['name']}.pdf"
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{fname}"'})


# ============================ Comment bank ============================
# Reusable, average-banded report-card comments. When a teacher writes a
# comment, the UI calls /suggest to offer the ones that fit the student.

class CommentBankIn(BaseModel):
    text: str = Field(min_length=2, max_length=300)
    min_average: float = Field(default=0.0, ge=0, le=100)
    max_average: float = Field(default=100.0, ge=0, le=100)
    audience: str = Field(default="form_teacher", pattern="^(form_teacher|principal)$")


@router.get("/comment-bank", tags=["results"])
async def list_comment_bank(
    db: DbDep, user: Annotated[User, Depends(require_roles(
        Role.TEACHER, Role.SCHOOL_ADMIN))],
    audience: str | None = Query(None),
):
    school_id = tenant_scope(user)
    stmt = select(CommentBankEntry).where(
        CommentBankEntry.school_id == school_id,
        CommentBankEntry.deleted_at.is_(None))
    if audience:
        stmt = stmt.where(CommentBankEntry.audience == audience)
    rows = (await db.execute(stmt)).scalars().all()
    rows.sort(key=lambda r: (r.audience, r.min_average))
    return [{"id": r.id, "text": r.text, "min_average": r.min_average,
             "max_average": r.max_average, "audience": r.audience} for r in rows]


@router.get("/comment-bank/suggest", tags=["results"])
async def suggest_comments(
    db: DbDep, user: Annotated[User, Depends(require_roles(
        Role.TEACHER, Role.SCHOOL_ADMIN))],
    average: float = Query(...), audience: str = Query("form_teacher"),
):
    """Bank entries whose band contains this average — what the UI offers a
    teacher as they write. Band is [min, max], inclusive both ends."""
    school_id = tenant_scope(user)
    rows = (await db.execute(select(CommentBankEntry).where(
        CommentBankEntry.school_id == school_id,
        CommentBankEntry.audience == audience,
        CommentBankEntry.deleted_at.is_(None),
        CommentBankEntry.min_average <= average,
        CommentBankEntry.max_average >= average))).scalars().all()
    return [{"id": r.id, "text": r.text} for r in rows]


@router.post("/comment-bank", tags=["results"], status_code=status.HTTP_201_CREATED)
async def add_comment_bank(
    payload: CommentBankIn, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER))],
):
    school_id = tenant_scope(user)
    lo, hi = sorted((payload.min_average, payload.max_average))
    entry = CommentBankEntry(school_id=school_id, text=payload.text.strip(),
                             min_average=lo, max_average=hi,
                             audience=payload.audience, created_by=user.id)
    db.add(entry)
    await db.commit()
    return {"id": entry.id}


@router.delete("/comment-bank/{entry_id}", tags=["results"])
async def delete_comment_bank(
    entry_id: str, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER))],
):
    from datetime import datetime, timezone
    school_id = tenant_scope(user)
    entry = await db.get(CommentBankEntry, entry_id)
    if not entry or entry.school_id != school_id or entry.deleted_at:
        raise HTTPException(status_code=404, detail="Comment not found")
    entry.deleted_at = datetime.now(timezone.utc)
    entry.updated_by = user.id
    await db.commit()
    return {"removed": True}


# ====================== Affective traits (grid) ======================
# The school configures its trait list under settings. Here a form teacher
# rates a whole arm at once; ratings land on each student's TermResult.

class AffectiveGridIn(BaseModel):
    arm_id: str
    term_id: str
    # {student_id: {trait: rating(1-5)}}
    ratings: dict[str, dict[str, int]]


@router.get("/results/affective", tags=["results"])
async def get_affective_grid(
    db: DbDep, user: Annotated[User, Depends(require_roles(
        Role.TEACHER, Role.SCHOOL_ADMIN))],
    arm_id: str = Query(...), term_id: str = Query(...),
):
    """The school's trait list plus each student's current ratings, for the
    grid the form teacher fills in."""
    from app.models.school import School
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    traits = (school.affective_traits or []) if school else []

    results = await _arm_term_results(db, school_id, arm_id, term_id)
    students = {s.id: s for s in (await db.execute(select(Student).where(
        Student.school_id == school_id))).scalars().all()}
    rows = []
    for tr in results:
        st = students.get(tr.student_id)
        rows.append({
            "student_id": tr.student_id,
            "admission_number": st.admission_number if st else "",
            "name": f"{st.first_name} {st.last_name}" if st else "",
            "ratings": tr.affective or {},
        })
    rows.sort(key=lambda r: r["name"])
    return {"traits": traits, "students": rows}


@router.post("/results/affective", tags=["results"])
async def save_affective_grid(
    payload: AffectiveGridIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.SCHOOL_ADMIN))],
):
    """Save behaviour ratings for a whole arm. Ratings are clamped to 1-5 and
    only known traits are kept; an empty rating clears that trait."""
    from app.models.school import School
    school_id = tenant_scope(user)
    school = await db.get(School, school_id)
    traits = set((school.affective_traits or []) if school else [])

    results = {tr.student_id: tr for tr in
               await _arm_term_results(db, school_id, payload.arm_id, payload.term_id)}
    saved = 0
    for sid, ratings in payload.ratings.items():
        tr = results.get(sid)
        if not tr:
            continue
        clean = {}
        for trait, val in ratings.items():
            if trait in traits and isinstance(val, int) and 1 <= val <= 5:
                clean[trait] = val
        tr.affective = clean
        tr.updated_by = user.id
        saved += 1
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="term_results", record_id=payload.arm_id,
                       changes={"affective_rated": {"old": None, "new": saved}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"saved": saved}
