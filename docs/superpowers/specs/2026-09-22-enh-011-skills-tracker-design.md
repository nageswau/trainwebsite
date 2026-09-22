# ENH-011 — School Skills Tracker (Soft Skills, Digital/Web Skills) — Design

**Status:** Policy decisions D1–D9 confirmed by the user in-session, 2026-09-22 (`EXPLICIT_APPROVAL`, §3).
The section-by-section design (backend/API after an `api-and-interface-design` review, §5; frontend after a
`frontend-ui-engineering` review, §7) was presented in-session; the user then instructed "Proceed with ENH-011"
without answering three small points, which this spec **adopts as recommended and flags** (D10–D12, marked
`ADOPTED_ON_PROCEED`, not `EXPLICIT_APPROVAL`). Implementation follows the plan in
`docs/superpowers/plans/2026-09-22-enh-011-skills-tracker.md`.

**Traceability:** `School CRM.md` §9/§10 (`EVID-014`, `DERIVED_BLUEPRINT`) → backlog ENH-011
(`docs/delivery/ENHANCEMENT_BACKLOG.md`, `DERIVED_BACKLOG`) → user decisions 2026-09-22 → `DEC-SCOPE-023`
(proposed by this spec, registered by the plan) → this spec → plan → tests → code. Closes the **Skills** half
of `PRD_OPEN_ITEMS.md` item 77; Portfolio (ENH-012) stays open.

**Acceptance-criteria numbering:** `AC-nn` is local to this spec; cite `DEC-SCOPE-023` / `ENH-011` elsewhere.

## 1. Problem (audit result)

The backlog describes SCH-009 as "student → course/batch → attendance → assessment → certification" and asks
to "generalize" it. The code audit (Graphify + reads, 2026-09-22) shows SCH-009 has **no batch, enrolment or
per-session attendance**: `SchoolTestPrepRecord`/`SchoolLanguageRecord` (`models.py:1181-1212`) are
per-student rows (a `classes_attended` integer, free-text scores, a status). The backlog's own acceptance
criterion ("a batch can be created, students enrolled…") therefore cannot be met by reusing SCH-009's shape.
No Skills table, route or UI exists; entitlements declare `soft_skills` (Bronze) and `web_designing` (Silver)
with `used: null` (`schools.py:752,756`).

## 2. Goals and non-goals

**Goals:** a Career Counselor can create a Soft Skills or Digital Skills batch for one school in their
portfolio, enrol that school's students, record per-session attendance and several assessments, and mark each
student completed/certified; parents are told on enrolment and completion/certification; parents, teachers,
coordinators and principals see it read-only in their existing scope; entitlements count real usage.

**Non-goals (recorded, not built):** migrating SCH-009 (IELTS/SAT/Language) into this model; deleting
batches/enrolments/sessions/assessments (withdrawal is the audited alternative); automatic certification
rules; a school-wide batch list for coordinators; dashboard/report KPI charts (`skills_training` stays
untracked); bulk CSV entry (ENH-028); per-student projects (§10 "Project") and batch duration (not selected,
D7); a shared attendance-roster component with SCH-001's `SchoolActivitiesPanel`.

## 3. Decisions

