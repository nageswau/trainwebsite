# itc-031 — Unified IT student lifecycle status and history (design)

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-031 (PDF §3 student lifecycle; PDF classified `UNVERIFIED`). Scope approved by the
owner 2026-11-01 (backlog Q-01). Dependencies itc-013 (`DEC-SCOPE-346`), itc-023 (`DEC-SCOPE-352`) and itc-027 (`DEC-SCOPE-354`) are
merged. Q-30 is open; the owner said to proceed with the recommended answers, so L1–L9 below are **the builder's calls
(`NEEDS_CONFIRMATION`)**. Decision `DEC-SCOPE-358`.

## 1. What exists (Graphify discovery)

| Piece | Where | Note |
|---|---|---|
| Enrolment status | `Enrollment.status` free text | values in use: `pending_consent`, `active`, `rejected`, `withdrawn`, `dropped`, `completed` |
| Fee state | `services/fee_accounts.balance_for` (itc-013) | per enrolment, computed, batched |
| At risk | `StudentRiskFlag` open row (itc-023) | per enrolment, daily sweep |
| Completed | `Certificate.enrollment_id` issued, or status `completed` | |
| HR review | `HrReviewTask.stage` (itc-027) | per student |
| Interview / placed | `JobApplication.status` (`interview`, `selected`, `joined`) by `student_id` | per student; `applications.change_status` the writer |
| 360 | `/it/{counselor,admin}/students/[id]/profile` (`ItStudentProfilePage`) | counselor (linked) + IT Admin |

MUST CHANGE: `models.Enrollment`, migration, new `services/it_lifecycle.py`, `api/it_student_profiles.py`, `services/it_student_profiles.py`,
`api/admin.py` enrolment list/PATCH, `ItStudentProfilePage.tsx`, `lib/itStudentProfile.ts`.
MAY CHANGE (hook one line): `api/fee_accounts.py`, `api/payments._mark_paid`, `api/workflows.py` (create enrolment, consent, certificate
issue), `services/hr_reviews.py`, `services/applications.change_status`, `services/it_at_risk.sweep`.
SHOULD NOT CHANGE: fee maths, risk rules, HR stages, application transitions, the student access gate.
HIGH REGRESSION RISK: every hooked writer (a failure in the history writer would roll back their transaction), the new status CHECK.

## 2. Decisions (builder's calls)

- **L1 Stages** (fixed set, order): `enrolled`, `fee_pending`, `partially_paid`, `paid`, `training_active`, `at_risk`, `completed`,
  `resume_submitted`, `hr_screening`, `interview`, `placed`, `not_placed`, `closed`. Labels are served by the API (`stage_label`) so
  itc-005 can rename them in one place.
- **L2 Components** (computed per enrolment, shown beside the stage so concurrent states stay visible):
  - fee: not billed → none (the card says "Not billed"; the stage falls back to `enrolled`); `enrolled_pending_payment` →
    `fee_pending`; `partially_paid`; `fully_paid` → `paid`.
  - training: seated (`active`/`completed`) and effective start ≤ today (IST) → `training_active`; an open risk flag → `at_risk`;
    status `completed` or an issued certificate for the enrolment → `completed`; otherwise none.
  - placement (the student's newest seated enrolment only — HR and applications are per student): any application `joined` → `placed`;
    application `interview`/`selected` or HR `interview_ready`/`completed` → `interview`; HR `under_review`/`changes_requested`/`screening`
    → `hr_screening`; HR `resume_received` → `resume_submitted`; HR `withdrawn` or nothing → none.
- **L3 Display precedence (Q-30):** enrolment `rejected`/`withdrawn`/`dropped` → `closed`; override `closed` → `closed`; placement `placed`
  → `placed`; override `not_placed` → `not_placed`; else the furthest track: placement, then training, then fee.
- **L4 Overrides (Q-30):** only `not_placed` and `closed`, by the **IT Admin** only (counselor read-only), with a reason (3–500 chars);
  `null` clears it. Any other stage → 409 (`placed` → "Placed needs a joining record"). `not_placed` on a student already placed → 409.
  Stored on the enrolment (`lifecycle_override`, `lifecycle_override_reason`) — it is a manual source record, not a cached stage. Every
  override change writes an itc-001 audit row with before/after.
- **L5 No stored stage (AC3):** the current stage is always derived on read. History rows are transitions (past facts), never read back
  as the current stage.
- **L6 History writer:** `it_lifecycle.sync(db, enrollment_ids, actor, cause)` — locks the enrolment rows, derives, and inserts a row
  `(from_stage, to_stage, cause, actor, created_at)` when the stage differs from the last row (the first row has `from_stage` NULL). No
  commit — it runs inside the caller's transaction. Causes: `enrolment`, `fee`, `certificate`, `hr_review`, `placement`, `override`,
  `daily_check`. Actor NULL = the system (gateway webhook, daily check).
- **L7 Daily catch-up:** time-only transitions (a start date arriving) and writers without a hook are caught by the itc-023 daily sweep,
  which ends with `sync_all` (chunked, actor NULL, cause `daily_check`). A failure there is logged and never changes the sweep's counts.
- **L8 Readers (AuthZ):** the lifecycle and its history on the 360 for the linked counselor and the IT Admin (`staff_student` scope:
  out of scope = 404). `/admin/enrollments` gains `lifecycle` (stage + label). The student's own record gets a safe stage only:
  `at_risk` reads as `training_active` (no "At risk" wording) and no history. Dashboards and reports are itc-032 (depends on itc-031).
- **L9 Enrolment status CHECK:** `ck_enrollments_status` over the six values in use, added `NOT VALID` and validated only when no row
  breaks it (existing data is never rewritten). The admin PATCH answers 422 for any other status instead of a database error.

## 3. API (additive)

- `GET /api/v1/{counselor|admin}/it/students/{id}/lifecycle` → `{ "enrollments": [ { enrollment_id, enrollment_code, program, batch,
  stage, stage_label, components: {fee, training, placement}, override: {stage, reason} | null, history: [ {from_stage, from_label,
  to_stage, to_label, cause, actor, created_at} ] (newest first, 50) } ] }`.
- `PUT /api/v1/admin/it/students/{id}/enrollments/{eid}/lifecycle-override` `{stage: "not_placed"|"closed"|<other stage>|null,
  reason}` → the lifecycle response. 403 counselor route (none exists), 404 out of scope, 409 non-overridable, 422 bad body.
- `.../profile` enrolments and `/it/me/profile` enrolments gain `lifecycle: {stage, stage_label}` (student: safe subset).
- `/admin/enrollments` rows gain `lifecycle: {stage, stage_label}`.

## 4. Risks

- A hook raising inside a writer's transaction: the writer only reads plus one insert; covered by focused tests on each hook.
- Locks: `sync` locks enrolment rows in id order; writers that already hold the row are in the same transaction.
- Performance: derivation is ~7 queries for any number of enrolments (`derive_many`).
