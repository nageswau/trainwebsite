# mgmt-020 — BDM dashboards — exploratory QA (2026-10-13)

- **Build:** `feature/mgmt-020` on an isolated Docker stack (`-p mgmt020`, web `http://localhost:13020`, api `127.0.0.1:18020`), seeded
  demo accounts. The test database is shared with backend pytest runs, so the counts include test rows.
- **Method:** a scripted Playwright (Chromium) walk acting as an independent tester, plus screenshots at 1366×900, 820×1180 and
  375×812. Console errors, page errors, HTTP ≥ 400 responses and failed requests were captured for every session. Next.js `_rsc`
  prefetches aborted by navigation were filtered out as noise. Browser Use was not available in this session.

## Scenarios

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Command Center → "BDM" entry → `/management/bdm` (Agent tab by default, this IST month) | partner | Pass |
| 2 | Agent / School / College tabs: 9 / 7 / 6 figures, `aria-current` on the shown tab, split into "In the period" / "Right now" | partner | Pass |
| 3 | Internships tile reads "Not tracked", never 0 (BD11) | partner, super_admin | Pass |
| 4 | Period form: submit keeps the type; reload keeps from/to; a tab switch keeps the period; Back restores the previous tab | partner | Pass |
| 5 | "This month" link resets the period, keeping the type | partner | Pass |
| 6 | Invalid: start after end → "The period must start on or before its end"; 367+ days → "The period can be at most 366 days" (no tiles) | partner | Pass |
| 7 | Malformed address (`type=corporate`, `from=2025-02-30`, repeated `type`) → dropped, page shows the defaults | partner | Pass (by design) |
| 8 | Super admin: "Management BDM figures" in their own sidebar opens the page | super_admin | Pass |
| 9 | Accountant (finance tier) → "Access unavailable"; no BDM entry on the Command Center | accountant | Pass |
| 10 | BDM (not management) → "Access unavailable" | bdm (agent) | Pass |
| 11 | Signed out → `/admin/login?next=%2Fmanagement%2Fbdm` | — | Pass |
| 12 | Tablet / phone: no horizontal scroll on any tab | partner | Pass after QA-01 |
| 13 | Console errors, failed network calls, broken images | all | None |
| 14 | Server error (500) → "BDM figures are unavailable right now. Please try again." | partner | Pass (unit test; not forced on the live stack) |
| 15 | Duplicate submission | — | n/a: a GET form, idempotent |

## Issues found and fixed

| ID | Severity | Role / page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|
| QA-01 | Low | partner, `/management/bdm?type=college`, 375 px | Open the College tab on a phone | All three tabs visible, the current one fully in view | "College BDM" (the current tab) cut off at the right edge of the scroll strip | The BDM strip wraps (`.report-tablist.wrap`); e2e asserts the tab is fully in the viewport |
| QA-02 | Low | partner, College tab, 375 px | Look at the Internships tile | "Not tracked" reads as words | "Not tracked" in the 28 px figure size, wrapping onto two lines | `.metric-untracked` (18 px); unit test |
| QA-03 | Low | any, intro line | One active BDM of a type | "1 active Agent BDM." | "1 active Agent BDMs." (found by code inspection) | Singular for one; unit test |

No issue remains open.
