# nehn-028 — Trainer per-student progress view (design)

**Source:** backlog `nehn-028` (`docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md`), requirement §10 "View student progress", L232-236.
**Decision:** `DEC-SCOPE-305`. **API:** §12HC. **RBAC:** §2.216. **Migration:** none.

## Intent

A trainer sees, for each student of one of their batches, the four progress factors the requirement names — attendance,
assignments, assessments, overall completion — plus certificate eligibility with the reasons it is not met, so at-risk students can
be spotted mid-course. Today the Student Progress page shows only the hand-set progress % and its subtitle promises an
"attendance risk" that is never shown.

## Goals

- `GET /api/v1/workflows/it/batches/{batch_id}/progress` — one row per seated enrolment of the batch.
- The numbers are the certificate eligibility numbers: `_certificate_eligibility` is refactored onto a shared, set-based
  calculator (`app/services/training_progress.py`) used by the eligibility endpoint, the issue path, the coordinator queue and the
  new view. AC1 then holds by construction.
- The trainer page leads with a progress table: batch picker, search, "at risk only", "show dropped/withdrawn", sortable columns,
  and a per-student details row (each criterion against its threshold, the reasons).
- The subtitle says what is shown (AC3).

## Non-goals

- Progress % stays manual (the existing "Update learner progress" form). Computing it is `NEEDS_CONFIRMATION` (backlog open question).
- No IT-admin page: the API admits it_admin (any batch) for nehn-010/admin reuse; the admin UI is a follow-up.
- No export (nehn-010 owns reports).

## Decisions (builder's calls, `NEEDS_CONFIRMATION` where marked)

1. **Scope:** trainer — own batches only (another trainer's batch → 403; unknown batch → 404); it_admin and super_admin — any IT
   batch. Other roles 403. Same `_require(... {"trainer","it_admin"}, "it")` rule as the other trainer endpoints.
2. **Rows:** enrolments whose status is not `pending_consent`/`rejected` (never seated). Dropped/withdrawn rows are returned with
   their status; the UI hides them by default and shows them greyed on demand (`NEEDS_CONFIRMATION`: hidden vs greyed).
3. **Attendance:** % exactly as eligibility (present + late + excused over recorded sessions). With no recorded session the API
   still returns 0 (eligibility does), plus `attendance_sessions: 0`; the UI shows "—" and no risk flag.
4. **At risk:** `attendance_sessions > 0 and attendance_percent < rules.min_attendance_percent` (the admin-configurable nehn-031
   threshold, default 75).
5. **Assignments:** submitted (distinct published assignments with any submission) / graded (eligibility's count) / total published.
6. **Fee:** a trainer gets `fee_clear: true|false` and the reason "Fee payment pending" — never the amount (the new endpoint is
   not a financial surface; the existing eligibility endpoint is unchanged).
7. **Reasons:** computed server-side from the same criteria, so the UI never re-derives eligibility.
8. **Performance:** the calculator runs one grouped query per factor for any number of enrolments (no N+1). The queue's per-row
   loop moves onto it too.

## Response

```json
{
  "batch": {"id": "…", "name": "…", "program": "…", "start_date": "…", "end_date": "…"},
  "rules": {"min_progress_percent": 100, "min_attendance_percent": 75},
  "students": [{
    "enrollment_id": "…", "student_id": "…", "student_code": "…", "student": "…", "enrollment_code": "…", "status": "active",
    "progress_percent": 40, "attendance_percent": 60.0, "attendance_sessions": 5, "at_risk": true,
    "assignments_submitted": 2, "assignments_graded": 1, "assignments_total": 3,
    "assessments_passed": 0, "assessments_total": 1, "fee_clear": true,
    "eligible": false, "reasons": ["Progress 40% (needs 100%)", "Attendance 60% (needs 75%)", "2 of 3 assignments not graded", "1 of 1 assessment not passed"],
    "certificate_issued": false
  }]
}
```

## Acceptance criteria (from the backlog)

1. For each student, attendance % and eligibility match `GET /it/certificates/eligibility/{enrollment_id}`.
2. Students below the attendance threshold are flagged.
3. The subtitle claim matches what is shown.
4. Another trainer's batch returns 403; unknown 404.

## Plan

1. RED/GREEN `tests/test_nehn_028_batch_progress.py`: scope (own/other/unknown/admin/student), parity with the eligibility endpoint,
   at-risk flag, no-sessions edge, dropped rows, reasons, fee without amount, subtitle.
2. Extract `training_progress.criteria(db, enrollments, rules)`; `_certificate_eligibility` and the queue call it. Existing
   certificate tests (nehn-031, adm-006, stu-007, nehn-032) stay green.
3. Endpoint + portal subtitle/header-only.
4. Web: `TrainerProgressPanel.tsx` (vitest RED/GREEN) mounted first in the student-progress actions; `PortalSection` gets
   `table={false}` for this header-only section.
5. e2e `nehn-028-trainer-progress.spec.ts`; browser QA desktop/tablet/mobile.
6. Docs: DEC-SCOPE-305, API §12HC, RBAC §2.216, RTM, tracker, backlog status.

## Regression risks

Certificate eligibility refactor (issue, queue, override snapshot); the nehn-031 e2e that drives the Recommend form on this page.
