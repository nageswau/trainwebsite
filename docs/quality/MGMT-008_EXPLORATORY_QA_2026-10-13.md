# mgmt-008 — exploratory browser QA — 2026-10-13

- **Build:** `feature/mgmt-008`, Docker Compose project `mgmt008` (web `localhost:13008`, api `127.0.0.1:18008`), seeded demo data.
- **Tools:** Playwright (Chromium) scripts for the exploratory pass; the committed e2e `tests/e2e/mgmt-008-recruitment-revenue.spec.ts`.
- **Roles:** partner (`partner.one@`), accountant, super admin, recruiter (`placement@`, IT portal), signed out.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Partner, current month, desktop 1366 / tablet 820 / phone 375 | 9 KPI tiles in §6 order; empty state "No recruitment revenue in October 2026."; no horizontal overflow; no console errors or 5xx |
| 2 | Accountant: Command Center → "Recruitment revenue" | Lands on `/management/revenue/recruitment` |
| 3 | Financial year, reload, back | `period=year` kept after reload; intro "Financial year 2026-27 to date: …"; back returns to the page |
| 4 | `?month=2099-01` / `?month=1999-12` | Alerts "Choose this month or an earlier one" / "Choose January 2000 or a later month"; no figures |
| 5 | `?month=abc&period=week` | Malformed values dropped; current month shown |
| 6 | `?month=2000-01` (no data) | Flow KPIs 0; Placement percentage and Revenue per placement "—" |
| 7 | `?month=2019-06&period=year` (rows exist) | "Recruiter invoice payments ₹6,000.00", Total ₹6,000.00 (Σ rows = total); desktop and phone |
| 8 | Super admin, phone | Heading "Recruitment & Placement KPIs"; 8 tiles; no ₹ anywhere; no table; own sidebar link "Recruitment KPIs" |
| 9 | Recruiter (wrong role) | "Access unavailable" |
| 10 | Signed out | Redirect `/admin/login?next=%2Fmanagement%2Frevenue%2Frecruitment` |
| 11 | Duplicate submission | n/a — read-only GET form |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | partner, accountant | `/management/revenue/recruitment` with revenue rows | Open a period with revenue (scenario 7) | Spacing between the table and the note under it | The note touched the table's bottom border at every width | **Fixed** (`marginTop: 16` on the note); re-verified at 1366 and 375 |

No console errors, failed network calls or unexpected redirects in any scenario. E2E: 3 passed.
