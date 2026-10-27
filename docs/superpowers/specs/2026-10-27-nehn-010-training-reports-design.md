# nehn-010 — Training reports pack: student, trainer, course, completion, attendance (design)

Decision: `DEC-SCOPE-305` · API §12HC · RBAC §2.216 · no migration.
Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §C `nehn-010` (DERIVED_BLUEPRINT over the §14 ORIGINAL_REQUIREMENT
lines 296-308; action 24). Dependency nehn-009 (`DEC-SCOPE-303`, report framework) is merged. The client's admin report template
(CI-02, §26 L785-790) has not arrived: **every field list is provisional** and is refined when it does.

The session ran in autonomous mode: the owner asked for recommended defaults instead of questions. Every choice marked **(builder's
default)** is `NEEDS_CONFIRMATION` by the client and is listed in the decision register.

## 1. Intent

Operational training reports with filters and Excel export, served by the nehn-009 registry: they appear in the existing Report library
(super admin, IT admin, trainer), page as JSON, and download as CSV/xlsx with the same rows, the throttle, the cap and the audit row.
No new router, page or component.

**Non-goals.** No `enrollments.completed_at` column (see C1). No new grants or catalogue resources; no management/HR/recruiter access
(their own items nehn-011/016/017 add scope rules). No new indexes (the grouped queries use the indexed `attendance.batch_id`,
`student_id`, `assignments.batch_id`, `assessments.batch_id`, `submissions.assignment_id`; EXPLAIN on real volumes first).

## 2. Definitions (builder's defaults)

- **C1 Completed** = a counted seat whose `progress_percent` ≥ 100 (the mgmt-017 Completion KPI and the certificate rule's default
  progress). The **completion date** is the batch `end_date` (nehn-009's reading of (d)); no actual-completion timestamp is stored.
- **C2 Seats.** `pending_consent`/`rejected` never took the seat and are left out of the counts; `withdrawn`/`dropped` are *dropped*;
  every other status is *counted* (management_training's `NOT_TAKEN`/`DROPPED`). Row-per-seat reports list every status (the
  `status` filter narrows).
- **C3 Attendance %** = (present + late + excused) / marked × 100, 2 decimals; nothing marked → empty ("—"), never 0 %.
- **C4 Assignments** graded / published total; **assessments** passed (best graded attempt ≥ pass mark) / total (scheduled, open,
  closed, published) — the certificate eligibility criteria.
- **C5 Revenue** (course-wise, `financial` class) = paid (`paid`, `succeeded`) enrolment-fee payments (`enrollment_fee`, `enrollment`)
  of the course's seats in scope. Manual ledger entries and refunds are the IT revenue dashboard's (mgmt-007), not this report's.
- **C6 Pending grading** = submissions still `submitted` in the trainer's batches.

## 3. Shared calculator (`services/training_progress.py`)

Set-based subqueries keyed by (student, batch): attendance counts, graded submissions, passed assessments, and per-batch assignment and
assessment totals, plus the percent expression. Each accepts optional `student_id`/`batch_id` (and session-date bounds for attendance)
so one seat's read stays a narrow query. `workflows._certificate_eligibility` reads its attendance/assignment/assessment figures from it
(pending fee stays where it is), so **report (e) and eligibility compute the attendance % with the same SQL** (AC2). Returned values and
the eligibility decision are unchanged (an empty attendance still reads 0 there, as before).

## 4. Reports (resource `reports.training`, scope as the pilot)

Scope: super_admin/it_admin all rows; a trainer their own batches (`Batch.trainer_id`) in **every** report (builder's default: a
trainer's own course and completion figures are not sensitive; the backlog's "a, b, e" is satisfied and AC3 holds everywhere); any
other role granted the resource sees nothing. Filters intersect the scope. Revenue passes `field_policy` (super_admin, or a role or user
given `field.financial.view` — it_admin does not hold it by default; recruiter, HR and trainer never do).

| id | Title | Grain / order | Columns | Filters |
|---|---|---|---|---|
| `student-courses` (a) | Student-wise course report | seat; enrolled desc | student code, student, course, batch, trainer, enrolled on, status, progress %, attendance %, assignments graded, assignments total, assessments passed, assessments total, certificate | from/to (enrolled), course, batch, trainer, student, status, latest, completion |
| `students-by-trainer` (b) | Students per trainer | seat; trainer, batch, student | trainer, batch, course, student code, student, status, progress % | from/to (enrolled), course, batch, trainer, student, status |
| `course-completion` (c) | Course completion | batch; batch end desc | course, batch, trainer, starts, ends, students, completed, completion %, certificates | course, batch, trainer, completion |
| `completions` (d) | Completions in a period | completed seat; batch end desc | student code, student, course, batch, trainer, batch ends, progress %, attendance %, certificate | completion, course, batch, trainer, student, latest |
| `attendance` (e) | Attendance | seat; course, batch, student | student code, student, course, batch, trainer, marked, present, absent, late, excused, attendance % | from/to (**class date**), course, batch, trainer, student, status |
| `trainers` (f) | Trainer report | trainer; name | trainer, batches, students, attendance %, average progress %, pending grading | course, trainer, completion |
| `courses` (g) | Course-wise report | course; title | course, batches, enrolments, active, completed, dropped, revenue (`financial`) | from/to (enrolled), course, trainer |

Certificate column: the certificate's status (`issued`, …) or "Not issued". Students/averages count counted seats (C2); trainer
attendance % pools classes (attended / marked across the trainer's batches, as mgmt-017). A course or trainer appears when it has a
batch in scope (and, under an enrolment-date filter, still appears with zero seats).

## 5. Acceptance criteria → tests

1. Each of (a)–(g) is in the catalogue, honours its filters and exports xlsx with the JSON's rows. — pytest
2. (e)'s attendance % equals `GET /it/certificates/eligibility/{id}`'s for the same seat; 0 marked → "—". — pytest
3. A trainer sees only own batches in every report; another trainer's id → empty. — pytest
4. Revenue is absent for a trainer and a role without `field.financial.view`, present for super_admin and after a grant. — pytest
5. Edge: student in two batches of one course (two rows), dropped seat (counted as dropped, not completed), batch with no attendance.
6. Certificate eligibility/workflow tests (nehn-031/032) stay green. — pytest
7. Web: library lists the pack; a report renders and downloads. — Playwright e2e

## 6. Risks
Eligibility refactor (covered by existing certificate tests + AC2 parity). Decimal percentages serialise as numbers in JSON and as
`66.67` text in CSV. Grouped subqueries scan the attendance table for whole-scope reports — acceptable at current volume; revisit with
EXPLAIN (nehn-009 note).
