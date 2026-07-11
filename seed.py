"""Seed super admin, a demo school, academic structure, students, assessment
components and raw scores — enough to compute results and print a report card.

Run:  python seed.py
"""
import asyncio
import random
from datetime import date
from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models import Base
from app.models.school import School, User, Role
from app.models.academics import (
    AcademicSession, Term, SchoolClass, ClassArm, Subject, ClassCategory, TermName,
)
from app.models.student import Student, Guardian, Gender
from app.models.results import AssessmentComponent, ScoreEntry

random.seed(42)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        db.add(User(school_id=None, email="owner@fiyox.ng",
                    hashed_password=hash_password("owner123"),
                    role=Role.SUPER_ADMIN, first_name="Platform", last_name="Owner"))

        school = School(name="Government Secondary School, Ikeja",
                        slug="gss-ikeja", state="Lagos",
                        address="12 School Road, Ikeja", primary_color="#0B4F6C")
        db.add(school)
        await db.flush()

        db.add(User(school_id=school.id, email="admin@gss-ikeja.ng",
                    hashed_password=hash_password("admin123"),
                    role=Role.SCHOOL_ADMIN, first_name="Amaka", last_name="Okoro"))
        db.add(User(school_id=school.id, email="bursar@gss-ikeja.ng",
                    hashed_password=hash_password("bursar123"),
                    role=Role.BURSAR, first_name="Chika", last_name="Nwosu",
                    phone="+2348010000009"))
        parent = User(school_id=school.id, email="parent@gss-ikeja.ng",
                      hashed_password=hash_password("parent123"),
                      role=Role.PARENT, first_name="Mama", last_name="Chinedu",
                      phone="+2348010000002")
        db.add(parent)

        session = AcademicSession(school_id=school.id, name="2025/2026",
                                  is_current=True, start_date=date(2025, 9, 15))
        db.add(session)
        await db.flush()
        term = Term(school_id=school.id, session_id=session.id, name=TermName.FIRST,
                    is_current=True, next_term_begins=date(2026, 1, 12))
        db.add(term)

        jss1 = SchoolClass(school_id=school.id, name="JSS1",
                           category=ClassCategory.JUNIOR, level_order=1)
        db.add(jss1)
        await db.flush()
        arm = ClassArm(school_id=school.id, class_id=jss1.id, name="A")
        db.add(arm)
        await db.flush()

        subjects = []
        for name in ["Mathematics", "English Language", "Basic Science", "Civic Education"]:
            subj = Subject(school_id=school.id, name=name, category=ClassCategory.JUNIOR)
            db.add(subj)
            subjects.append(subj)
        await db.flush()

        components = []
        for seq, (cname, mx, is_exam) in enumerate([
            ("Test 1", 10, False), ("Test 2", 10, False),
            ("Assignment", 10, False), ("Exam", 70, True),
        ]):
            comp = AssessmentComponent(school_id=school.id, name=cname,
                                       max_score=mx, is_exam=is_exam, sequence=seq)
            db.add(comp)
            components.append(comp)
        await db.flush()

        students = []
        for i, (fn, ln, g) in enumerate([
            ("Chinedu", "Eze", Gender.MALE),
            ("Fatima", "Bello", Gender.FEMALE),
            ("Tunde", "Adeyemi", Gender.MALE),
            ("Ngozi", "Okafor", Gender.FEMALE),
            ("Ibrahim", "Sani", Gender.MALE),
        ], start=1):
            st = Student(school_id=school.id, admission_number=f"GSS/25/{i:03d}",
                         first_name=fn, last_name=ln, gender=g, current_arm_id=arm.id,
                         date_admitted=date(2025, 9, 15))
            db.add(st)
            students.append(st)
        await db.flush()
        db.add(Guardian(school_id=school.id, parent_user_id=parent.id,
                        student_id=students[0].id, relationship="Mother"))

        for st in students:
            for subj in subjects:
                for comp in components:
                    lo = int(comp.max_score * 0.45)
                    score = random.randint(lo, comp.max_score)
                    db.add(ScoreEntry(
                        school_id=school.id, student_id=st.id, subject_id=subj.id,
                        arm_id=arm.id, term_id=term.id, component_id=comp.id,
                        score=float(score)))

        await db.commit()
        print("Seeded demo school with 5 students, 4 subjects, 4 components, scores.")
        print(f"ARM_ID={arm.id}")
        print(f"TERM_ID={term.id}")
        print(f"STUDENT_ID={students[0].id}")
        print("  Super admin: owner@fiyox.ng / owner123")
        print("  School admin: admin@gss-ikeja.ng / admin123")
        print("  Bursar: bursar@gss-ikeja.ng / bursar123")
        print("  Parent (of Chinedu): parent@gss-ikeja.ng / parent123")


if __name__ == "__main__":
    asyncio.run(main())
