"""Academic structure reads — the selectors every screen needs (term, arm,
subject). Any authenticated user of the school can read these.
"""
from fastapi import APIRouter
from sqlalchemy import select
from app.core.deps import DbDep, CurrentUser, tenant_scope
from app.models.academics import AcademicSession, Term, SchoolClass, ClassArm, Subject

router = APIRouter(prefix="/api/academics", tags=["academics"])


@router.get("/terms")
async def list_terms(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    sessions = {s.id: s.name for s in (await db.execute(select(AcademicSession).where(
        AcademicSession.school_id == school_id))).scalars().all()}
    terms = (await db.execute(select(Term).where(
        Term.school_id == school_id, Term.deleted_at.is_(None)))).scalars().all()
    return [{
        "id": t.id,
        "name": str(t.name).split(".")[-1].lower(),
        "session": sessions.get(t.session_id, ""),
        "is_current": t.is_current,
        "start_date": str(t.start_date) if t.start_date else None,
        "end_date": str(t.end_date) if t.end_date else None,
        "next_term_begins": (str(t.next_term_begins)
                             if t.next_term_begins else None),
    } for t in terms]


@router.get("/arms")
async def list_arms(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    classes = {c.id: c.name for c in (await db.execute(select(SchoolClass).where(
        SchoolClass.school_id == school_id,
        SchoolClass.deleted_at.is_(None)))).scalars().all()}
    arms = (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id, ClassArm.deleted_at.is_(None)))).scalars().all()
    out = [{
        "id": a.id,
        "name": a.name,
        "class_id": a.class_id,
        "class_name": classes.get(a.class_id, ""),
        "label": f"{classes.get(a.class_id, '')} {a.name}".strip(),
    } for a in arms]
    return sorted(out, key=lambda x: x["label"])


@router.get("/subjects")
async def list_subjects(db: DbDep, user: CurrentUser):
    school_id = tenant_scope(user)
    subjects = (await db.execute(select(Subject).where(
        Subject.school_id == school_id, Subject.deleted_at.is_(None)))).scalars().all()
    return sorted([{
        "id": s.id, "name": s.name, "code": s.code,
        "category": str(s.category).split(".")[-1].lower() if s.category else None,
    } for s in subjects], key=lambda x: x["name"])


# ---------- Academic setup (school admin writes) ----------
from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from app.core.deps import require_roles
from app.models.school import User, Role
from app.models.results import AssessmentComponent
from pydantic import BaseModel
from app.schemas import SessionIn, TermIn, ClassIn, ArmIn, SubjectIn, QuickSetupIn

AdminOnly = Depends(require_roles(Role.SCHOOL_ADMIN))

DEFAULT_COMPONENTS = [
    {"name": "Test 1", "max_score": 10, "is_exam": False, "sequence": 1},
    {"name": "Test 2", "max_score": 10, "is_exam": False, "sequence": 2},
    {"name": "Assignment", "max_score": 10, "is_exam": False, "sequence": 3},
    {"name": "Exam", "max_score": 70, "is_exam": True, "sequence": 4},
]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionIn, db: DbDep,
                         user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    if payload.is_current:
        for s in (await db.execute(select(AcademicSession).where(
                AcademicSession.school_id == school_id))).scalars().all():
            s.is_current = False
    obj = AcademicSession(school_id=school_id, name=payload.name,
                          is_current=payload.is_current, created_by=user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "is_current": obj.is_current}


