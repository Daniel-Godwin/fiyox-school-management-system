# Fiyox School Management System

A multi-tenant platform (Fiyox) that lets many Nigerian secondary schools move from paper to online. Formerly working-titled SchoolSuite/EduCore NG.

A SaaS platform that lets **many** Nigerian secondary schools move from manual
paper records to an online system. One deployment serves every school; each
school's data is strictly isolated.

Built with **FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL/SQLite**.

## Phase 0 (this scaffold) — the foundation
- Multi-tenant core: `School` is the tenant; every school-owned row carries a `school_id`.
- Auth: JWT with `school_id` + `role` baked into the token → every request is pinned to one tenant.
- RBAC: `super_admin`, `school_admin`, `bursar`, `teacher`, `student`, `parent`.
- School onboarding (self-serve for the platform owner).
- Nigerian academic model: 3-term sessions, JSS/SSS classes, arms, subjects.
- Students, enrollment history (promotion trail), guardians, teaching assignments.
- Configurable, per-school grading (CA/Exam weights + WAEC-style bands).

## Project layout (modular monolith)

Each domain is a self-contained slice — its own model, schema, service, and
router — wired together through one aggregator. A domain can later be extracted
into its own microservice without touching the others.

```
app/
  core/       config, database, security, deps (auth/tenant/RBAC guards)
  models/     base + one file per domain (school, academics, student, results, audit)
  schemas/    one file per domain (auth, school, student, results) + re-export hub
  services/   business logic (results, report, report_pdf, importer, audit)
  api/
    router.py     the single aggregate router (registers every domain router)
    routes/       one router file per domain
      system.py auth.py schools.py students.py results.py audit.py imports.py
  main.py     mounts the aggregate router, nothing else
seed.py       demo data
```

## Adding a new module (the recipe)

To add a feature (e.g. `fees`), create these four files and register one line —
nothing else in the app changes:

1. `models/fees.py` — SQLAlchemy models (inherit `TenantMixin` + `TimestampMixin`
   so they get `school_id`, timestamps, soft delete, and authorship for free);
   register them in `models/__init__.py`.
2. `schemas/fees.py` — Pydantic request/response models; re-export in `schemas/__init__.py`.
3. `services/fees.py` — business logic, kept out of the router.
4. `api/routes/fees.py` — a `router = APIRouter(prefix="/api/fees", ...)`.
5. Add `fees` to the tuple in `api/router.py`.

Every endpoint must: resolve `tenant_scope(user)`, declare RBAC via
`require_roles(...)`, and call `record_audit(...)` on sensitive writes. That
checklist is what keeps the platform safe and consistent as modules multiply.

## Setup

Always work inside a virtual environment so Fiyox's dependencies stay isolated
from the rest of your machine.

**1. Create and activate a virtual environment**

macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Windows (Command Prompt):
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

You'll know it worked when your prompt shows `(.venv)` at the front.

**2. Install dependencies and run**
```bash
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
python seed.py                # creates demo data
uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

**Shortcut:** run `./setup.sh` (macOS/Linux) or `setup.bat` (Windows) to do
step 1 and the installs automatically. To leave the environment later, type
`deactivate`.

### Demo logins
| Role         | Email                   | Password  |
|--------------|-------------------------|-----------|
| Super admin  | owner@fiyox.ng    | owner123  |
| School admin | admin@gss-ikeja.ng      | admin123  |

## Roadmap
- **Phase 1 — Result Engine ✅ (built)**: configurable assessment components
  (Test 1/Test 2/Assignment/Exam), bulk score entry gated by role, computation
  (per-subject total, grade, class average, subject position; per-student grand
  total, average, overall position with competition-rank tie handling),
  branded PDF report card + on-screen JSON view, affective domain + comments,
  publish gate (parents/students only see published results).
  Endpoints under `/api`: `assessment-components`, `scores`, `results/compute`,
  `term-results/{id}` (comments/publish), `report/{student_id}`, `report/{student_id}/pdf`.
- **Phase 2 — Enterprise hardening ✅ (started)**: soft delete (`deleted_at`),
  authorship (`created_by`/`updated_by`) on every table, and an append-only
  `audit_logs` trail capturing old→new values on sensitive changes (score edits,
  result publishing). Viewable at `GET /api/audit-logs` (admin). This answers the
  "who changed this result?" accountability question schools care about.
- **Sprint 5 — Bulk onboarding ✅ (built)**: upload a CSV/XLSX to onboard a whole
  school's students in one go. Downloadable template, dry-run preview, per-row
  validation (clear reasons), duplicate skipping, and optional auto-creation of
  missing classes/arms from the sheet. Every insert is audited with a `bulk_import`
  tag. Endpoints: `GET /api/import/students/template`, `POST /api/import/students`
  (`?dry_run=true`, `?auto_create_classes=true`). This is the paper→Fiyox migration
  on-ramp and the future hook for OCR-based digitization of old registers.
- **Phase 2 (cont.) — Fees & Payments**: fee structures, invoices, Paystack, receipts, defaulter handling.
- **Phase 3 — Attendance, timetable, announcements, SMS/email (Termii/Africa's Talking).**
- **Phase 4 — AI layer**: at-risk prediction, performance analytics, auto report-card
  comments (LLM), natural-language queries, OCR migration of old paper records.
- **Phase 5 — Hardening**: Alembic migrations, Postgres Row-Level Security, audit logs, backups, monitoring.
