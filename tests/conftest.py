"""Shared test fixtures.

Each test gets a fresh in-memory SQLite database, seeded with one tenant
(school + admin + teacher + academic structure + subject + components + students)
and a second super-admin account. The app's get_db dependency is overridden to
use the per-test session, so tests are fully isolated from each other.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import date
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db
from app.core.security import hash_password
from app.models import Base
from app.models.school import School, User, Role
from app.models.academics import (
    AcademicSession, Term, SchoolClass, ClassArm, Subject, ClassCategory, TermName,
)
from app.models.student import Student, Gender
from app.models.results import AssessmentComponent


async def _seed(TestSession) -> dict:
    ids: dict = {}
    async with TestSession() as db:
        db.add(User(school_id=None, email="owner@fiyox.ng",
                    hashed_password=hash_password("owner123"),
                    role=Role.SUPER_ADMIN, first_name="Platform", last_name="Owner"))

        school = School(name="GSS Ikeja", slug="gss-ikeja", state="Lagos",
                        address="12 School Road", primary_color="#0B4F6C")
        db.add(school)
        await db.flush()
        ids["school_id"] = school.id

        db.add(User(school_id=school.id, email="admin@gss-ikeja.ng",
                    hashed_password=hash_password("admin123"),
                    role=Role.SCHOOL_ADMIN, first_name="Amaka", last_name="Okoro"))
        db.add(User(school_id=school.id, email="teacher@gss-ikeja.ng",
                    hashed_password=hash_password("teach123"),
                    role=Role.TEACHER, first_name="Tunde", last_name="Bello",
                    phone="+2348010000001"))

        session = AcademicSession(school_id=school.id, name="2025/2026", is_current=True)
        db.add(session)
        await db.flush()
        term = Term(school_id=school.id, session_id=session.id, name=TermName.FIRST,
                    is_current=True, next_term_begins=date(2026, 1, 12))
        db.add(term)
        await db.flush()
        ids["term_id"] = term.id

        jss1 = SchoolClass(school_id=school.id, name="JSS1",
                           category=ClassCategory.JUNIOR, level_order=1)
        db.add(jss1)
        await db.flush()
        arm = ClassArm(school_id=school.id, class_id=jss1.id, name="A")
        db.add(arm)
        await db.flush()
        ids["arm_id"] = arm.id

        subj = Subject(school_id=school.id, name="Mathematics", category=ClassCategory.JUNIOR)
        db.add(subj)
        await db.flush()
        ids["subject_id"] = subj.id

        comps = []
        for seq, (n, mx, ex) in enumerate([
            ("Test 1", 10, False), ("Test 2", 10, False),
            ("Assignment", 10, False), ("Exam", 70, True),
        ]):
            comp = AssessmentComponent(school_id=school.id, name=n, max_score=mx,
                                       is_exam=ex, sequence=seq)
            db.add(comp)
            comps.append(comp)
        await db.flush()
        ids["component_ids"] = [c.id for c in comps]

        students = []
        for i, (fn, ln, g) in enumerate([
            ("Chinedu", "Eze", Gender.MALE),
            ("Fatima", "Bello", Gender.FEMALE),
            ("Ngozi", "Okafor", Gender.FEMALE),
        ], start=1):
            st = Student(school_id=school.id, admission_number=f"GSS/25/{i:03d}",
                         first_name=fn, last_name=ln, gender=g, current_arm_id=arm.id)
            db.add(st)
            students.append(st)
        await db.flush()
        ids["student_ids"] = [s.id for s in students]
        await db.commit()
    return ids


@pytest_asyncio.fixture
async def ctx():
    """Yield (client, ids) with a fresh seeded in-memory DB per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ids = await _seed(TestSession)
    ids["session_factory"] = TestSession

    async def override_get_db():
        async with TestSession() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, ids
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def headers(client: AsyncClient, email: str, password: str) -> dict:
    return {"Authorization": f"Bearer {await login(client, email, password)}"}