| # | Question | Decision | Authority |
|---|---|---|---|
| D1 | Scope | §9 Soft Skills and §10 Digital/Web Skills are both `CURRENT` | EXPLICIT_APPROVAL |
| D2 | Shape | New school-scoped batch → enrolment → per-session attendance → assessments → completion/certification, `module_type` ∈ {`soft_skills`, `digital_skills`} | EXPLICIT_APPROVAL |
| D3 | Existing SCH-009 | Left as-is: no table, route, UI or data change | EXPLICIT_APPROVAL |
| D4 | Delivering role | `career_counselor`, scoped by `SchoolStaffAssignment` portfolio | EXPLICIT_APPROVAL |
| D5 | Surfaces | Staff read-only (coordinator/principal own school, teacher assigned students) via overview/timeline; Parent Portal Skills section; SCH-008 timeline (reverses `DEC-SCOPE-016`'s exclusion); entitlement usage | EXPLICIT_APPROVAL |
| D6 | Parent notifications | On enrolment and on transition to completed or certified | EXPLICIT_APPROVAL |
| D7 | Batch scope and fields | One school per batch; fields: title, module type, school, start/end dates, topic, trainer name | EXPLICIT_APPROVAL |
| D8 | Assessments / completion | Multiple named assessments per batch; the counselor sets completion/certification manually (no auto rule) | EXPLICIT_APPROVAL |
| D9 | Transfer (ENH-005) | Derived freeze: an enrolment whose student's current school ≠ the batch's school is read-only and shown "Transferred out"; ENH-005 code untouched | EXPLICIT_APPROVAL |
| D10 | Sessions per day | At most one session per batch per calendar day (unique) | ADOPTED_ON_PROCEED |
| D11 | Certification | `certified` is terminal (no un-certify) | ADOPTED_ON_PROCEED |
| D12 | Route skeletons | Add `loading.tsx` skeletons for the two new counselor routes only | ADOPTED_ON_PROCEED |

## 4. Data model — migration `0035_school_skills` (create-table only)

No existing table is altered and no existing row is read or written; `downgrade()` drops only these tables.

| Table | Columns | Constraints / indexes |
|---|---|---|
| `school_skill_batches` | `id`, `school_id`→schools, `module_type` str(20), `title` str(160), `topic` str(120)?, `trainer_name` str(120)?, `start_date` date, `end_date` date?, `status` str(20) default `open`, `created_by_user_id`→users, timestamps | CHECK module_type IN (…); CHECK status IN (`open`,`closed`); CHECK end_date IS NULL OR end_date >= start_date; index (school_id, module_type) |
| `school_skill_enrollments` | `id`, `batch_id`→batches, `school_student_id`→school_students, `status` str(20) default `enrolled`, `completed_at`?, `certified_at`?, `enrolled_by_user_id`→users, timestamps | UNIQUE (batch_id, school_student_id); CHECK status IN (`enrolled`,`completed`,`certified`,`withdrawn`); index school_student_id |
| `school_skill_sessions` | `id`, `batch_id`, `session_date` date, `topic` str(160)?, `created_by_user_id`, timestamps | UNIQUE (batch_id, session_date) (D10) |
| `school_skill_attendance` | `id`, `session_id`, `enrollment_id`, `present` bool, `marked_by_user_id`, timestamps | UNIQUE (session_id, enrollment_id); index enrollment_id |
| `school_skill_assessments` | `id`, `batch_id`, `name` str(120), `max_score` numeric(6,2), `created_by_user_id`, timestamps | UNIQUE (batch_id, name); CHECK max_score > 0 |
| `school_skill_scores` | `id`, `assessment_id`, `enrollment_id`, `score` numeric(6,2), `remarks` text?, `recorded_by_user_id`, timestamps | UNIQUE (assessment_id, enrollment_id); CHECK score >= 0; index enrollment_id |

"Frozen" (D9) is computed, never stored: `student.school_id != batch.school_id`.

## 5. Backend and API

**Module:** `app/api/school_skills.py`, `APIRouter(prefix="/school", tags=["school-skills"])`, registered in
`main.py` beside ENH-005's routers so `schools.py` (2,044 lines) does not grow. Reuses unchanged from
`schools.py`: `_portfolio_school_ids`, `_student_in_portfolio`, `_notify_student_parents`. Pydantic models in
`app/schemas.py` (`extra="forbid"`, `Literal` enums, `Field` bounds). Error bodies follow the codebase's real
convention, FastAPI `{"detail": ...}` (API_CONTRACT §0.3's `error_code` shape is implemented nowhere; not
introduced here). snake_case fields. No `Idempotency-Key` (§0.2 reserves it for financial/GDPR endpoints).

### 5.1 Career Counselor endpoints (`/api/v1/school/career-counselor/...`)

| Method / path | Success | Errors |
|---|---|---|
| `POST /skill-batches` `{school_id, module_type, title, topic?, trainer_name?, start_date, end_date?}` | 201 `SkillBatchOut` | 403 school not in portfolio; 422 |
| `GET /skill-batches?module_type=&status=&limit=25&offset=0` | 200 `{items, total, limit, offset}` newest first; items carry `school_name`, `enrolled_count` | 422 bad filter; limit 1–100 (ENH-005 D6 precedent) |
| `GET /skill-batches/{id}` | 200 `SkillBatchDetail`: batch + enrolments (student name, status, `frozen`, attendance `{present, marked}`, scores) + sessions (with attendance) + assessments | 404 not found or outside portfolio. Not paginated: enrolments capped at 200 per batch |
| `PATCH /skill-batches/{id}` `{title?, topic?, trainer_name?, start_date?, end_date?, status?}` | 200 `SkillBatchOut` | 404; 422 (incl. `school_id`/`module_type` sent → forbidden extra; end before start) |
| `POST /skill-batches/{id}/enrollments` `{school_student_ids: [1..100] unique}` | 201 `[SkillEnrollmentOut]`, all-or-nothing | 404 batch; 403 a student outside portfolio; 422 a student at a different school than the batch; 409 already enrolled / batch closed / cap 200 |
| `PATCH /skill-enrollments/{id}` `{status}` | 200 `SkillEnrollmentOut`; same status → 200 no-op, no notification | 404; 409 transition not allowed / frozen |
| `POST /skill-batches/{id}/sessions` `{session_date, topic?}` | 201 `SkillSessionOut` | 404; 409 duplicate date / closed; 422 date outside batch dates |
| `PUT /skill-sessions/{id}/attendance` `{records: [1..200] {enrollment_id, present}}` | 200 the session's full attendance | 404; 422 enrolment not in this batch / duplicate ids; 409 enrolment withdrawn, certified or frozen / batch closed |
| `POST /skill-batches/{id}/assessments` `{name, max_score}` | 201 `SkillAssessmentOut` | 404; 409 duplicate name / closed; 422 |
| `PUT /skill-assessments/{id}/scores` `{scores: [1..200] {enrollment_id, score, remarks?}}` | 200 the assessment's full score list | 404; 422 score > max_score / enrolment not in batch; 409 as attendance |

The two `PUT`s upsert only the listed rows (idempotent; unlisted rows untouched).

**Enrolment transitions (D8, D11):** `enrolled → completed | certified | withdrawn`; `completed → certified |
enrolled`; `withdrawn → enrolled`; `certified` terminal. `completed_at`/`certified_at` set on entry, never
cleared (history for the timeline). Enrolment-status changes are allowed on a closed batch (certifying after the
last session is the normal case); every other child write needs an open batch.

### 5.2 Read surfaces (existing endpoints, additive)

- `GET /school/students/{id}/overview` gains `skills: {soft_skills: {status, enrollments[]}, digital_skills:
  {…}}`; rollup `certified` > `completed` > `in_progress` (any enrolled) > `not_started`; withdrawn-only →
  `not_started`. Each enrolment: batch title, topic, trainer, dates, status, `attendance {present, marked}`,
  `assessments [{name, max_score, score, remarks}]`.
- `GET /school/students/{id}/timeline` gains categories `soft_skills`/`digital_skills`, types `skill_enrolled`
  (created_at), `skill_completed` (completed_at), `skill_certified` (certified_at).
- `GET /school/entitlements`: `used` for `soft_skills` and `web_designing` (↔ `digital_skills`) = non-withdrawn
  enrolments in this school's batches of that module.
- Scope is the existing `_load_readable_student`/`_own_school_id` checks — unchanged.

### 5.3 Authorization

A `_require_career_counselor` dependency runs before any lookup (wrong role → 403 before a 404 could reveal
existence). Batch/session/assessment/enrolment outside the counselor's portfolio → 404 (masked). A student
outside the portfolio → 403 via `_student_in_portfolio` (consistent with SCH-004/009). Any counselor whose
portfolio contains the batch's school may manage it (shared, like SCH-004). Readers: unchanged scope rules.

### 5.4 Transactions, concurrency, failure

- One transaction per write, `AuditLog` row included. Parent notifications run **after** commit in their own
  `try` (ENH-005 pattern): a rolled-back write never notifies; a notification failure is logged and never
  undoes the write.
- Enrol: batch row locked `FOR NO KEY UPDATE`, so the 200 cap and the open-status check are serialized; the
  unique index turns a concurrent duplicate into 409 (`IntegrityError` caught, rolled back).
- Status change: enrolment row `FOR UPDATE` — two concurrent "certify" give one transition, one notification.
- Session/attendance/assessment/score writes take the batch `FOR SHARE`, so a concurrent close waits; attendance
  and scores upsert with Postgres `ON CONFLICT … DO UPDATE` (last write wins; retry-safe).
- Accepted: an attendance mark committed at the instant a transfer is approved can land (harmless history).
- A double-submitted batch create has no natural key; the UI disables the button (no idempotency key, §0.2).

### 5.5 Logging and audit

`AuditLog` actions `school.skill_batch_create|update`, `school.skill_enrollment_create|status_change`,
`school.skill_session_create`, `school.skill_attendance_mark`, `school.skill_assessment_create`,
`school.skill_scores_record`; metadata carries ids/counts, never student names. Structured logger
`app.school.skills` (`get_logger`): info on each committed write (ids, counts), warning on a failed
post-commit notification (`exc_info`), warning on a 409 from a concurrent conflict.

## 6. Backward compatibility

No existing route, request or response field changes; SCH-009 untouched; overview/timeline additions are
additive. One approved behaviour change: `entitlements.used` becomes a number for `soft_skills`/`web_designing`
— `sch-011-entitlements.spec.ts:52-55` and any backend assertion on `used: None` for them are updated because
the requirement changed (D5), not to make a test pass.

## 7. Frontend

Reuses `PortalShell`, `SCHOOL_NAV`, `serverApi`, `lib/apiErrors` (`detailMessage`, `isPage`, `Page`,
`NOT_COMPLETED`), `lib/formatDate`, `.card/.empty/.status/.skeleton-line/.form-error/.form-message/.table-wrap/
.form-grid/.metric-grid`, ENH-005's client patterns (AbortController, ref guard against double click, focus to
alert/status, 401 → "Sign in again"). Not reused: `DataTable` (strings only, admin-only), `SchoolActivitiesPanel`
roster (inline; extraction would change SCH-001).

