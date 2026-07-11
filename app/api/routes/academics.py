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
