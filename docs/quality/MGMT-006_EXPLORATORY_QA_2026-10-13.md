# mgmt-006 — Abroad Education revenue dashboard — exploratory browser QA (2026-10-13)

- **Build:** `feature/mgmt-006`, Docker Compose project `mgmt006` (web `localhost:13006`, api `127.0.0.1:18006`), seeded demo data plus a
  QA fixture made only in the stack DB and not committed. The fixture puts these in this IST month: an agency-linked application-fee
  payment (₹18,000, "QA006 Northern Pathways", intake "Jan 2027"), a direct-application service fee (₹12,000, intake "Sep 2026"), and
  a ₹50,000 university commission receipt for "QA006 Maple University" (country "QA006 Canada").
- **Tools:** Playwright Chromium scripts: desktop 1366×900, tablet 820×1180, mobile 375×812. Console, page-error and failed-response
  listeners on every page. Full-page screenshots, kept outside the repo.

## Scenarios

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Command Center → "Abroad Education revenue" link → page | partner | Pass. The figures reconcile: kinds 37,000 + 18,000 + 50,000 = 1,05,000; country 80,000 + 25,000 unattributed; agency 18,000 + 12,000 Direct + 75,000 unattributed. Agent-generated ₹18,000 |
| 2 | Same page | accountant | Pass. "University commission is shown to partners only; these figures leave it out." No commission row. Revenue ₹55,000; the QA006 country is ₹30,000 (the receipt left out). The JSON holds no "University commission" text |
| 3 | `super_admin` opens the URL | super_admin | Pass. "Access unavailable" / "Finance access required" |
| 4 | Signed out | — | Pass. Redirect to `/admin/login?next=%2Fmanagement%2Frevenue%2Fabroad` |
| 5 | Month change by keyboard (Enter), double-click Show, reload, back | partner | Pass. The URL keeps `month=2025-04`; the double submit is an idempotent GET |
| 6 | `?month=2099-01` / `1999-12` | partner | Pass. The API's 422 message ("Choose this month or an earlier one" / "Choose January 2000 or a later month"), no tables |
| 7 | `?month=2026-13`, `abc`, `2026-4` | partner | Pass. Dropped by the page; the current month is shown |
| 8 | `?month=2000-01` (empty) | partner | Pass. Status "No Abroad Education revenue or expenses are recorded in the financial year 1999-00 up to January 2000 yet."; "No Abroad expenses …" row |
| 9 | Ledger link | partner | Pass. `/management/ledger?month=2026-10&vertical=abroad&include=auto` opens the filtered ledger |
| 10 | API stopped, page loaded | partner | Shared `accessUnavailable` card "fetch failed" (`/management/me` fails first). This is the existing shared behaviour, as on mgmt-010, and not this item's. A 500 after `/me` shows "The Abroad revenue dashboard is unavailable right now. Please try again." (vitest) |
| 11 | Console errors, failed requests, broken images, page overflow | all | None at all three widths |
| 12 | Scroll regions | — | Every table sits in a labelled, keyboard-focusable (`tabIndex=0`) region, with its title outside the region |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Low | partner, accountant / mobile 375px | Open the page on a phone | The headline figures and the three-column expense table are readable without scrolling sideways | The summary and expense tables had `minWidth: 420`: the Annual column sat off-screen and the empty-expenses message was clipped (region scroll overflow 47px) | **Fixed** (`921ff852`). The summary is now three `kpi-grid` tiles (the ledger's totals idiom, annual value plus "This month"), and the expense table has no minimum width (overflow 0). Vitest asserts both; the Playwright spec reads the tiles |

The four-column breakdown tables still scroll sideways inside their focusable regions on a phone. This is the same idiom as mgmt-010's
heads table, and the share column needs the width.

## Automated evidence

- Backend `tests/test_mgmt_006_abroad_revenue.py`: 22 passed, 3 consecutive runs.
- Web vitest: `managementAbroadRevenue.test.ts` and `ManagementAbroadRevenue.test.tsx` (20). With the management suites, 138 passed.
- Playwright `mgmt-006-abroad-revenue.spec.ts`: 3 passed against the stack (plus `mgmt-010-expenses.spec.ts`, 2 passed).
