# mgmt-011 — Salary management + employee cost ratio — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-011-salary-management-design.md`.

Each task is TDD: test first (RED), minimum code (GREEN), then refactor. Run focused tests only; full regression is deferred to its own
session.

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | `Department` and `SalaryMonthTotal` models + CHECKs. Migration `0154_salaries`: guarded, seeds departments, deactivates the "Salaries" category, downgrade refuses with data | `test_mgmt_011_migration.py` | `models.py`, `alembic/versions/0154_salaries.py` |
| 2 | Schemas: the month-row validation (SM3), duplicate departments (SM4), output | `test_put_rejects_*` | `schemas.py` |
| 3 | `GET/POST/PATCH /management/departments` (SM1, SM2, SM11) | `test_department_*` | `services/salaries.py`, `api/management.py`, `management_audit.py` |
| 4 | `PUT /management/salaries`: replace the month, advisory lock, future/inactive/unknown 422, audit (SM4, SM11, SM12) | `test_put_*` | same |
| 5 | `GET /management/salaries`: rows, totals, R6, warnings, revenue, ratio (SM5–SM7, SM14) | `test_ac1_*`, `test_get_*` | same |
| 6 | The ledger `salary` automatic source (SM8, SM9) | `test_ac3_*` | `services/ledger.py`, `schemas.py` |
| 7 | Access on every route: finance only; super_admin and others 403; 401 (SM10) | `test_ac2_*` | `api/management.py` |
| 8 | Web lib: types, month param, URLs, ratio/money text, nav hrefs, ledger source label | `salaries.test.ts`, `management.test.ts` | `lib/salaries.ts`, `lib/management.ts`, `lib/managementLedger.ts` |
| 9 | Page + `SalaryGrid` (KPIs, grid, totals, warning, save, states) + `Departments` | `SalaryGrid.test.tsx` | `components/`, `app/management/salaries/page.tsx` |
| 10 | Playwright: the accountant saves a month (cost + ratio + the ledger line); super_admin is refused | `mgmt-011-salaries.spec.ts` | `tests/e2e/` |
| 11 | Docs: DEC-SCOPE, API §, RBAC §, DATA_MODEL, backlog status, QA report (written after merging main) | — | `docs/` |

**Regression watch:**

- mgmt-005 tests: the new UNION member shape and the `LedgerAutoLine` Literal.
- The mgmt-002 KINDS tests.
- The mgmt-004 category tests: "Salaries" is now inactive in the shared DB.
- `/admin/audit` hides the new finance kinds (MA8, automatic through `hidden_from_admin_audit`).
- `management.test.ts` (the nav entries).
