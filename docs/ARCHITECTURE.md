# Fiyox School Management System — Architecture & Build Plan (consolidated)

Multi-tenant school management platform for Nigerian secondary schools.
This document is the single source of truth that
reconciles our running codebase with the external planning note.

---

## 0. Status at a glance

| Layer | Status |
|---|---|
| Multi-tenant core (shared DB + `tenant_id`, JWT-pinned) | **Built** |
| Auth + RBAC (6 roles) | **Built** (single-role; multi-role planned) |
| School onboarding | **Built** |
| Academic model (sessions, terms, classes, arms, subjects) | **Built** |
| Students, enrollment history, guardians, teaching assignments | **Built** |
| Result engine (components → scores → totals, grades, positions) | **Built** |
| Report card (on-screen JSON + branded PDF) | **Built** |
| Publish gate (parents see published only) | **Built** |
| Audit logs + soft delete + created_by/updated_by | **In progress (tonight)** |
| Result approval workflow | Planned (Phase 2) |
| Fees, invoices, payments (Paystack/Flutterwave) | Planned (Phase 2) |
| Attendance | Planned (Phase 2) |
| SMS/email notifications (Termii / Africa's Talking) | Planned (Phase 3) |
| Timetable, announcements, library | Planned (Phase 3) |
| AI layer (risk, auto-comments, WAEC readiness) | Planned (Phase 4) |

---

## 1. Executive decisions (and why)

1. **Multi-tenant pool model.** One database, every school-owned row carries
   `school_id`, JWT carries `school_id` so each request is pinned to one tenant.
   Cheapest and most scalable for price-sensitive schools. Add Postgres
   Row-Level Security as defense-in-depth later; offer schema-per-tenant only to
   large schools that demand hard isolation.
2. **Compute-and-store results, not compute-on-read.** Positions and class
   averages depend on the whole arm and must be stable once published. We
   snapshot them on an explicit compute action. *(This corrects the external
   note's "never store averages" advice.)*
3. **Stack:** FastAPI (async) + SQLAlchemy 2.0 + PostgreSQL (Neon in prod,
   SQLite in dev) + reportlab for PDFs. Frontend: Next.js (React + TS) as a PWA
   for offline tolerance. Redis + Celery/RQ for background jobs when volume needs it.
4. **Audit-first.** Soft delete (`deleted_at`), `created_by`/`updated_by` on every
   row, and an `audit_logs` table capturing old→new values on sensitive changes.
   "Who changed this result?" is a sales feature, not an afterthought.
5. **Multi-role RBAC.** Adopt the external note's many-to-many roles so one
   person can be both bursar and teacher (common in small schools).
6. **AI in separate tables, human-in-the-loop.** ML outputs never overwrite
   academic tables. Auto-generated comments pre-fill a field a teacher reviews.

---

## 2. Review of the external plan — adopt / revise / add

**Adopt as-is:** multi-tenant `tenant_id`; single `users` table; configurable
assessment types and per-school grading; UUID PKs; audit logs; soft delete;
`created_by`/`updated_by`; separate AI tables; multi-role RBAC; index strategy;
subscription fields on `schools`.

**Revise:**
- "Never store averages" → **store computed snapshots** (rationale above).
- "Argon2 for passwords" → we use bcrypt (fine and battle-tested); Argon2 is a
  reasonable later switch, not a blocker.
- Grading stored as a **table** in the note → we store bands as JSON on `School`
  for MVP simplicity; migrate to a `grading_system` table if schools need to
  query/version bands.
- Heavyweight "BRS/SRS/ERD/API/wireframes before code" sequence → keep only this
  plan + an ERD + the roadmap; validate the schema with running code (already done).

**Add (missing from the note, needed for Nigeria):**
- Result **approval workflow** with explicit states (Section 7).
- **Withhold-results-on-debt** policy (flag already on `School`).
- Named SMS providers: **Termii** and **Africa's Talking** (feature-phone reach).
- **NDPA 2023** compliance for minors' data (consent, minimization, retention).
- Offline / low-bandwidth handling (PWA sync, lightweight payloads).
- Payment **webhooks + idempotency** for Paystack/Flutterwave reconciliation.
- Separation of **platform billing** (schools paying us) from **school fees**
  (parents paying schools) — two different money flows (Appendix A).

---

## 3. Architecture

```
Clients (Admin / Teacher / Parent / Student PWA)
        │  HTTPS, JWT (carries school_id + roles)
        ▼
FastAPI (async) ── tenant guard ── RBAC guard
        │
        ├── Result engine / report PDFs
        ├── Fees & payments (Paystack/Flutterwave webhooks)
        ├── Notifications (Termii / Africa's Talking, email)
        ├── AI microservice(s) (risk, comments, WAEC readiness)
        └── Audit + soft-delete layer
        │
        ▼
PostgreSQL (one DB, isolated by school_id)   Redis (cache/queues)   Object storage (report cards, media)
```

**Isolation guarantee:** verified in tests — a second school's admin sees zero of
the first school's students; a school admin is blocked (403) from platform actions.

**Scaling path:** Redis caching → Celery/RQ + broker for background jobs →
object storage (S3/R2) → read replicas for analytics → Kubernetes for horizontal
FastAPI scaling → separate AI services. Core data model does not change.

---

## 4. Canonical data model (module by module)

Tables marked **[built]** exist in code. Naming reflects the codebase; the
external note's equivalent name is shown where it differs.

**Base columns on every school-owned table:** `id` (UUID), `school_id`,
`created_at`, `updated_at`, `deleted_at` (soft delete), `created_by`, `updated_by`.

### Tenant
- `schools` **[built]** — name, slug (subdomain), email, phone, address, state,
  lga, logo_url, primary_color, `grading_config` (JSON), `withhold_results_on_debt`,
  subscription_plan, subscription_expiry, is_active.

### Users & access
- `users` **[built]** — school_id (null for super admin), email (unique per school),
  hashed_password, first/last/phone, is_active, primary `role`.
- `roles`, `user_roles` — **planned** many-to-many for multi-hat staff.
- `permissions` — **planned** (optional; role→permission map for fine control).

### Academic
- `academic_sessions` **[built]** (note: `sessions`) — name "2025/2026", is_current.
- `terms` **[built]** — first/second/third, dates, next_term_begins, is_current.
- `school_classes` **[built]** (note: `classes`) — JSS1…SS3, category, level_order.
- `class_arms` **[built]** — arm name, class_id, form_teacher_id, capacity(planned).
- `subjects` **[built]** — name, code, category, is_core.
- `timetable` — **planned**.

### People
- `students` **[built]** — admission_number, names, gender, dob, current_arm_id,
  user_id, date_admitted, is_active. Add state_of_origin, religion, blood_group,
  genotype (planned fields).
- `enrollments` **[built]** — student × session × arm (promotion trail).
- `guardians` **[built]** (note: `parents` + `parent_student`) — parent_user_id,
  student_id, relationship.
- `teaching_assignments` **[built]** (note: `teacher_subject`) — teacher × subject × arm.
- `staff_profiles` — **planned** (staff_number, qualification, department, employment_date).

### Assessment & results
- `assessment_components` **[built]** (note: `assessment_types`) — name, max_score,
  is_exam, sequence. Configurable per school; components sum to 100.
- `score_entries` **[built]** — raw score per student × subject × term × component.
- `subject_results` **[built]** — computed total, grade, remark, subject_position,
  class_average, breakdown (JSON).
- `term_results` **[built]** — grand_total, average, subjects_count, class_size,
  overall_position, affective (JSON), form_teacher_comment, principal_comment,
  is_published. Add workflow `status` (Section 7).

### Finance — **planned (Phase 2)**
- `fee_categories` — school fees, exam, sports, transport, hostel.
- `fee_structure` — class × term × category → amount.
- `invoices` — student, invoice_number, amount, discount, balance, status, due_date.
- `payments` — invoice, method (cash/transfer/POS/Paystack/Flutterwave), reference,
  amount, date, received_by. Webhook-verified, idempotent by reference.

### Communication — **planned (Phase 3)**
- `announcements` — title, message, target (teachers/parents/students/all), published_at.
- `message_log` — SMS/email delivery records (provider, status, cost).

### AI — **planned (Phase 4)**
- `ai_predictions` — student, prediction_type (risk/attendance/WAEC readiness),
  value, confidence, model_version, generated_at.
- `ai_reports` — generated analytics artifacts (file_url, generated_by).

### Audit — **in progress (tonight)**
- `audit_logs` — tenant_id, user_id, action, table_name, record_id, changes (JSON
  old/new), ip_address, created_at.

### Indexes
Single: `school_id`, `student_id`, `teacher_id`, `class_id`, `subject_id`,
`session_id`, `term_id`, `invoice_number`, `admission_number`.
Composite: (`school_id`, `student_id`), (`school_id`, `subject_id`),
(`school_id`, `session_id`), (`school_id`, `term_id`).

---

## 5. Nigeria-specific rules

- **Academic shape:** 3 terms/session; JSS1–SS3; arms (A/B); CA + exam.
- **Grading:** WAEC-style A1–F9 default bands, but **configurable per school**
  (CA/exam split and bands vary). Report cards carry affective/psychomotor ratings
  (punctuality, neatness) plus form-teacher and principal comments.
- **Result approval workflow:** see Section 7.
- **Withhold results on debt:** optional per-school policy; if on, unpaid students'
  results are gated until cleared.
- **Payments:** Paystack and Flutterwave; verify via **webhooks**, make payment
  writes **idempotent** by reference; support cash/transfer/POS reconciliation.
- **Notifications:** **Termii** and **Africa's Talking** for SMS (feature-phone
  reach), email as secondary. Result-published and fee-reminder alerts.
- **Data protection (NDPA 2023):** minors' data — collect the minimum, define
  retention, log access, secure at rest and in transit, support data-subject requests.
- **Connectivity:** PWA with offline score entry + sync; lightweight payloads;
  tolerate flaky power/internet.

---

## 6. Security & compliance

UUID keys (no sequential exposure); bcrypt password hashing (Argon2 optional
later); JWT **access + refresh** tokens; RBAC on every endpoint; tenant guard on
every query; HTTPS everywhere; encryption at rest for sensitive fields; soft
delete (no hard destroys of academic records); `audit_logs` for accountability;
automated daily backups; least-privilege DB roles.

---

## 7. Result approval workflow (state machine)

```
draft ──(subject teacher submits)──▶ submitted
submitted ──(exam officer / form teacher reviews)──▶ reviewed
reviewed ──(principal publishes)──▶ published ──(term ends)──▶ locked
```

- Scores are editable only in `draft`/`submitted`.
- Parents and students see results **only** in `published` (and not withheld for debt).
- Every transition writes an `audit_logs` entry (who, when, from→to).
- `locked` freezes the term result; corrections require an admin override that is
  itself audited.

---

## 8. API surface

**Built:** `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/schools`,
`POST|GET /api/students`, `POST|GET /api/assessment-components`, `POST /api/scores`,
`POST /api/results/compute`, `PATCH /api/term-results/{id}` (comments/publish),
`GET /api/report/{student_id}`, `GET /api/report/{student_id}/pdf`.

**Tonight:** `GET /api/audit-logs`.

**Planned:** classes/arms/subjects CRUD, enrollment/promotion, attendance,
fee-structure/invoices/payments (+ Paystack/Flutterwave webhooks), announcements,
notifications, AI endpoints, bulk CSV/Excel import.

---

## 9. Sprint roadmap (reconciled)

- **Sprint 0 — Foundation ✅** multi-tenant core, auth/RBAC, onboarding, academic model.
- **Sprint 1 — Result Engine ✅** components, scores, compute, report card + PDF, publish gate.
- **Sprint 2 — Enterprise hardening (now)** audit logs, soft delete, created_by/updated_by,
  approval workflow states, Alembic migrations, Postgres switch.
- **Sprint 3 — Fees & Payments** structures, invoices, Paystack/Flutterwave, receipts, debt gating.
- **Sprint 4 — Attendance + Notifications** attendance capture, Termii/Africa's Talking, announcements.
- **Sprint 5 — Onboarding at scale** bulk CSV/Excel import (OCR migration path).
- **Sprint 6 — AI layer** risk prediction, attendance anomaly, auto-comments, WAEC readiness.
- **Sprint 7 — Frontend** Next.js PWA dashboards (Admin, Teacher, Parent, Student, Bursar).

---

## 10. Tonight & next

**Tonight (Sprint 2 start):** add the audit/soft-delete/authorship foundation —
soft-delete columns, `created_by`/`updated_by`, an `audit_logs` table, and a
`record_audit()` path wired into the sensitive result mutations so score changes
are captured old→new, plus a `GET /api/audit-logs` view. This is the external
note's best idea and is best added before more tables pile on.

**Next:** either Sprint 3 (Fees — revenue) or Sprint 5 (bulk import — makes the
platform demoable to a pilot school fast). Recommend Fees for the business case,
or bulk import if you want a live pilot first.

---

## Appendix A — Two money flows (don't conflate)

1. **School fees** — parents pay schools (invoices, receipts, Paystack/Flutterwave).
   Lives in the Finance module, per tenant.
2. **Platform billing** — schools pay *you* the subscription (per-term/per-student).
   Belongs in a separate platform-level billing module keyed on `schools`, not in
   any tenant's data. Keep these codepaths and tables distinct.
