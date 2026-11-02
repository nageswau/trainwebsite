# itc-023 — At-risk thresholds and alerts (design + plan)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-023 (classification `UNVERIFIED` PDF §6 "Flag students when attendance or
assessment performance falls below administrator-defined thresholds", §9 "reminders for … attendance or assessment concerns";
owner-approved for build in waves by Q-01, 2026-11-01). **Decision:** `DEC-SCOPE-352`. **Dependencies:** itc-002 (merged), itc-003
(merged), itc-021 (merged, PR #422); itc-022 (optional, not built — the remediation link is deferred). Q-21 is open; built with the
recommended answers below (owner: "proceed with recommended answers"), each `NEEDS_CONFIRMATION`.

## Discovery (graphify-led)

| Class | Item |
|---|---|
| MUST CHANGE | `models.py` (+`ItRiskThreshold`, `StudentRiskFlag`); new migration `0236_it_at_risk`; new `services/it_at_risk.py` (sweep + reads); `services/training_progress.py` (+ an additive `assessment_average()` builder); `notifications/events.py` (student + cleared events); `worker.py` (`itc023-at-risk` beat); new `api/it_at_risk.py` router + `main.py`; `schemas.py` (`ItRiskThresholdIn`); `services/portal.py` (IT admin "At Risk" and trainer "Notifications" headers); FE `lib/navigation.ts`, `PortalPage.tsx`, `ItStudentProfilePage.tsx`, new `lib/itAtRisk.ts`, `ItRiskThresholdsPanel.tsx`, `ItAtRiskList.tsx` |
| MAY CHANGE | the IT counselor / trainer / admin dashboards (a lead panel only, the payloads unchanged) |
| SHOULD NOT CHANGE | the certificate batch-progress `at_risk` (`workflows.py:1720`, nehn-028/031) — kept as-is (R2); `reports/training.py` at-risk report; `training_progress.attendance/seat/seats` |
| HIGH REGRESSION RISK | `training_progress` (certificates, reports, KPIs) — only an additive builder; the notifications catalogue (itc-002 tests pin the event list); PortalPage section dispatch; portal nav tests |

## Decisions (Claude's calls under "proceed with recommended answers", `NEEDS_CONFIRMATION`)

- **R1 thresholds per programme** — `it_risk_thresholds` (PK `program_id`): `min_attendance_percent` (0–100 or NULL = off),
  `min_assessment_percent` (0–100 or NULL = off), `max_consecutive_absences` (1–60 or NULL = off) and `min_sessions` (1–60, default 3:
  the attendance-% criterion waits until that many counted sessions, the first-week edge). No row, or every criterion off = the programme
  is not monitored, so **nothing is flagged on deploy** (opt-in).
- **R2 the certificate `at_risk` stays** — the batch-progress column keeps its certificate-threshold meaning (Q-21 "keep"); the new flag
  is a separate, stored, alerting record.
- **R3 criteria (per active enrolment)** — attendance: `training_progress` attended/counted (so itc-021's leave policy applies) below
  the minimum once `counted >= min_sessions`; assessment: the mean of the student's best graded attempt % over the batch's counted
  assessments they have a graded attempt for, below the minimum (no graded attempt = not judged); consecutive absences: the trailing run
  of `absent` rows by session date (late/leave/present ends the run) at or above the limit.
- **R4 the flag** — `student_risk_flags`: one row per raise (history), `cleared_at` NULL while open; a partial unique index allows one open
  flag per enrolment. It keeps the reasons (`attendance` / `assessment` / `absences`) and the figures at the last check.
- **R5 transitions** — not flagged → flagged: a row + alerts; flagged → clear: `cleared_at` + "back on track" alerts; still flagged with
  other reasons/figures: updated silently (not a transition). An open flag whose enrolment is no longer active or whose programme is no
  longer monitored is closed silently (`clear_reason = 'stopped'`; a recovery is `'recovered'`).
- **R6 recipients** — the student, the batch trainer and the itc-003 counselor (when linked and active); the IT Admin reads the list (not
  alerted). The student's notice is a separate supportive, generic event (`it.training.check_in`: "Let's get you back on track"); staff get
  itc-002's `it.training.at_risk`; a clearing is `it.training.back_on_track` for all three. No figure ever reaches a notice (itc-002).
- **R7 the job** — Celery beat `itc023-at-risk`, daily 01:30 UTC (07:00 IST), one batch at a time; per enrolment a savepoint holds the
  flag change and its notices, so a failure rolls back both, and a concurrent run hits the partial unique index / the conditional
  `UPDATE … WHERE cleared_at IS NULL` and sends nothing twice (AC2).
- **R8 readers** — `GET /it/at-risk`: IT Admin any student, IT counselor linked students, trainer own batches, others 403; `student_id`
  narrows to one student, `history=true` adds cleared flags. The student does not read flags (supportive notice only).
- **R9 remediation (itc-022)** — not built; deferred until itc-022 lands.

## Acceptance criteria (testable)

1. AC1 a flag is raised when a criterion is crossed and cleared when none is (attendance 68 % with a 75 % minimum → raised; back to 80 %
   → cleared), with history kept.
2. AC2 one alert per transition: a second run raises nothing and notifies nobody; a raise notifies the student, trainer and counselor
   once each; a clear notifies them once each.
3. AC3 thresholds are per programme: the same figures under another programme without thresholds raise nothing.
4. AC4 fewer than `min_sessions` counted sessions → no attendance flag (first week).
5. AC5 assessment average and consecutive absences criteria raise their own reasons.
6. AC6 API: thresholds GET/PUT are IT-Admin only (403 others), 422 on bad values, 404 on an unknown programme, PUT audited before/after;
   `GET /it/at-risk` is scoped (counselor sees only linked students, trainer only own batches, student 403).
7. AC7 FE: the IT Admin "At Risk" page edits thresholds and lists open flags; the student record (360) shows the badge and history; the
   counselor, trainer and admin dashboards list open flags; the trainer has a Notifications page.

## Plan (TDD, small tasks)

1. `tests/test_itc_023_at_risk.py` (RED) → migration `0236_it_at_risk` + models; migration test.
2. `training_progress.assessment_average()`; `services/it_at_risk.py` sweep → GREEN on AC1–AC5; events; worker beat.
3. API router + schemas → AC6.
4. Portal headers (admin "at-risk", trainer "notifications"), nav; FE lib, panels, profile card (vitest RED/GREEN); e2e spec.
5. Docs: DEC-SCOPE-352, API §12IX, RBAC §2.252, backlog status, RTM; graphify update.
