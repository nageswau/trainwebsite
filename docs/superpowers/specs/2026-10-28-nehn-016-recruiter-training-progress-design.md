# nehn-016 — Nearing-completion list and recruiter read-only training progress (design)

Decision: `DEC-SCOPE-309` · API §12HG · RBAC §2.220 · migration `0212_placement_report_grants` (seed only).
Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §E `nehn-016` (DERIVED_BLUEPRINT over the ORIGINAL_REQUIREMENT lines
§12 L271-276, §5 L104-109, §14 L303/L307). Dependencies nehn-004/005/008/009/010 are merged (FEEDBACK_TRACKER "Done — confirm defaults").

The session ran in autonomous mode: the owner asked for recommended answers instead of questions. Every choice marked **(builder's
default)** is `NEEDS_CONFIRMATION` and is listed in the decision register.

## 1. Intent

Recruiters see which students finish training soon, so placement work starts before the course ends, and they read a student's training
progress without admin access. Everything is read-only and served by the nehn-009 report registry; the panel is one new GET beside the
rec-036 journey. No write route, no new table.

**Non-goals.** No HR access (nehn-017). No recruiter-dashboard figure change (the rec-032 tiles keep their contract; the reports are
reached from a new "Report library" nav item). No `batches(end_date)` index: `batches` is small (one row per batch) and the queries join
it from `enrollments`; revisit with EXPLAIN on real volumes. No placement-readiness *rule*: readiness is the stored `placement_profiles`
status the IT admin already maintains.

## 2. Definitions (builder's defaults)

- **P1 Population (OD-08).** Only IT students in the placement pool: a candidate linked to the student with `opted_in` true, not
  archived, the student an active `it_student`. rec-010 (`DEC-SCOPE-138`) made placement visibility opt-in; showing anyone else would
  contradict the consent the student gave. Admins reading these reports see the same population (they have the training pack for all).
- **P2 Expected completion** = the batch `end_date` (nehn-010 C1). A student "completing in N days" has a counted seat (nehn-010 C2:
  not `pending_consent`/`rejected`/`withdrawn`/`dropped`) whose batch ends today … today + N (IST calendar days, both inclusive). N
  defaults to 15, 1-365.
- **P3 Two batches.** One row per student: the counted seat with the **latest** end date (backlog edge case). A student whose latest
  seat ends after the window is not listed. Equal latest dates list both seats.
- **P4 Progress figures** are nehn-010's calculator (`training_progress`): attendance % = (present + late + excused) / marked, "—" when
  nothing is marked; assignments graded / published; assessments passed / counted; certificate status or "Not issued".
- **P5 Readiness** = `placement_profiles.readiness_status` (default "preparation" when no profile row, as `/workflows` reads it);
  **candidate status** = `candidates.status` (available, interviewing, placed, …). An already-placed student still appears.
- **P6 No financial data.** No column is tagged `financial`; fees, discounts and payments are never selected. An unknown parameter such
  as `include=fees` is refused (422) by the registry.

## 3. Reports (new resource `reports.placement`)

Scope: placement_team, placement_manager, it_admin, super_admin → the P1 population; any other role granted the resource sees no rows
(deny by default). Grants seeded for placement_team, placement_manager and it_admin (view + download); super_admin implicit. hr_team holds
none → 403.

| id | Title | Grain / order | Columns | Filters |
|---|---|---|---|---|
| `completing-soon` | Students completing soon | student (latest seat); batch end asc, name | student code, student, phone, email, course, batch, trainer, batch ends, days left, progress %, attendance %, readiness, candidate status | days, course, batch, trainer, student |
| `placement-students` | Student placement report | student; name | student code, student, email, course (latest seat), batch ends, progress %, readiness, candidate status, applications, interviews, offers, joined | course, batch, student |

`days` is a new standard filter in the registry ("Completing within (days)", whole number 1-365). `placement-students` counts each
student's candidate's applications, interview rounds, offers and offers with joining status `joined`. Both reports are one row per
student on their latest counted seat (P3), so the course/batch/trainer filters match that seat; a pool student with no counted seat has
no training to report and is not a row.

## 4. Training panel — `GET /api/v1/recruiter/candidates/{id}/training`

Readers: placement_team, placement_manager, super_admin (the candidate writers, R11). hr_team → 403 (its own item, nehn-017); any other
role → 403. A candidate outside the pool (`candidates.load`) → 404. An external candidate (no linked student) → `{"student": false,
"seats": [], "readiness": null}`. Otherwise one row per seat (P4 figures + course, batch, trainer, starts, ends, status, progress),
newest end first, `pending_consent`/`rejected` left out, plus `readiness` (`readiness_status`, `resume_status`, `mock_interview_status`,
`aptitude_status`, `available`). Read-only, not audited (like the journey read). The web shows it as a "Training progress" card on the
candidate page with loading, error + Retry and empty states.

## 5. Web

`/recruiter/report-library` (placement_team, RECRUITER_NAV) and `/recruiter/manager/report-library` (placement_manager,
RECRUITER_MANAGER_NAV) render the shared `ReportLibraryPage`; a "Report library" nav item in both navs. `ReportView` renders `days` as a
number input. `RecruiterCandidateTraining` card under the journey.

## 6. Acceptance criteria → tests

1. Batch ends in 10 days → listed; in 20 days → not (N=15); `days=30` lists it. — pytest
2. No financial column in JSON/CSV/xlsx; `include=fees` → 422. — pytest
3. A non-opted-in (or archived) student is excluded; an opted-in one included. — pytest
4. Recruiter has no write route on training data (the panel route is GET only; the reports are GET only). — pytest (POST/PATCH → 405)
5. HR → 403 on reports and the panel; recruiter → 200. — pytest
6. Edge: null end date impossible (column NOT NULL); student in two batches → one row (latest end); dropped seat ignored; placed
   student still listed. — pytest
7. Placement report counts applications, interviews, offers, joined. — pytest
8. Panel figures equal the student-courses report's for the same seat. — pytest
9. Web: library page for a recruiter, `days` input, training card states. — vitest; browser QA.

## 7. Risks

Registry change (`days` filter) touches every report's parser — covered by nehn-009/010 tests. Rec candidate page tests (rec-009/036)
stay green: the detail response is unchanged (the panel is a separate read). Numbering may collide with parallel nehn-011/017 sessions;
renumber at merge.
