# mgmt-011 — Salary management + employee cost ratio — exploratory browser QA (2026-10-12)

## Setup

- **Stack:** an isolated Docker Compose stack (`-p mgmt011`, web `http://localhost:13311`, api `127.0.0.1:18311`), built from
  `feature/mgmt-011` and seeded with `app.seed`.
- **Browser:** Chromium (Playwright 1.x), headless.
- **Script:** the scratchpad `qa011.js` / `qa011b.js` drove the browser.
- **Accounts:**
  - `accountant@edusphere.local` (Ravi Accountant)
  - `partner.one@edusphere.local` (Arjun Partner)
  - `superadmin@edusphere.local`
- **Month:** each run used a random far-past month, because the shared DB is never emptied.

## First pass (no code changes)

| # | Scenario | Result |
|---|---|---|
| 1 | The accountant opens Command Center → Salaries; both nav entries (Salaries, Employee cost → `#employee-cost`) are live | Pass |
| 2 | Empty month: grid of active departments, tiles at ₹0.00, ratio "—" | Pass |
| 3 | Invalid inputs (headcount −2, paid 12.345, incentives "abc") → 422 placed on the department rows, alert "Check the highlighted departments…" | Pass, see **QA-02** |
| 4 | Happy path: save Training → status "Salaries for <Month> saved.", tiles and the employee cost updated | Pass |
| 5 | Double-click Save → exactly 1 PUT | Pass |
| 6 | Reload keeps the saved values | Pass |
| 7 | Future month `?month=2999-01` → alert "Salaries can be recorded up to the current month…"; malformed `?month=garbage` → the current month | Pass |
| 8 | The ledger with `include=auto` for the month shows exactly one "Salaries · Training" automatic expense line | Pass |
| 9 | Departments: add (status message, appears in the grid); duplicate name in another case → 409 alert; deactivate → leaves the grid of a month without its row | Pass |
| 10 | The partner reads the same month | Pass |
| 11 | super_admin → "Access unavailable / Finance access required", no Salaries nav entry | Pass |
| 12 | Signed out → `/admin/login?next=%2Fmanagement%2Fsalaries` | Pass |
| 13 | Desktop 1366, tablet 820, mobile 375: no horizontal page overflow (the grid scrolls inside `.table-wrap`) | Pass, see **QA-01** |
| 14 | Console / network: only the 422 and 409 that were provoked on purpose; no 5xx, no failed requests, no page errors | Pass |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | accountant / partner | `/management/salaries` at 375 px | Open a month with ₹2,00,000 payable | Figures on one line | "₹2,00,000.0" / "0" broke inside the two-across tiles (`07-mobile-top.png`) | **Fixed**: `.salary-tiles` figures are 17 px at ≤ 420 px; re-verified in the browser |
| QA-02 | Low | accountant / partner | `/management/salaries` | Enter headcount −2 **and** paid 12.345 on one row, save | Both problems shown | Only the first message for the row was shown | **Fixed**: `rowErrors` joins every message of a row (vitest RED → GREEN); re-verified ("Employees: … · Salary paid: …") |

## Not defects

- A test-filled shared DB lists 60+ "Dept xxxxxxxx" rows (pytest departments), so the grid is long. Real data has about 10 seeded
  departments.
- it_admin signs in at `/it/login`; its 403 is covered by `test_ac2_non_finance_roles_get_403_everywhere`.

## Playwright

`tests/e2e/mgmt-011-salaries.spec.ts`: 3 passed. These also passed against the same stack: mgmt-001 command center, mgmt-004 ledger, and
mgmt-005 automatic lines (11 passed in total).