@router.post("/terms", status_code=status.HTTP_201_CREATED)
async def create_term(payload: TermIn, db: DbDep,
                      user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    session = await db.get(AcademicSession, payload.session_id)
    if not session or session.school_id != school_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if payload.is_current:
        for t in (await db.execute(select(Term).where(
                Term.school_id == school_id))).scalars().all():
            t.is_current = False
    obj = Term(school_id=school_id, session_id=payload.session_id,
               name=payload.name, is_current=payload.is_current, created_by=user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": str(obj.name).split(".")[-1].lower(),
            "is_current": obj.is_current}


@router.post("/classes", status_code=status.HTTP_201_CREATED)
async def create_class(payload: ClassIn, db: DbDep,
                       user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    obj = SchoolClass(school_id=school_id, name=payload.name,
                      category=payload.category, level_order=payload.level_order,
                      created_by=user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


@router.post("/arms", status_code=status.HTTP_201_CREATED)
async def create_arm(payload: ArmIn, db: DbDep,
                     user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    klass = await db.get(SchoolClass, payload.class_id)
    if not klass or klass.school_id != school_id:
        raise HTTPException(status_code=404, detail="Class not found")
    obj = ClassArm(school_id=school_id, class_id=payload.class_id,
                   name=payload.name, created_by=user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "class_id": obj.class_id,
            "label": f"{klass.name} {obj.name}"}


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
async def create_subject(payload: SubjectIn, db: DbDep,
                         user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    obj = Subject(school_id=school_id, name=payload.name, code=payload.code,
                  category=payload.category, created_by=user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "code": obj.code}


@router.post("/quick-setup", status_code=status.HTTP_201_CREATED)
async def quick_setup(payload: QuickSetupIn, db: DbDep,
                      user: Annotated[User, AdminOnly]):
    """Configure a brand-new school in one call: session + current term,
    classes with arms, subjects, and the standard CA/exam components.
    Safe to run once on a fresh school; existing structure is left alone."""
    school_id = tenant_scope(user)

    existing = (await db.execute(select(AcademicSession).where(
        AcademicSession.school_id == school_id))).scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This school already has an academic session — add items individually instead")

    session = AcademicSession(school_id=school_id, name=payload.session_name,
                              is_current=True, created_by=user.id)
    db.add(session)
    await db.flush()

    term = Term(school_id=school_id, session_id=session.id, name=payload.term,
                is_current=True, created_by=user.id)
    db.add(term)

    created_classes = []
    for i, cname in enumerate(payload.classes):
        category = "senior" if cname.upper().startswith("SS") else "junior"
        klass = SchoolClass(school_id=school_id, name=cname, category=category,
                            level_order=i + 1, created_by=user.id)
        db.add(klass)
        await db.flush()
        for aname in payload.arms:
            db.add(ClassArm(school_id=school_id, class_id=klass.id, name=aname,
                            created_by=user.id))
        created_classes.append(cname)

    for sname in payload.subjects:
        db.add(Subject(school_id=school_id, name=sname, created_by=user.id))

    if payload.with_default_components:
        for c in DEFAULT_COMPONENTS:
            db.add(AssessmentComponent(school_id=school_id, created_by=user.id, **c))

    await db.commit()
    return {
        "session": payload.session_name,
        "term": str(payload.term).split(".")[-1].lower(),
        "classes": created_classes,
        "arms_per_class": payload.arms,
        "subjects": payload.subjects,
        "components": [c["name"] for c in DEFAULT_COMPONENTS] if payload.with_default_components else [],
    }


# ---------- Structure maintenance: schools open and close arms ----------
from datetime import datetime, timezone
from app.models.student import Student
from app.services.audit import record_audit


class ArmRename(BaseModel):
    name: str


class TermDatesIn(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    next_term_begins: str | None = None   # printed on every report card


@router.patch("/terms/{term_id}")
async def set_term_dates(term_id: str, payload: TermDatesIn, db: DbDep,
                         user: Annotated[User, AdminOnly]):
    """Set the term's dates. `next_term_begins` appears on the report card —
    it is the line every parent looks for."""
    from datetime import date as _date
    school_id = tenant_scope(user)
    term = await db.get(Term, term_id)
    if not term or term.school_id != school_id:
        raise HTTPException(status_code=404, detail="Term not found")

    changes = {}
    for field in ("start_date", "end_date", "next_term_begins"):
        raw = getattr(payload, field)
        if raw is None:
            continue
        try:
            value = _date.fromisoformat(raw)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"{field} must be a date like 2026-09-14")
        old = getattr(term, field)
        if old != value:
            changes[field] = {"old": str(old) if old else None, "new": str(value)}
            setattr(term, field, value)

    if changes:
        term.updated_by = user.id
        await record_audit(db, school_id=school_id, user_id=user.id,
                           action="update", table_name="terms",
                           record_id=term.id, changes=changes)
        await db.commit()
    return {"id": term.id,
            "start_date": str(term.start_date) if term.start_date else None,
            "end_date": str(term.end_date) if term.end_date else None,
            "next_term_begins": (str(term.next_term_begins)
                                 if term.next_term_begins else None)}


@router.patch("/arms/{arm_id}")
async def rename_arm(arm_id: str, payload: ArmRename, db: DbDep,
                     user: Annotated[User, AdminOnly]):
    school_id = tenant_scope(user)
    arm = await db.get(ClassArm, arm_id)
    if not arm or arm.school_id != school_id or arm.deleted_at:
        raise HTTPException(status_code=404, detail="Arm not found")
    old = arm.name
    arm.name = payload.name
    arm.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="update",
                       table_name="class_arms", record_id=arm.id,
                       changes={"name": {"old": old, "new": payload.name}})
    await db.commit()
    klass = await db.get(SchoolClass, arm.class_id)
    return {"id": arm.id, "name": arm.name,
            "label": f"{klass.name} {arm.name}" if klass else arm.name}


@router.delete("/arms/{arm_id}")
async def close_arm(arm_id: str, db: DbDep,
                    user: Annotated[User, AdminOnly]):
    """Close a class arm. Refused while students are still in it — they must be
    moved first, or their results and invoices would be orphaned."""
    school_id = tenant_scope(user)
    arm = await db.get(ClassArm, arm_id)
    if not arm or arm.school_id != school_id or arm.deleted_at:
        raise HTTPException(status_code=404, detail="Arm not found")

    occupants = (await db.execute(select(Student).where(
        Student.school_id == school_id,
        Student.current_arm_id == arm_id,
        Student.deleted_at.is_(None)))).scalars().all()
    if occupants:
        raise HTTPException(
            status_code=409,
            detail=(f"{len(occupants)} student(s) are still in this arm. "
                    "Move them to another arm first."))

    arm.deleted_at = datetime.now(timezone.utc)
    arm.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="delete",
                       table_name="class_arms", record_id=arm.id,
                       changes={"name": {"old": arm.name, "new": None}})
    await db.commit()
    return {"closed": True}


@router.delete("/classes/{class_id}")
async def close_class(class_id: str, db: DbDep,
                      user: Annotated[User, AdminOnly]):
    """Close a whole class (and its arms). Refused while any arm has students."""
    school_id = tenant_scope(user)
    klass = await db.get(SchoolClass, class_id)
    if not klass or klass.school_id != school_id or klass.deleted_at:
        raise HTTPException(status_code=404, detail="Class not found")

    arms = (await db.execute(select(ClassArm).where(
        ClassArm.school_id == school_id, ClassArm.class_id == class_id,
        ClassArm.deleted_at.is_(None)))).scalars().all()
    arm_ids = [a.id for a in arms]
    if arm_ids:
        occupants = (await db.execute(select(Student).where(
            Student.school_id == school_id,
            Student.current_arm_id.in_(arm_ids),
            Student.deleted_at.is_(None)))).scalars().all()
        if occupants:
            raise HTTPException(
                status_code=409,
                detail=(f"{len(occupants)} student(s) are still in this class. "
                        "Move them first."))

    now = datetime.now(timezone.utc)
    for a in arms:
        a.deleted_at = now
        a.updated_by = user.id
    klass.deleted_at = now
    klass.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="delete",
                       table_name="school_classes", record_id=klass.id,
                       changes={"name": {"old": klass.name, "new": None},
                                "arms_closed": {"old": len(arms), "new": 0}})
    await db.commit()
    return {"closed": True, "arms_closed": len(arms)}


class TransferIn(BaseModel):
    student_ids: list[str]
    to_arm_id: str


@router.post("/students/transfer")
async def transfer_students(payload: TransferIn, db: DbDep,
                            user: Annotated[User, AdminOnly]):
    """Move students between arms — needed before an arm can be closed, and for
    ordinary reshuffles (e.g. splitting JSS1 A into A and B)."""
    school_id = tenant_scope(user)
    target = await db.get(ClassArm, payload.to_arm_id)
    if not target or target.school_id != school_id or target.deleted_at:
        raise HTTPException(status_code=404, detail="Target arm not found")

    moved = 0
    for sid in payload.student_ids:
        st = await db.get(Student, sid)
        if not st or st.school_id != school_id:
            raise HTTPException(status_code=404, detail=f"Student {sid} not found")
        if st.current_arm_id == payload.to_arm_id:
            continue
        old = st.current_arm_id
        st.current_arm_id = payload.to_arm_id
        st.updated_by = user.id
        await record_audit(db, school_id=school_id, user_id=user.id,
                           action="update", table_name="students", record_id=st.id,
                           changes={"current_arm_id": {"old": old,
                                                       "new": payload.to_arm_id}})
        moved += 1
    await db.commit()
    return {"moved": moved}


@router.delete("/subjects/{subject_id}")
async def remove_subject(subject_id: str, request: Request, db: DbDep,
                         user: Annotated[User, AdminOnly]):
    """Retire a subject the school no longer teaches.

    History is sacred: past results and printed report cards keep the subject's
    name forever. What ends is the *future* — the subject leaves the pick
    lists, its teaching assignments are closed, and any timetable lessons for
    it are removed. Nothing a parent already received changes.
    """
    from datetime import datetime, timezone
    from app.models.timetable import Lesson
    from app.models.student import TeachingAssignment
    from app.models.results import ScoreEntry

    school_id = tenant_scope(user)
    subject = await db.get(Subject, subject_id)
    if not subject or subject.school_id != school_id or subject.deleted_at:
        raise HTTPException(status_code=404, detail="Subject not found")

    now = datetime.now(timezone.utc)

    assignments = (await db.execute(select(TeachingAssignment).where(
        TeachingAssignment.school_id == school_id,
        TeachingAssignment.subject_id == subject_id,
        TeachingAssignment.deleted_at.is_(None)))).scalars().all()
    for a in assignments:
        a.deleted_at = now

    lessons = (await db.execute(select(Lesson).where(
        Lesson.school_id == school_id,
        Lesson.subject_id == subject_id,
        Lesson.deleted_at.is_(None)))).scalars().all()
    for l in lessons:
        l.deleted_at = now

    has_scores = (await db.execute(select(ScoreEntry).where(
        ScoreEntry.school_id == school_id,
        ScoreEntry.subject_id == subject_id))).scalars().first() is not None

    subject.deleted_at = now
    subject.updated_by = user.id
    await record_audit(db, school_id=school_id, user_id=user.id, action="delete",
                       table_name="subjects", record_id=subject.id,
                       changes={"name": {"old": subject.name, "new": None}},
                       ip_address=request.client.host if request.client else None)
    await db.commit()
    return {"removed": True,
            "assignments_closed": len(assignments),
            "lessons_removed": len(lessons),
            "history_kept": has_scores,
            "note": ("Past results and report cards keep this subject."
                     if has_scores else
                     "No scores were ever recorded for it.")}