| File | Role |
|---|---|
| `lib/skills.ts` | types, labels, status classes, `TRANSITIONS` (mirrors §5.1), `attendanceText()` |
| `app/school/career-counselor/skills/page.tsx` + `loading.tsx` | server page: me, first batch page, portfolio students (school picker) |
| `components/SchoolSkillBatchesPanel.tsx` | filters, list + Load more, create form → navigate to new batch |
| `app/school/career-counselor/skills/[id]/page.tsx` + `loading.tsx` | server page: batch detail + that school's students; `h1` = batch title; 404 → "Batch not found" |
| `components/SchoolSkillBatchHeader.tsx` | details, inline edit, close/reopen |
| `components/SchoolSkillEnrolments.tsx` | roster table + enrol picker (fieldset/legend, filter, checkboxes) + status control |
| `components/SchoolSkillAttendance.tsx` | sessions, add session, per-session checkbox roster, Mark all present, unsaved-changes guard |
| `components/SchoolSkillScores.tsx` | assessments, add assessment, per-assessment score grid with remarks |

States: server-rendered first paint; skeleton on filter change and route navigation; "Saving…" + disabled +
`aria-busy` during writes, old content kept; empty states for no portfolio school / no batches / no enrolments /
all enrolled / no sessions / no assessments; 401/403/404/409/422/network each handled (422 field errors →
`aria-invalid` + `aria-describedby`); closed-batch banner hides write controls; frozen rows show a
"Transferred out" text badge and are excluded from inputs. Mobile: roster table in `.table-wrap`; attendance
and scores stacked (`.form-grid`), 44px checkbox rows.

