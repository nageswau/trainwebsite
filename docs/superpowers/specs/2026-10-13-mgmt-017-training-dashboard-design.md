# mgmt-017 — Training & trainer dashboard (design)

**Source:** `EVID-017` §12 "TRAINING & TRAINERS" (lines 469–511, `DERIVED_BLUEPRINT`): 11 Training KPIs (Total courses, Active
batches, Students, Trainers, Attendance, Completion, Dropouts, Assessments, Certifications, Placement-ready students, Placements) and 7
Trainer-performance metrics (Students trained, Attendance, Completion, Student feedback, Assessment results, Batch performance, Placement
outcomes). Backlog `MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-017 (depends on mgmt-003, merged in PR #244). Open question Q-19.

**Authority:** every TR answer below is a **recommended default, `UNVERIFIED`**, taken on the owner's standing instruction to proceed
with recommended answers. TR10/TR12/TR15 answer Q-19. Registered as `DEC-SCOPE-208` (provisional numbering, after mgmt-012's 207).

## What the data supports (verified in code)

- `Program` (catalogue, `active`), `Batch` (`status` ∈ upcoming/active/completed/cancelled, one `trainer_id`, `start_date`/`end_date`).
- `Enrollment.status`: `pending_consent` → `active` (consent / admin approve), `rejected` (admin). The admin enrolment edit
  (`PATCH /admin/enrollments/{id}`) accepts any status string; nothing in a workflow writes `withdrawn`, `dropped` or `completed`.
  `progress_percent` 0–100 is set by the batch's trainer; 100 is the certificate rule's "completed course".
- `Attendance.status` ∈ present/absent/late/excused; attended = present/late/excused over marked rows (workflows.py certificate rule).
- `AssessmentAttempt`: graded attempts carry `percentage`; passed = best graded percentage ≥ `Assessment.pass_percent` (certificate rule).
- `Certificate.status` is always `issued`, dated `issued_on`.
- `CourseFeedback.rating` 1–5 per student per batch; nothing aggregates it today.
- `PlacementProfile.readiness_status` is **free text** (no vocabulary, typed in a plain input); `available` / `withdrawn` are booleans.
- Placement = `JobOffer.joining_status = 'joined'` dated `actual_joining_date` (rec-023; the recruiter and management-recruitment
  dashboards' rule), reached through `JobApplication.student_id`.
- `LiveSession.trainer_id` is written but read by no one; every trainer view goes through `Batch.trainer_id`.

## Decisions (TR1–TR16)

| # | Point | Answer |
|---|---|---|
| TR1 | Period | `from` / `to`, inclusive IST dates, default this IST month; start after end or > 366 days → 422 (bdm-024 P2, as mgmt-018 CS2) |
| TR2 | Batches in the period | Batches not `cancelled` whose run (`start_date`..`end_date`) overlaps the period. Students, Completion, Dropouts and every trainer figure except placements are read over these batches |
| TR3 | Counted enrolment | An enrolment whose status is not `pending_consent`, `rejected` or `withdrawn`/`dropped` — a student who actually took the seat. (mgmt-003 S3 "IT Training Students" is unchanged; it also counts pending ones) |
| TR4 | Total courses | Active programs in the catalogue (`Program.active`), now |
| TR5 | Active batches | Batches with status `active`, now |
| TR6 | Students | Distinct students with a counted enrolment in a batch in the period |
| TR7 | Trainers | Active `trainer` users, now (= mgmt-003 S11) |
| TR8 | Attendance | Attended ÷ marked attendance rows with a session date in the period, %, one decimal; `null` when nothing was marked (a missing row is "not marked", never absent) |
| TR9 | Completion | Of the counted enrolments in the period's batches, the share at 100% progress (the certificate rule's completed course), %, one decimal; `null` with none |
| TR10 | Dropouts | Enrolments in the period's batches whose status is `withdrawn` or `dropped` (set by an admin's enrolment edit; no other flow drops a student). A count |
| TR11 | Assessments | Assessments (not `draft`) scheduled in the period |
| TR12 | Certifications | Certificates issued in the period |
| TR13 | Placement-ready | Students with a placement profile marked **available** and not withdrawn, now. `readiness_status` is free text, so it is not used |
| TR14 | Placements | Distinct students with a counted enrolment (any batch, any time) whose job offer was **joined** with an actual joining date in the period |
| TR15 | Trainer table | Every `trainer` user, active or not, one row each (name order). A batch is credited to its `Batch.trainer_id` only; a live session run by another trainer does not make the batch theirs (no double counting). Columns: Batches (in the period, context), Students trained (TR6 per trainer), Attendance (TR8 over their batches), Completion (TR9), Student feedback (average `CourseFeedback` rating of their period batches, one decimal, out of 5, with the response count; `null` with none), Assessment results (pass rate: of the student-assessment pairs with a graded attempt on their batches' assessments scheduled in the period, the share whose best graded % ≥ pass mark; `null` with none), Batch performance (average progress % of counted enrolments in their period batches — RPT-001's course figure, per trainer), Placement outcomes (TR14, students of any of their batches) |
| TR16 | Access and shape | Operational tier (partner, super_admin); accountant 403 "Operational access required"; others 403 "Management access required"; signed out 401. Response: `from`, `to`, `as_of`, `kpis` (key, label, definition, value), `trainer_figures` (key, label, definition), `trainers` (rows). Command Center "Training" (Students) and "Trainers" (People, `#trainers`) go live; super admin sidebar "Management training figures". Read-only, no audit row; no money |

The KPI tiles are company-wide (not the sum of trainer rows: a student can sit in two trainers' batches, and a batch can have no trainer).

## Architecture

- `services/management_training.py` — `KPIS`, `TRAINER_FIGURES`, `dashboard(db, start, end, now)`. One scalar SELECT for the KPIs
  (scalar subqueries, as mgmt-003) and one grouped query per trainer figure, keyed by `Batch.trainer_id` — the query count does not grow
  with trainers. Read-only.
- `api/management.py` — `GET /management/training?from&to`, `_operational(user)` then `period()`.
- `schemas.py` — `ManagementTrainingOut` (+ KPI, figure, trainer row models).
- Web: `lib/managementTraining.ts`, `components/ManagementTraining.tsx`, `app/management/training/page.tsx` (server-rendered period form,
  as mgmt-018), `lib/management.ts` (Training, Trainers hrefs), `lib/navigation.ts` (super admin entry).

## UI

Period form → note (period, IST, trainer count) → "Training KPIs" tiles (11; `null` shares say "Nothing marked" / "No enrolments") →
"Trainer performance" table (scrolls in its own box on a phone) with Inactive marks; "—" where a trainer has no figure. Empty state
when there are no trainer accounts. 422 message shown; 401/403 → access card.

## Testing

Backend (`test_mgmt_017_training.py`): access matrix; period default/422; per-trainer exact figures over a fixed past period with
fresh trainers/programs (shared DB); TR2 overlap, TR3 counted enrolment, TR8 not-marked rule, TR9/TR10, assessment pass rate best-attempt
rule, feedback average, placement crediting; KPI figures move by exactly the fixture's contribution (delta checks, shared DB); TR7 equals
the snapshot's Trainers. Web: vitest for lib + component; Playwright e2e for the page.
