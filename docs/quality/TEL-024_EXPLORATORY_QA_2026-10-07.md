# tel-024 — Exploratory QA (2026-10-07)

**Stack:** isolated compose project `tel024` (web :3024, API :8024), built from `feature/tel-024`; demo seed plus a QA fixture: manager
"Meera Manager" with two telecallers, counselor "Asha Counselor", campaign "Instagram Cyber Security", a CSV-injection campaign
`=HYPERLINK("http://x")`, and 12 leads at stages from Assigned to Converted (one lost after Qualified, one linked straight from Contacted).
**Tools:** Playwright (Chromium) in the `web-test` container: the repo spec `tests/e2e/tel-024-reports.spec.ts` and a throw-away
screenshot sweep (console errors, 5xx responses, side scroll and broken images captured per page).

## Scenarios

| # | Role / page | Check | Result |
|---|---|---|---|
| 1 | Manager, all five reports @1366 | tables render, Total row, current report marked | Pass |
| 2 | Manager, Course @820 / Campaign @390 | no side scroll; table stacks into labelled blocks on a phone | Pass |
| 3 | Manager, Campaign funnel | cumulative + monotonic (9 / 7 / 6 / 4 / 1); an "interested" call counts as Qualified (Interested is past Qualified) | Pass |
| 4 | Manager, report links | a filter (campaign) is kept when switching report | Pass |
| 5 | Manager, Telecaller report | lead filters hidden; calls / connected per telecaller | Pass |
| 6 | Manager, `?report=nope` | falls back to Lead Source (the API's 404 is for a direct call) | Pass |
| 7 | Manager, `product_id=abc`, a 2-year range, a reversed range | sentence above the form, typed values kept | Pass (after QA-01/02) |
| 8 | Manager, an empty range | "No leads in this range.", no CSV button | Pass |
| 9 | Manager, Source filter + Apply, Clear filters | narrows to empty state; Clear returns to `?report=campaign` | Pass |
| 10 | Manager, Download CSV | `text/csv`, BOM, labels, Total last; `'=HYPERLINK(...)` neutralised; "Report downloaded." | Pass |
| 11 | Super admin, `/admin/telecaller-reports` and the manager page | own sidebar on the admin page; Team picker offered | Pass |
| 12 | IT admin, `/it/admin/telecaller-reports` | IT leads only; no Team picker; `team=overseas` → empty; manager page → access card | Pass |
| 13 | Overseas admin | own division's (empty) figures | Pass |
| 14 | Telecaller | page → "Telecaller manager role required"; API → 403 | Pass |
| 15 | Signed out | redirected to `/admin/login?next=…` | Pass |
| 16 | All pages | console errors, failed (5xx) calls, broken images | none |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Minor | Manager, any report with a refused input | open `?report=source&product_id=abc` | heading "Lead Source Report" | heading fell back to the tab label "Lead Source" | **Fixed** (heading from the tab: "<label> Report"; unit test) |
| QA-02 | Minor | Manager (one team), refused input | same | no Team picker (nothing to choose) | an empty "All teams" picker appeared because options are unknown on a failed read | **Fixed** (shown only with a real choice, or to keep a team already chosen; unit tests) |

Not tel-024 (recorded, not fixed): the shared `.table` CSS left-aligns `.num` cells and the sticky first column paints its header white
(identical on the AGN-020 agency reports); `tests/lib/dateZoneSweep.test.ts` fails on 27 pre-existing call sites on `main`, none in this diff.