Other surfaces: `SchoolChildOverview.tsx` — Skills card (two subsections) and two `ChildStatusRow` chips;
`skills` typed optional; header comment updated. `SchoolStudentTimeline.tsx` — two categories with labels and
AA-contrast colours. `SchoolEntitlementsPanel.tsx` — no change. `navigation.ts` — counselor nav gains Skills.

## 8. Acceptance criteria

- **AC-01** A career counselor creates a Soft Skills and a Digital Skills batch for a portfolio school; a school
  outside the portfolio → 403; a non-counselor → 403.
- **AC-02** Enrolling that school's students succeeds and notifies each linked parent once, after commit; a
  student from a different school → 422; outside the portfolio → 403; a duplicate → 409; nothing is written
  when any student in the request fails.
- **AC-03** Sessions and attendance: a session per day (duplicate date 409), attendance upsert is idempotent,
  attendance summary `{present, marked}` is correct.
- **AC-04** Several assessments per batch; scores upsert, `score > max_score` → 422, remarks stored.
- **AC-05** Status transitions follow §5.1; `certified` is terminal; completed/certified notify parents once;
  a repeated status is a no-op without a notification; two concurrent certifies yield one notification.
- **AC-06** A closed batch rejects enrol/session/attendance/assessment/score writes (409) but allows status
  changes and reopening.
