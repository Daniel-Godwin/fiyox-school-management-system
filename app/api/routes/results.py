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
    AssessmentComponent, ScoreEntry, TermResult,
)
from app.schemas import (
    ComponentIn, ComponentOut, BulkScoresIn, ComputeIn, TermResultUpdate,
)
from app.services.results import compute_term
from app.services.report import build_report_data
from app.services.report_pdf import build_report_pdf
from app.services.audit import record_audit

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
    """Existing raw scores for one arm+subject+term — used to prefill the entry grid."""
    school_id = tenant_scope(user)
    rows = (await db.execute(select(ScoreEntry).where(
        ScoreEntry.school_id == school_id,
        ScoreEntry.arm_id == arm_id,
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
            "form_teacher_comment": tr.form_teacher_comment,
            "principal_comment": tr.principal_comment,
        })
    return sorted(rows, key=lambda r: r["position"])


# ---------- Bulk publish (school admin) ----------
@router.post("/results/publish", tags=["results"])
async def publish_results(
    payload: ComputeIn, request: Request, db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    """Publish every computed result for an arm+term in one action (each row audited)."""
    school_id = tenant_scope(user)
    ip = request.client.host if request.client else None
    results = (await db.execute(select(TermResult).where(
        TermResult.school_id == school_id,
        TermResult.arm_id == payload.arm_id,
        TermResult.term_id == payload.term_id))).scalars().all()
    published = 0
    for tr in results:
        if not tr.is_published:
            await record_audit(db, school_id=school_id, user_id=user.id,
                               action="publish", table_name="term_results",
                               record_id=tr.id,
                               changes={"is_published": {"old": False, "new": True}},
                               ip_address=ip)
            tr.is_published = True
            tr.updated_by = user.id
            published += 1
    await db.commit()
    return {"published": published, "already_published": len(results) - published}


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
