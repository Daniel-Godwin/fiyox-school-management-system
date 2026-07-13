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
from fastapi import Depends, HTTPException, status
from app.core.deps import require_roles
from app.models.school import User, Role
from app.models.results import AssessmentComponent
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
