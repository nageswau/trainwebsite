# mgmt-023 — University partnership dashboard: exploratory QA (2026-10-14)

**Build:** `feature/mgmt-023`, Docker Compose stack `mgmt023` (web `http://localhost:13023`, api `127.0.0.1:18023`), seeded demo
accounts, shared test DB (138 active universities, 15 lost / closed at the time). Browser: Playwright Chromium (headless), widths 1366,
820 and 375. Roles: `partner.one@`, `superadmin@`, `accountant@`, `counselor@`, signed out.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Partner opens Command Center → Partnerships → Universities | Page loads (~190 ms); 12 KPI tiles in §19 order, Revenue last; 8-step pipeline; 3 expected windows; next-month table (5 rows = the window's count) |
| 2 | super_admin opens it from "Management university figures" | 11 tiles; no Revenue tile, no "Commission received" text; API response has no `revenue` key |
| 3 | Accountant / counselor open the URL | "Access unavailable" card, no figures |
| 4 | Signed out | Redirect to `/admin/login?next=%2Fmanagement%2Funiversities` |
| 5 | Apply a period, Back, Forward, Reload, "This month" | Address holds the period; inputs follow Back / Forward / Reload; "This month" clears it |
| 6 | Start after end; > 366 days; empty `to` with an early `from` | API wording shown in `.form-error` ("The period must start on or before its end" / "A period can be at most 366 days"); no tiles |
| 7 | Impossible / repeated dates in the address | Dropped; the page shows this month |
| 8 | Double-click Apply | One navigation; no duplicate effect (read-only GET) |
| 9 | Desktop / tablet / phone | No horizontal page scroll at 1366 / 820 / 375; the next-month table scrolls in its own region |
| 10 | Console, failed requests, broken images | None (aborted `_rsc` prefetches filtered) |
| 11 | Totals vs upc-029 | Pipeline, Universities identified, Active, Countries, Applications, Enrollments and Revenue equal `/partnership/global-dashboard` for the same period (pytest `test_totals_equal_the_global_partnership_dashboard`) |

## Issues found and fixed

| ID | Severity | Role | Page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|---|
| QA23-01 | Low | partner | `/management/universities` | Read the Revenue tile | Received and expected on separate, labelled lines | "Commission received · Expected —" on one line | Two caption lines: "Commission received in the period" / "Expected: …" |
| QA23-02 | Low | partner, super_admin | same | Read the pipeline card | The lost / closed note spaced from the last step | Note flush under "Active Partner" | `.universities-lost { margin-top: 12px }` |
| QA23-03 | Low | partner, super_admin | same | Read the expected windows | "Weighted forecast N" (upc-029 wording) | Bare "Weighted N" | Caption reworded |

Each fix: component test updated first (RED), then the change (GREEN), web rebuilt, the browser scenario and the e2e spec re-run.

## Not changed (observed, out of scope)

- Window labels ("Expected Partnerships This Month", "Expected Next Month", "Expected This Quarter") are upc-023's source wording.
- Owner names such as "partnership_manager 4878" are pytest rows in the shared DB.
