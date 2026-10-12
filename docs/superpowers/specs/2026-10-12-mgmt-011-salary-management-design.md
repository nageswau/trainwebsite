# mgmt-011 — Salary management + employee cost ratio — design

- **Feature:** `mgmt-011` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-011). Depends on mgmt-004 (merged, PR #246). It also reads
  mgmt-005's `ledger.lines()` (merged, PR #249).
- **Evidence:** `EVID-017` §9 (lines 356–386, `DERIVED_BLUEPRINT`) has 7 figures: total employees, department-wise salary, salary
  payable, salary paid, incentives, commissions and employer cost. It also has "Total Monthly Employee Cost", which it compares against
  revenue, and the Employee Cost Ratio = employee cost ÷ revenue × 100. The source calls it "a very important business KPI". Management
  M6 and M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`) set department totals per month with no per-person salaries, and give the finance
  tier only, with super_admin excluded. Backlog Appendix B defines R6 and R7.
- **Decision:** `DEC-SCOPE-193` (provisional number). SM1–SM14 below are **recommended defaults, `UNVERIFIED`**. I took them on the
  owner's instruction to proceed with recommended answers. They answer Q-13 (the department list) as an interim default. The second half
  of Q-13 (the role → department mapping for productivity) stays open, so headcount is entered, not counted.

## 1. Intent

The accountant, or a partner, records each month's salary totals per department. The page then shows the month's employee cost and
the Employee Cost Ratio against ledger revenue.

Saved salary cost reaches the ledger by itself as an automatic expense line. It is never entered twice. super_admin and every other
role are refused at the route, so no salary figure reaches them.

## 2. Decisions (SM1–SM14)

| # | Point | Answer |
|---|---|---|
| SM1 | Departments (Q-13 interim) | A managed list `departments`: name 2–80 characters, unique ignoring case, plus `active`. Seeded with Management, Counseling, Telecalling, Business Development, Training, Placement & Recruitment, Partnerships, Marketing, Accounts & Administration, and Operations & Support |
| SM2 | Managing departments | Partner and accountant can add, rename, deactivate and reactivate. A deactivated department keeps its months. It is left out of a month's grid unless that month already has its row |
| SM3 | Month row | One row per (month, department). `headcount` is an integer 0–100 000. `payable`, `paid`, `incentives`, `commissions` and `employer_cost` are rupees: Numeric(14,2), ≥ 0, at most 2 decimals. INR only (ML5). `employer_cost` = the employer's contributions on top of salary (PF, ESI, insurance) |
| SM4 | Write | `PUT /management/salaries?month=YYYY-MM` with `{rows: [...]}` replaces the month: rows sent are inserted or updated, and rows left out are removed. `rows: []` clears the month. A duplicate department → 422. An unknown department → 422. An inactive department that has no row yet in that month → 422. A month after the current IST month → 422 |
| SM5 | Paid > payable | Allowed and saved. The row carries the warning `paid_exceeds_payable`, and the grid shows it |
| SM6 | Total employee cost (R6) | Paid + incentives + commissions + employer cost, per row and in total. This is cash basis, like the ledger (MA2). Payable is shown but is not a cost |
| SM7 | Employee Cost Ratio (R7) | R6 ÷ revenue × 100, rounded half-up to 2 decimals. Revenue = the month's counted ledger income: approved manual entries + INR automatic lines, all verticals (mgmt-005 `lines_totals`). `null` (shown "—") when revenue is 0 |
| SM8 | Ledger line | Each saved department row whose R6 > 0 is an automatic expense line in `ledger.lines()`. Source `salary`, label "Salaries", vertical `shared`, dated the month's last day, description "Salaries · <department>", INR, counted. It is computed on read and nothing is copied (MA1). It counts once saved, with no approval step: the salary audit trail covers it |
| SM9 | Counted once (AC3) | The migration deactivates the seeded "Salaries" ledger expense category, so salary cost cannot also be recorded as a new manual entry. Existing entries keep it (ML3). If a partner reactivates it, manual salary entries count too. The page says so |
| SM10 | Access | Finance tier only (partner, accountant), using the ledger's `require_finance`. super_admin gets 403 "Finance access required"; every other role gets 403. Q-33: a department with a headcount of 1 is shown unmasked to the finance tier |
| SM11 | Audit | `mgmt.salary` (finance): one row per PUT that changes something. Entity = the month, fields = the changed field names, count = the department rows changed. `mgmt.department` (finance): create/update with field names. No salary values in the audit |
| SM12 | Concurrency | A PUT takes a transaction-scoped advisory lock on its month, so two saves of one month serialise and the last one wins. A department name race → 409 via the unique index |
| SM13 | Page | `/management/salaries?month=YYYY-MM` (default: the current IST month). It has a month form, KPI tiles (the 7 §9 figures + total employee cost, revenue and ratio), an editable grid per department with a totals row and Save, and a Departments section. Both nav entries ("Salaries", "Employee cost") go live |
| SM14 | Read | `GET /management/salaries?month` → `{month, current_month, rows, totals, revenue, ratio, updated_at, updated_by}`. `rows` are the active departments plus any inactive department that has a row in the month. A department with no row has `entered: false` and null figures. `GET/POST/PATCH /management/departments` manage the list |

## 3. Data

Migration `0153_salaries` (provisional), guarded like 0150 and 0151:

- `departments` (id, name, active, created/updated by, timestamps) with the unique index `lower(name)`. Seeded when the table is empty.
- `salary_month_totals` (id, `month` date = the 1st, department_id FK RESTRICT, headcount, payable, paid, incentives, commissions,
  employer_cost, created/updated by, timestamps). It has UNIQUE(month, department_id), CHECKs (≥ 0, month is day 1) and the index
  `month`.
- The update `ledger_categories SET active = false WHERE kind='expense' AND name='Salaries'` (SM9). downgrade() reactivates it and
  refuses while salary rows exist.

## 4. Components

- `services/salaries.py`: department CRUD helpers, `month_view(db, month)` and `save_month(db, user, month, rows)`.
- `services/ledger.py`: a sixth `_auto("salary", …)` source in `lines()`.
- `services/management_audit.py`: the two kinds.
- `api/management.py`: the salaries and departments routes.
- `schemas.py`: `LEDGER_AUTO_SOURCES` + "salary", plus the salary and department schemas.
- Web:
  - `lib/salaries.ts` (types, month parsing, URLs, the ratio text).
  - `components/SalaryGrid.tsx` (KPIs + grid + save).
  - `components/Departments.tsx`.
  - `app/management/salaries/page.tsx`.
  - `lib/management.ts` hrefs.
  - The `lib/managementLedger.ts` source label.

## 5. Error handling

| Status | When |
|---|---|
| 401 | Signed out |
| 403 | No finance tier |
| 422 | A bad or future month, values out of range, or a duplicate, unknown or inactive department (each placed on its field) |
| 409 | A duplicate department name |

The page shows its access card on 401/403, an error notice when the read fails, the inline 422 message on save, a disabled Save while
saving, and an empty state when there are no departments.

## 6. Testing

- **Backend `test_mgmt_011_salaries.py`:**
  - AC1: the ratio matches the formula.
  - AC2: super_admin gets 403 on every route.
  - AC3: one ledger salary line per department row, and the Salaries category is inactive.
  - PUT replaces the month.
  - Validation 422s, the paid > payable warning, a future month refused, an inactive department.
  - Audit rows and department CRUD.
- **`test_mgmt_011_migration.py`:** single head, model = migration.
- **Web vitest:** `salaries.test.ts` and `SalaryGrid.test.tsx`.
- **Playwright `mgmt-011-salaries.spec.ts`:** the accountant saves a month and sees the cost and ratio; super_admin is refused.
