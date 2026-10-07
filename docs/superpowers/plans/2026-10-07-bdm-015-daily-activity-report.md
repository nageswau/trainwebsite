# bdm-015 — Daily activity report — implementation plan

Spec: `docs/superpowers/specs/2026-10-07-bdm-015-daily-activity-report-design.md`. TDD per task (red → green → refactor); focused
tests only.

| # | Task | Files | Tests first |
|---|---|---|---|
| 1 | Model `BdmDailyReport` + migration `0094_bdm_daily_reports` | `app/models.py`, `alembic/versions/0094_bdm_daily_reports.py` | `tests/test_bdm_015_migration.py` (chain/head, parity, table exists, guarded, offline SQL) |
| 2 | Metric catalogue + `daily_counts` (one SELECT of scalar subqueries) | `app/services/bdm_metrics.py` | `tests/test_bdm_015_metrics.py` per type: in/out window, other BDM, not tracked, constant query count |
| 3 | Schemas | `app/schemas.py` | covered by API tests |
| 4 | BDM routes: GET preview/snapshot, POST submit (lock, 409, 422, audit) | `app/services/bdm_daily_reports.py`, `app/api/bdm_daily_reports.py`, `app/main.py` | `tests/test_bdm_015_reports.py` |
| 5 | Activity lock: `editable(..., submitted)`, create/update/delete 409 under the advisory lock | `app/services/bdm_activities.py`, `app/api/bdm_activities.py` | `tests/test_bdm_015_activity_lock.py`; rerun bdm-009 tests |
| 6 | Manager grid, detail, comment | same API/service files | `tests/test_bdm_015_manager.py` |
| 7 | Web lib + components: `lib/bdmDailyReports.ts`, `BdmDailyReportCounts`, `BdmDailyReportSubmit`, `BdmDailyReportComment` | `apps/web/lib`, `apps/web/components` | vitest `tests/unit/bdm015*.test.ts(x)` |
| 8 | Pages + nav: `/bdm/daily-report`, `/bdm/manager/daily-reports`, `/bdm/manager/daily-reports/[bdmId]` | `apps/web/app/bdm/...`, `lib/navigation.ts` | nav tests updated; Playwright `tests/e2e/bdm-015-daily-report.spec.ts` |
| 9 | Docs: decision register `DEC-SCOPE-099`, backlog status, API contract / RBAC addenda | `docs/...` | — |

Verification per task: `pytest tests/test_bdm_015_*.py tests/test_bdm_009_*.py -q`, `ruff`, `tsc`, `eslint`, vitest for touched
files; at the end `next build` and Playwright for bdm-015 + bdm-009.
