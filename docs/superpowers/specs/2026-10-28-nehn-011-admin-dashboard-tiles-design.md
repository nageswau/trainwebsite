# nehn-011 — Admin dashboard: enrolments, student progress, course-wise and fee tiles (design)

Status: builder's design, 2026-10-28. Decision `DEC-SCOPE-311`; API §12HI; RBAC §2.222. No migration.
Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` § nehn-011 (backlog rows 287-295, 350). Dependency nehn-010 is merged
(PR #373). The client's admin report template (CI-02) has not arrived, so the tile list is the backlog's list, `NEEDS_CONFIRMATION`.

## Intent
The admin dashboard shows only counts of users, enquiries, revenue, programmes and universities. Admins also need to see enrolments,
student progress, students at risk, course fees and a course-wise summary. Each tile opens the nehn-010 report it summarises.

## Goals
- G1. `GET /admin/dashboard` gains an additive `training` block. Every existing key keeps its value and meaning.
- G2. Each tile value is computed from the same query as the report it links to, so tile and report always agree (AC1).
- G3. The training block is present only for a caller who holds `reports.training.view`. Overseas admin has no such grant by default,
  so they see their division's figures and no training tiles (AC2). Fee values are present only with `field.financial.view` (AC3).
- G4. The tiles render on the Super Admin dashboard (`/admin`) and the IT Admin dashboard (`/it/admin/dashboard`). They link into
  that portal's report library.

## Non-goals
- No cache. The backlog's 60 s cache is `NEEDS_CONFIRMATION`; the aggregates are a few grouped queries.
- No new report. No change to the overseas admin dashboard, the portal payload metrics, or certificate eligibility.
- No change to what the existing `revenue` key means (every paid payment in the division).

## Builder's calls (each `NEEDS_CONFIRMATION` until the client template)
| # | Call |
|---|---|
| C1 | **Enrolments / Active / Completed / Dropped** are the column totals of the course-wise report (`courses`), unfiltered. Enrolments = seats taken (not `pending_consent`/`rejected`); active = counted seats below 100 %; completed = counted seats at 100 %; dropped = `withdrawn`/`dropped`. |
| C2 | **Completed** links to `completions` (one row per completed seat; its unfiltered row count equals C1's completed). |
| C3 | **Average progress** = the mean `progress_percent` of counted seats (rounded to 1 dp; `null` → "—" when there are none). Links to `student-courses`. |
| C4 | **At-risk students** = counted seats with at least one class marked and attendance % below the certificate rule's `min_attendance_percent` (configurable; default 75). This is the nehn-028 trainer view's `at_risk`. New standard report filter `attendance_below` (whole number 1-100) on the `attendance` report. The tile links to `attendance?attendance_below=<threshold>`, and its value is that report's row count. |
| C5 | **Course fees collected / pending** are totals of the `courses` report's `revenue` and a new `pending_fees` column: the seats' enrolment-fee payments in `pending`/`overdue` (`accounts.UNPAID`). Both are `financial`. |
| C6 | **Course-wise mini table** = the first 5 rows (QA-02) of the `courses` report in its own order, with the financial columns stripped by the field policy. A link opens the full report. |
| C7 | The training block's scope is the reports' scope: super_admin and it_admin see every row. |

## API (additive)
```
GET /api/v1/admin/dashboard   (ensure_admin, unchanged)
{ ...existing keys...,
  "training": {                                   # only with reports.training.view
    "enrolments": int, "active": int, "completed": int, "dropped": int,
    "average_progress": number|null, "at_risk": int, "at_risk_threshold": int,
    "fees_collected": number, "fees_pending": number,    # only with field.financial.view
    "courses": {"columns": [{key,label}], "items": [...], "total": int}   # field policy applied
  } }
```
`GET /reports/attendance?attendance_below=75` is new. Out-of-range or non-integer values return 422 "Attendance below % must be a whole
number from 1 to 100". Other reports refuse the filter with 422, as for any undeclared filter.

## Frontend
- New server component `components/AdminTrainingTiles.tsx({training, basePath})`. It renders the `action-card`, a tile grid of links
  (reusing the `metric`/`cards` design classes) and the mini table (`.table.stack` with `data-label`). With no `training` block it
  renders nothing. An empty system shows zeros, and "—" for the average.
- `/admin/page.tsx` passes `d.training` with `/admin/report-library`.
- `PortalPage` adds the tiles as the lead of `it/admin` dashboard. They read `/admin/dashboard`, and a failed read drops the tiles
  only.
- `ReportView` gets a number input for `attendance_below`, and `FILTER_LABELS` gets its label.

## Security
Auth unchanged (`ensure_admin`). The training block's gate is a grant check (`user_has_grant`). Rows are scoped by the report query.
Financial values are omitted, not nulled, without `field.financial.view`. The filter value is parsed to an int (no SQL text). No new
logging of values.

## Tests (TDD)
Backend `tests/test_nehn_011_admin_dashboard.py`, on the nehn-010 fixture:
1. Tile totals equal the linked reports' totals (AC1), including at-risk = attendance report row count with `attendance_below`.
2. Overseas admin: no `training` key; the existing keys are unchanged (AC2).
3. it_admin without the financial grant: no fee keys, no revenue/pending column in the mini table. With the grant, the keys are present (AC3).
4. A role without dashboard access gets 403. An empty scope (a fresh DB slice can't be guaranteed) is checked with the unit
   `average_progress is None` path through a trainer-less scope.
5. `attendance_below` validation: 0, 101 and "x" return 422; an undeclared report returns 422.
6. `courses.pending_fees` equals the hand-counted pending fee (nehn-010 fixture: s2 1000 pending).
Web vitest: `AdminTrainingTiles` renders the links/values, the hidden fee tiles and the empty-state "—". The Super Admin page test still
passes. Playwright `nehn-011-admin-dashboard.spec.ts`: super admin tile → report pre-filtered; IT admin sees tiles; overseas admin does not.

## Plan (small tasks)
1. RED/GREEN: registry `attendance_below` filter + attendance report condition.
2. RED/GREEN: `courses.pending_fees` financial column; update the nehn-010 class assertion (deliberate additive change).
3. RED/GREEN: `services/reports/dashboard.py::training_tiles(db, user)` + the `admin.py` dashboard wiring.
4. RED/GREEN: web component + pages + ReportView filter; tsc, lint, build.
5. Docs: decision register, API contract, RBAC matrix, backlog status, feedback tracker.
6. Docker QA (browser + Playwright).

## Regression risks
The nehn-010 report tests (columns of `courses`), `SuperAdminDashboard.test.tsx`, the e2e specs that land on the admin dashboards
(additive only), and certificate tests (untouched).
