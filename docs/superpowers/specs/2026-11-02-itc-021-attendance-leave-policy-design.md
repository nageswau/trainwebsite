# itc-021 — Attendance with approved leave, percentage policy, session link and audited corrections (design + plan)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-021 (classification `UNVERIFIED` PDF §4 "present/absent/late/approved leave …
attendance correction history", §6 "calculation policy configurable for approved leave"; owner-approved for build in waves by Q-01,
2026-11-01). **Decision:** `DEC-SCOPE-349`. **Dependencies:** itc-001 (merged, PR #408), itc-020 (merged, PR #417). Q-19 is open; built
with the recommended answers below (owner: "proceed with recommended answers"), each `NEEDS_CONFIRMATION`.

## Discovery (graphify-led)

| Class | Item |
|---|---|
| MUST CHANGE | `services/training_progress.py` (the shared attendance SQL: `ATTENDED` hard-codes excused); `models.Attendance` (+`marked_by_id`, `session_id`), `models.CertificateRule` (+`leave_policy`); `api/workflows.py` `mark_attendance`, `review_attendance_correction`, certificate rules GET/PUT; `schemas.CertificateRulesIn`; `services/management_training.py` (its own `ATTENDED` copy); `services/portal.py` (two Python/SQL copies of the attended set); `services/reports/training.py`, `services/reports/placement.py`, `api/hr_students.py` (denominator); new migration `0233`; FE `TrainerWorkflowForm.tsx`, `AttendanceCorrectionPanel.tsx`, `AdminCertificatePanel.tsx`, `lib/certificates.ts`, `lib/hrStudents.ts` |
| MAY CHANGE | report column label "Excused" → "Approved leave" (IT reports only); `TrainerProgressPanel` (reads the rules, unchanged shape) |
| SHOULD NOT CHANGE | School attendance (`SchoolAttendance`, `lib/attendance.ts`, `ATTENDANCE_STATUSES` in models — a different module whose "excused" is its own); skills attendance; `management_audit` |
| HIGH REGRESSION RISK | certificate eligibility (nehn-031), batch progress (nehn-028), training reports (nehn-010/011), management training KPIs (mgmt-017), HR student view (nehn-017), placement reports (nehn-016), student portal (stu-006) — all read the attended/marked figures |

## Decisions (Claude's calls under "proceed with recommended answers", `NEEDS_CONFIRMATION`)

- **L1 (Q-19a) approved leave = the existing `excused` value.** The stored/API value stays `excused` (no data rewrite, no API break, the
  School module's own "excused" untouched); every IT screen labels it **"Approved leave"**.
- **L2 (Q-19b) policy** `certificate_rules.leave_policy` ∈ `attended` | `excluded` | `absent`, default **`attended`** — today's rule, so
  no figure changes on deploy. `attended`: leave counts as attended; `excluded`: leave is left out of both numerator and denominator;
  `absent`: leave counts in the denominator only. Edited on the existing Certificate rules panel (grant `certificates.configure`, the
  IT Admin) and audited with before/after in the existing `certificate_rules.update` row.
- **L3 (Q-19c) retroactive.** The percentage is computed live from the rows, so a policy change applies to every later read and
  eligibility check (exactly like the thresholds today); issued certificates keep their own snapshot.
- **L4 `marked_by_id`** (nullable FK users): set when a trainer/admin creates or overwrites a row and when a correction is approved
  (the reviewer). Existing rows stay NULL ("unknown"); nothing is backfilled.
- **L5 `session_id`** (nullable FK `live_sessions` ON DELETE SET NULL): auto-linked at marking time to the date's single
  non-cancelled live session of the batch; NULL when there is none or more than one. itc-020's timetable classes are computed, not
  stored, so they have no id to link. No payload change.
- **L6 audited corrections.** An approved correction that changes the status writes itc-001's `attendance.update` row
  (`{status: [old, new]}`) besides the existing `attendance.correction_review` row.
- **L7 one SQL definition.** `training_progress.attended()` / `counted()` are the two filter expressions; they read the policy through a
  scalar subquery on `certificate_rules`, so no caller gains a query. `attendance()` gains a `counted` column (denominator) and keeps
  `marked` (rows marked, the "Classes marked" figure). Every percentage (`seat`, `seats`, reports a/d/e/f, placement, HR view,
  management KPIs, student portal dashboard and attendance section) becomes `attended / counted`.
- **L8 edge:** `excluded` with only leave marked → `counted = 0` → the % is "—" (NULL); eligibility already treats a NULL % as 0.

## Acceptance criteria (testable)

1. AC1: with policy `excluded`, 8 present + 2 leave + 0 absent → 100 % in `seat()` (certificate eligibility), `seats()` (batch
   progress), report (e) and the student portal; with `absent` → 80 %; with `attended` → 100 %; management KPI follows.
2. AC2: an overwrite (trainer re-mark) and an approved correction each write `attendance.update` with before/after; `marked_by_id` is
   the actor.
3. AC3: a trainer marking another batch → 403 (existing, regression).
4. AC4: GET rules returns `leave_policy`; PUT without it keeps the stored one (backward compatible); an invalid value → 422; a
   non-admin → 403.
5. AC5: marking a date with exactly one non-cancelled live session links `session_id`; otherwise NULL.
6. AC6: FE — the register, the correction panel, the HR view and reports say "Approved leave"; the rules panel shows a policy select.

## Plan (TDD, small tasks)

1. Test file `tests/test_itc_021_attendance_policy.py` (RED) → migration `0233_attendance_leave_policy` + model columns.
2. `training_progress.attended/counted/policy`, `attendance().counted`; switch callers (reports, placement, hr_students,
   management_training, portal) → GREEN; rerun nehn-010/028/031, mgmt-017, stu-006, nehn-017, nehn-016 tests.
3. `mark_attendance` (marked_by, session link) and `review_attendance_correction` (audit + marked_by).
4. Rules GET/PUT `leave_policy`.
5. FE labels + rules select (vitest RED/GREEN), e2e spec `itc-021-attendance-policy.spec.ts`.
6. Docs: DEC-SCOPE-349, API §12IU, RBAC §2.249 (unchanged grants noted), backlog status, RTM.
