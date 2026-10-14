# mgmt-031 — Partner home dashboard: exploratory QA (2026-10-14)

- **Build:** `feature/mgmt-031`. Isolated stack `mgmt031` (web `localhost:13131`, api `127.0.0.1:18131`), seeded demo accounts.
  The shared test DB also holds rows from the pytest runs (22 meetings today, 8 pending decisions, 21 discussions).
- **Method:** Playwright (Chromium). Partner, super_admin and accountant, each at 1440×900, 820×1180, 375×812 and 320×700. The
  script captured console errors, page errors, every HTTP ≥ 400, broken images and elements clipped past the viewport. It followed
  every link in the home (37 for the partner, 36 for super_admin), checked refresh, Back and keyboard Tab focus, and the
  signed-out page and API. Full-page screenshots were reviewed by eye. First pass with no code changes.

## First pass — results

| Check | Partner | super_admin | Accountant |
|---|---|---|---|
| Lands on | `/management` | `/admin` (own dashboard; `/management` by nav) | `/management` |
| Snapshot tiles | 7 (Revenue … Enrollments) | 3 (Students, Applications, Enrollments) | none (no home, HM1) |
| Panels | 9 | 8 (no Financial position) | 0 — pillars only |
| "₹" anywhere in `main` | yes | **no** (AC) | — |
| Horizontal overflow / clipped elements (4 viewports) | 0 / none | 0 / none | 0 / none |
| Broken images, console errors, HTTP ≥ 400 | none | none | none |
| Every home link opens (no 404, no Access unavailable) | 37/37 | 36/36 | — |
| Refresh / Back from a linked page | panels re-render (9 / 9) | 8 / 8 | — |
| Keyboard: Tab reaches the panel links, focus ring visible | yes | yes | — |
| Signed out | `/management` → `/admin/login?next=%2Fmanagement`; `GET /management/home` → 401 | | |

Server errors and empty states (the first month with no data) are covered by unit tests, because the shared stack cannot be emptied:
a failed home read shows "Today's figures are unavailable right now. Please try again." and the pillars still render. Duplicate
submission and invalid input do not apply, because the home is read-only and takes no parameters.

## Issues found

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA31-01 | Medium | partner, super_admin | `/management` | Sign in on a day with many management meetings (22 in the test DB) | The Today's meetings panel is bounded like the other list panels (first 5 + a count linking to the calendar) | Every meeting is listed; the panel stretches its grid row (≈ 650 px of empty space in Urgent issues and Pending decisions) and pushes the rest of the home down | `partner-desktop.png`, `super_admin-small.png` |
| QA31-02 | Low | partner, super_admin | `/management` → Business growth | Open the home when most factors have no month-on-month change | The panel lists the factors that changed and says how many have no comparison | 8 of 12 lines read "Revenue: —", "Profit: —", …, which is noise without explanation | `partner-desktop.png` |
| QA31-03 | Low | super_admin | `/management` | Sign in as super_admin | The snapshot note speaks only of the figures shown | "Money and applications are for October 2026 to date" although no money is shown | `super_admin-small.png` |

Not a defect: the super admin is greeted "Good afternoon, Global" because the seeded super admin is named "Global Super Admin"
(HM3 takes the first name).

## Fixes (Phase 6) and re-verification

Each fix followed RED → GREEN: the test was changed first and failed for the expected reason, then the fix made it pass.

| ID | Fix | Test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA31-01 | `GET /management/home` returns `meetings{items (the calendar's first 5 of today), total}` (HM7 updated in the spec, DEC-SCOPE-219 and API §12EG). The panel's link reads "All N meetings today" when there are more | `test_todays_meetings_match_the_meetings_page` (6 meetings created; first 5 and total equal the calendar's); component "All 7 meetings today" | Fixed: 5 rows, "All 32 meetings today"; panel rows are even (`partner-desktop.png`, second pass) |
| QA31-02 | Business growth lists only factors with a month-on-month change, and counts the rest ("11 factors have no month-on-month comparison yet.") | component: listed factors = changed ones; the count sentence | Fixed |
| QA31-03 | The snapshot note follows the scope: partners "Money, applications and enrollments are for …; cash is the latest balance entered.", super_admin "Applications and enrollments are for … (India time)." | component: both sentences | Fixed: no money wording for super_admin |

**Second pass (after the fixes, rebuilt stack):** every first-pass check repeated with the same results. No overflow, clipping,
broken images, console errors or HTTP ≥ 400 at the 4 viewports for any of the 3 roles. Every link opens. No "₹" for super_admin.
Playwright `mgmt-031-home`, `mgmt-001-command-center` and `mgmt-030-health`: 9/9 passed. Open issues: none.
