# AGN-014 — Browser QA (first pass, 2026-10-02)

**Build:** `feature/agn-014-commission-master-only` @ `72854ff` (all AGN-014 commits through the API/frontend/security review
fixes; the stack was built from this commit). **Stack:** isolated compose project `agn014` (web http://localhost:3014, API 8014), `python -m app.seed` applied.
**Browser:** isolated headless Chrome (own profile, CDP port 9314) driven by browser-use; trusted CDP input. **No code was changed
during this pass.** Data was created through the real API only: Master `QAO-M001` with commissions paid INR 20,000, paid USD 500,
claimed INR 7,500; one staff member with Reports on; a second approved agency with no commissions. Console, uncaught exceptions and
HTTP ≥ 400 were captured from CDP events for every run. Screenshots: session scratchpad (`qa-*.png`).

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Master: Revenue "INR 20,000 · USD 500"; Reports panel totals and four breakdowns correct per currency; CSV `agency-commissions-all-to-all.csv` with 3 correct rows ("+U" neutralised to `'+U`). Playwright `agn-014` 1/1 and neighbours 10/10. |
| 2 | Invalid inputs | PASS with QA14-05 — To before From: inline error, focus on To, `aria-invalid`, described; cleared on edit. `9999-12-31`: server 422 message shown (see QA14-05). |
| 3 | Empty states | PASS — unfiltered "Your agency has no commissions yet."; filtered "No commissions in this period."; Revenue "INR 0". QA14-10 (CSV still offered). |
| 4 | Server errors | PASS with QA14-08 — injected 500 → "Something went wrong on our side. Please try again." + Try again → recovers. |
| 5 | Loading states | PASS — 2.5 s latency: "Updating commission report…", previous content kept, `aria-busy="true"`, Apply `aria-disabled`. |
| 6 | Cancel / back | PASS — Back from Dashboard returns to Reports and reloads the report (no cancel control exists in the panel). |
| 7 | Refresh | PASS with QA14-06 — page reloads cleanly; the filter resets to all-time. |
| 8 | Duplicate submission | PASS — 3 Apply clicks during loading → 1 request; Download CSV double-click → 1 request, 1 file. |
| 9 | Unauthorized user | PASS — signed out: `/overseas/agent/reports` → `/overseas/login?next=…`; API 401. Expired mid-page → message (QA14-08). |
| 10 | Incorrect role | PASS — staff (Reports on): no Commissions link, no Revenue, no panel, no "commission" text; API JSON/CSV 403 even with a bad date; typed `/overseas/agent/commissions` → "Access unavailable — Only an agency Master can open this page". Overseas student and Overseas Admin: agent page "Access unavailable", API 403; the admin's own RPT-002 report unchanged. |
| 11 | Desktop 1440 | PASS with QA14-01, QA14-02, QA14-03, QA14-04 — panel spans the grid (1095/1095 px), no page overflow. |
| 12 | Tablet 820 | PASS — no page overflow; tables fit; inputs 160×51, buttons 49 px. |
| 13 | Mobile 390 | PASS with QA14-02, QA14-09 — no page overflow; tables scroll inside their wrappers. |
| 14 | Navigation | PASS — sidebar Reports link; tab order From (3 segments) → To (3) → Apply; Enter in a date field submits. |
| 15 | Success messages | PASS — "Report downloaded." (status), focus stays on Download CSV. |
| 16 | Error messages | PASS with QA14-07, QA14-08 — 401/403/422/500/offline each shown as an alert. |
| 17 | Broken images | PASS — none on dashboard or Reports. |
| 18 | Console errors | PASS — none from the app in normal use. Offline produces Next.js "Failed to fetch RSC payload" prefetch errors for sidebar links (framework behaviour, not AGN-014). Browser "Failed to load resource" lines appear only for deliberate 4xx/5xx probes. |
| 19 | Failed network calls | PASS — offline: `net::ERR_INTERNET_DISCONNECTED` handled with an alert + Try again; recovery works. |
| 20 | Unexpected redirects | PASS — none; signed-out redirect carries `next=` back to Reports. |

## Issues

| ID | Severity | Role | Page | Reproduction | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA14-01 | Low | Master | `/overseas/agent/dashboard` (1440 px) | Agency with paid INR and USD commissions; open the dashboard at 1440 px. | Revenue fits its card or wraps between currencies. | "INR 20,000 ·" / "USD 500" — wraps after the separator; the card (262×154) is taller than its row neighbours (262×111). Fits at 820/390. | `qa-dashboard-1440.png`; no console errors. |
| QA14-02 | Medium | Master | `/overseas/agent/reports` (all widths, worst on mobile) | Open Reports with any commissions. | A compact report: four small breakdown tables, the CSV action near the filters. | Each 2–3-row table carries the full DataTable toolbar (search, filter by, filter value, rows per page, pagination); at 390 px each toolbar fills ~a screen before its data; Download CSV sits after all four tables (~4 screens down). | `qa-reports-1440.png`, `qa-r5-reports-390.png`. |
| QA14-03 | Low | Master | `/overseas/agent/reports` | Inspect the four breakdown `<table>`s with assistive tech. | Each table has an accessible name (e.g. "Commissions by status"). | `aria-label` is null on all four tables (the `label` passed to DataTable does not name the table); only the visible `<h4>` above identifies them. | DOM: `table.getAttribute('aria-label') === null` ×4. |
| QA14-04 | Medium | Master | `/overseas/agent/reports` | Agency with paid INR 20,000 and USD 500; open Reports. | No mixed-currency total next to the per-currency panel. | The existing (pre-AGN-014) row "Paid commission 20500" adds INR and USD, directly above the panel's "INR 27,500 … · USD 500" — two contradictory figures on one page. | `qa-reports-1440.png`, `qa-r3-expired.png`. Known deferred minor, now visibly user-facing. |
| QA14-05 | Low | Master | `/overseas/agent/reports` | Leave From empty, set To = 31-12-9999 (the date picker allows it), Apply. | The field error, figures kept, no retry of an input error. | Alert "date_to must be before 9999-12-31" (raw parameter name), the figures disappear, and **Try again** is offered — it can only repeat the same 422. | `http 422 …/report?date_to=9999-12-31`; `qa-r2-9999.png`. |
| QA14-06 | Low | Master | `/overseas/agent/reports` | Apply 02-10-2026 → 02-10-2026; press browser Refresh (or go to Dashboard and Back). | The applied range survives (e.g. kept in the URL). | Inputs empty, all-time report shown. | URL stays `/overseas/agent/reports` (no query). |
| QA14-07 | Low | Master | `/overseas/agent/reports` | Go offline (DevTools), Apply. | A connection message (the repo has `NOT_COMPLETED`: "The request did not complete. Check your connection…"). | "Something went wrong on our side. Please try again." — blames the server for a client-side outage. | `net::ERR_INTERNET_DISCONNECTED` on `…/report?date_from=2026-01-01`; `qa-r3-offline` (capture skipped). |
| QA14-08 | Medium | Master | `/overseas/agent/reports` | Open Reports, let the session end (cookies cleared), Apply. | "Your session has expired" with a way to sign in (link with `next=`), no retry of a 401. | Message shown but no sign-in link or redirect; **Try again** only repeats the 401. AGN-006 fixed the same pattern (QA6-02). | `http 401 …/report`; `qa-r3-expired.png`. |
| QA14-09 | Low | Master | `/overseas/agent/reports` (390 px) | Open Reports on a phone-width screen. | The key figure (Amount) visible without sideways scrolling. | Amount and Currency columns are off-screen in each table; reachable only by scrolling the table horizontally. | `qa-r5-reports-390.png`; 4 × `.table-wrap` scrolls. |
| QA14-10 | Low (observation) | Master | `/overseas/agent/reports` | Agency with no commissions; Download CSV. | Either no CSV action, or a clear "nothing to export". | A header-only CSV downloads with "Report downloaded." (matches spec §5.4; may surprise a user). | file content = header row only. |

**Not reproduced / not AGN-014:** Next.js RSC prefetch console errors while offline (framework); "Students 0" on the QA agency is
because the QA applications were created by students naming the agent, not via agency student links (data shape, not a defect).

**Verdict:** AGN-014's acceptance criteria hold in the browser (Revenue, report, CSV, staff 403s, roles). Three Medium UX issues
(QA14-02, QA14-04, QA14-08) and seven Low ones are open. Nothing was fixed in this pass.

## Fix pass (2026-10-02, owner: "fix the issues")

Each fix test-first (RED observed, then GREEN); the stack rebuilt from the fix commits and every issue re-checked in the same
isolated browser.

| ID | Fix | Test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA14-01 | No-break space after "·" in the per-currency value (`services/portal.py` `_paid_per_currency`). | `test_revenue_is_per_currency` (expectation changed deliberately) | Wraps "INR 20,000" / "· USD 500" — between currencies. The card stays one line taller than its neighbours with two currencies (natural, accepted). |
| QA14-02 | The four breakdowns are plain compact tables (no DataTable toolbar); Download CSV moved under the totals, before the tables. | `…compact, named tables…` | No search/filter/rows controls in the panel; CSV precedes the first table. |
| QA14-03 | Each table is `aria-labelledby` its heading. | same | Names: By status / By university / By country / By intake. |
| QA14-04 | "Paid commission" report row uses the same per-currency formatter as Revenue. | `test_master_reports_paid_commission_row_is_per_currency` | "Paid commission — INR 20,000 · USD 500". |
| QA14-05 | A 422 is a field error (`'To' must be before 9999-12-31`), attached to and focusing the field; figures kept; no Try again. | `…server rejects the range…` | As expected; To `aria-invalid`, focused. |
| QA14-06 | Applied range written to the address (`?from=&to=`, `history.replaceState`), read back on load (YYYY-MM-DD only). | `…restores the range from the address…`, `…ignores a malformed range…` | Survives refresh and Back. |
| QA14-07 | Network failure: "The report could not load. Check your connection and try again." + Try again. | `shows a network failure as an alert` (text changed deliberately) | As expected; recovers online. 500 still "…on our side" + Try again. |
| QA14-08 | 401: "Your session has expired." + **Sign in again** link to `/overseas/login?next=<this page and range>`; no Try again. | `…sign-in link back to this page…`; 401 alert text changed deliberately | Link → sign in → back on `/overseas/agent/reports?from=2026-02-01` with the report. |
| QA14-09 | Three columns per table (country inside the university cell, header "Count"); `.commission-report .table { min-width: 0 }` (scoped — other tables keep 650 px); tighter cell padding ≤ 640 px. | header/row assertions in the compact-tables test | No table scrolls at 320, 390, 820, 1440 px; page never overflows; the portal table keeps `min-width: 650px`. |
| QA14-10 | Download CSV only when the report has commissions. | `…offers no CSV when there is nothing to export` | — (unit-verified). |

**Evidence after the fixes:** web `npx vitest run` 144 files / **1508 passed**; `tsc` 0; eslint 0 on changed files; backend
`test_agn_014` + `test_agn_003_permissions` + `test_agn_004_staff_guards` + `test_agn_002_staff_access` + `test_agn_002_qa_messages`
**89 passed**, ruff clean; Playwright (rebuilt stack) `agn-014`, `agt-003`, `agt-004`, `agn-002`, `agn-003`, `rpt-002`,
`enh-015-reports-downloads` **11 passed**; browser console clean apart from the deliberately provoked 401/500.
