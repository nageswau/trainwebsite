# mgmt-022 — Exploratory QA (School dashboard + school money), 2026-10-14

Stack: isolated Docker Compose project `mgmt022` (web `http://localhost:13022`, api `127.0.0.1:18022`), `feature/mgmt-022` with migration
`0161_school_values` at head, demo seed loaded. Browser: Playwright Chromium (headless), scripted exploratory pass; API checks with curl.
The shared stack database also holds backend test rows (72 schools), so figures are checked for behaviour, not exact counts.

## Scenarios

| # | Area | Role | Result |
|---|---|---|---|
| 1 | Command Center → Schools → `/management/schools`; 13 §18 tiles in order, period/now note | partner | Pass |
| 2 | School table: tier / active / valid until / renewal due meta; "No students"; "Not entered"; untagged line; All schools total | partner | Pass |
| 3 | Values editor: `-3` refused in the browser ("Enter an amount of 0 or more", no request); `4,50,000` / `500000.5` saved; row shows ₹4,50,000.00 / ₹5,00,000.50; "Saved." status | partner | Pass |
| 4 | Refresh keeps the saved values | partner | Pass |
| 5 | Period end before start → "The period must start on or before its end"; > 366 days → "The period can be at most 366 days"; garbage `from` → this month | partner | Pass |
| 6 | Ledger new entry: "School (optional)" hidden for expenses, shown for School projects income with every school listed | partner | Pass |
| 7 | Tablet 820 px / phone 375 px: no sideways page scroll; table scrolls in its own box | partner | Pass |
| 8 | Finance pillar "School revenue & contracts" → `#school-money`; money columns present; no operational "Schools" link | accountant | Pass (see QA22-01) |
| 9 | Super admin sidebar "Management school figures"; revenue tile "Finance only"; no ₹, no editor; `PATCH` → 403 "Finance access required" | super_admin | Pass |
| 10 | Wrong role: `GET`/`PATCH` → 403 "Management access required" | overseas_admin | Pass |
| 11 | Signed out: `GET` → 401 | — | Pass |
| 12 | Console errors, page errors, 5xx responses across all of the above | all | None |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA22-01 | Medium | accountant, partner | `/management/schools` (1366 px) | Accountant: Command Center → "School revenue & contracts" | The money the link names (revenue, contract value, renewal value) and "Edit values" are visible on arrival | They are the last four columns, beyond the table's right edge; the six count columns and completion come first, so the table must be scrolled sideways to see or edit any money, and an opened editor is clipped at the edge (screenshot `accountant.png`) | Fixed: with money visible, Revenue / Contract value / Renewal value / Values come straight after School |
| QA22-02 | Low (test only) | overseas_admin | e2e spec | The draft e2e signed the overseas admin in at `/admin/login`, which does not finish for that account | — | Timeout in the scripted pass | Fixed in `mgmt-022-schools.spec.ts`: signs in at `/overseas/login`, as the other specs do. The 403 itself was confirmed through the API |

No other defect found. Not in scope and not changed: the shared database's test schools crowd the table (demo data only).
