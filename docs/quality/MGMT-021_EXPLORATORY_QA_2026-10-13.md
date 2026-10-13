# mgmt-021 — Agent network dashboard: exploratory browser QA (2026-10-13)

## Setup

- **Stack:** Docker Compose project `mgmt021` from `feature/mgmt-021` after merging origin/main (mgmt-025). Web at
  `http://localhost:13021`, API at `127.0.0.1:18021`, demo accounts seeded.
- **Tools:** headless Chromium (Playwright 1.62) scripts in the session scratchpad, plus API calls with a cookie jar.
- **Data:** the shared database also holds rows from the backend test runs (80 approved agencies). So the checks are about the page and
  how its figures reconcile, not about exact counts.

## First pass (no code changed)

| Check | Role | Result |
|---|---|---|
| Happy path: Command Center → Partnerships "Agents" | partner | PASS. 12 tiles in §17 order, the 6-step chain, 80 ranked agencies, an "All agencies" total |
| Money | partner | PASS. Commission ₹1,68,987.00 for 2025-10-14..2026-10-13. Revenue ₹0.00 is correct for that period: the DB's only paid agency payments are dated 2015-04, 2019-04 and 2024-06/07 |
| Revenue reconciles with mgmt-006 | partner (API) | PASS. June 2024 revenue `250000.00` = `GET /management/revenue/abroad?month=2024-06` `agent_generated.month` `250000.00` |
| Invalid inputs | partner | PASS. A reversed period gives "The period must start on or before its end", over 366 days gives "The period can be at most 366 days", and a garbage address falls back to this month with no error |
| Empty period (Jan 2001) | partner | PASS. Period figures are 0; total, active, inactive and staff stay, because they are "right now" by definition (AN1, AN2, AN4) |
| Refresh / back / double submit / `#agencies` anchor | partner | PASS |
| Tablet 820px / phone 375px | partner | PASS. No sideways page scroll; the table scrolls in its own box |
| Console errors, failed requests, 5xx, broken images | all | PASS. None (the `_rsc` prefetch aborts are filtered as noise) |
| Super admin from their own sidebar ("Management agent figures") | super_admin | PASS. No "₹" anywhere, no Commission or Revenue columns, no revenue step, and the API returns `null` money |
| Wrong roles | accountant, overseas_admin, agent | PASS. The accountant gets the Access unavailable card and API 403. overseas_admin and agent get API 403 "Management access required" |
| Signed out | — | PASS. Redirected to `/admin/login?next=%2Fmanagement%2Fagents` |

### Issues

**QA21-01** (Low, partner and super_admin, `/management/agents`)
- **Steps:** open the page at 1366px; look at the Agency-wise table.
- **Expected:** the agency name reads on one or two lines.
- **Actual:** the Agency column is 152px wide (102px on a phone). "Dash agn-177c46e3 · DAS · New" wraps to three lines, so each row is
  92px tall.
- **Evidence:** `desktop-table.png`. No console or network errors.

Exploratory notes that are not defects:
- The table lists every approved agency, including those with no activity in the period (AN1). They sort last (AN10).
- A script check flagged "Revenue" missing from the column headers. That was a false alarm: CSS uppercases the header text, and all 10
  headers are present.

## Fix pass

**QA21-01** is fixed, TDD:
- **RED:** a test in `ManagementAgents.test.tsx` (QA21-01) expects the row header `.agents-agency` with its code and markers in
  `.agents-agency-meta`. It failed first.
- **GREEN:** the code and markers now sit on a small line of their own, and `.agents-agency { min-width: 160px }`.
- **Tried first:** 220px, then 180px. At 1366px those pushed the Revenue column 17px or more past the table box. At 160px every
  column fits.

Re-check after rebuilding the web container:

| Viewport | Result |
|---|---|
| 1366px | First row 67px tall (was 92px), Agency column 162px, table box overflow 0 |
| 375px | No sideways page scroll; the table scrolls inside its box |

- The full exploratory script was re-run with the same results as the first pass.
- `mgmt-021-agents.spec.ts` passes 3/3 against `localhost:13021`.
- No issues are open.