- **AC-07** After an ENH-005 transfer the enrolment is `frozen`: writes → 409, still visible in the student's
  overview/timeline at the new school.
- **AC-08** Overview `skills` block and timeline events appear for parent (linked child), teacher (assigned),
  coordinator/principal (own school); nothing for other students.
- **AC-09** Entitlements report real usage for `soft_skills`/`web_designing`.
- **AC-10** SCH-009 and all pre-existing tests pass unchanged except the entitlement expectation in §6.
- **AC-11** UI: keyboard-only flow create → enrol → attendance → scores → certify works; loading, empty, error
  and closed/frozen states render; no horizontal page scroll at 320px outside tables.
- **AC-12** Every write has an `AuditLog` row without student names; a failed notification does not fail the write.

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| Overview/timeline payload read by 5 pages | additive key only; optional type; existing overview/timeline tests re-run |
| `sch-011` entitlements e2e expects "Not tracked" | updated per D5 (§6) |
| Shared helpers (`_student_in_portfolio`, `_notify_student_parents`) | imported, not modified |
| Parent dashboard `ChildStatusRow` grid gets 6 items | wraps to two rows; parent e2e re-run |
| Timeline category union in TS | extended; unknown-category fallback already exists |
| Migration on existing data | create-only; `upgrade --sql` offline check; downgrade/upgrade rehearsal |

## 10. Tests (named in the plan)

Backend (pytest, isolated compose DB): schema validation (no DB); offline migration SQL; one file
`tests/test_enh_011_skills.py` covering AC-01…AC-09, AC-12, including concurrency (two sessions via
`asyncio.gather`) and notification-failure (monkeypatched `_notify_student_parents` raising). Frontend (vitest):
`lib/skills.ts`, each new component (states, keyboard, errors), `SchoolChildOverview` Skills card,
`SchoolStudentTimeline` labels. E2E (Playwright): `enh-011-skills.spec.ts` full counselor flow + parent view;
`sch-011` update. Browser validation and independent (Codex) review follow implementation and are **not** part
of this plan's completion claim.

## 11. Open items (`NEEDS_CONFIRMATION`)

D10–D12 were adopted on the instruction to proceed and should be confirmed. §10's "Project" and
"Duration" were not selected (D7) — they stay out unless requested.
