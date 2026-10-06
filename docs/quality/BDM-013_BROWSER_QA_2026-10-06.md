# bdm-013 — Browser QA: BDM calendar (2026-10-06)

**Build under test:** `feature/bdm-013-calendar` @ `db50ef8c`, compose project `bdm013` (web `localhost:13013`, API `localhost:18013`,
DB at `0078_enquiry_lead_record`, seeded). The web container was rebuilt after each fix and every scenario re-run.
**Tools:** Browser Use is not installed on this machine (as for bdm-007 and bdm-008). The pass used throwaway Playwright scripts in the
`web-test` container: an isolated headless Chromium that records console errors, page errors and 4xx/5xx responses, plus screenshots.
The scripts were kept outside the repository. **Accounts:** throwaway users created through the admin API: a College BDM, a School BDM
on another team, two BDM managers, and super_admin.

## Coverage (20 requested areas)

| # | Area | Result |
|---|---|---|
| 1 | Happy path | Week view reproduces §5: "Hyderabad – Agent Meetings", "Student Seminars" (23:30 IST appointment on its IST day), "Follow-ups", "Travel to Vijayawada", "Vijayawada"; next week shows "Vijayawada", "Return travel" (trip across the boundary). Day view: one day, `aria-current` on Day |
| 2 | Invalid inputs | `view=month`, `date=2026-02-30`, `date=garbage`, `date=2026-13-01`, repeated `view` → today's week / day, 200, no error. API: range > 31 days → 422; a BDM naming a BDM → 422 |
| 3 | Empty states | "Nothing planned this week." / "… this day."; empty days read "Nothing planned" |
| 4 | Server errors | Calendar read fails → inline `role=alert` "Unable to load the calendar." + "Try again" (unit test). API stopped → the shared `accessUnavailable` card ("fetch failed / Return to login"); this is pre-existing **QA4-09** (deferred, every BDM page), not bdm-013 |
| 5 | Loading | `loading.tsx` skeleton with the BDM / manager sidebar (seen in screenshots before streaming completes) |
| 6 | Cancel / back | Back after Next week returns to the previous week with its items |
| 7 | Refresh | Reload keeps view, date and items |
| 8 | Duplicate submission | Not applicable (read-only; no form) |
| 9 | Unauthorized | Signed out → `/bdm/sign-in?next=…` and `/admin/login?next=…` |
| 10 | Incorrect role | BDM on `/bdm/manager/calendar` → "This page is for BDM managers."; manager on `/bdm/calendar` → "BDM role required" |
| 11–13 | Desktop / tablet / mobile | No horizontal scroll at 1366, 768, 375, 320 px (week, day, manager), with long organization, place and task names |
| 14 | Navigation | Prev / Today / Next / Day / Week links; manager links keep `bdm=`; item links open appointment, trip, organization pages (BDM and manager versions all 200) |
| 15 | Success messages | Not applicable (read-only); the manager's empty state "Choose a BDM to see their calendar." |
| 16 | Error messages | "This BDM is not on your team." for another team's BDM, a malformed id and a manager's own id |
| 17 | Console errors | 0 |
| 18 | Broken images | 0 |
| 19 | Failed network calls | 0 unexpected 4xx/5xx (deliberate API 422 probes excluded) |
| 20 | Unexpected redirects | None |
| AC5 | Keyboard | Tab order: Day, Week, Previous week, Today, Next week, then items in reading order; every focused element has a visible ring; Enter opens the item |

## Issues (fixed test-first, re-checked in the browser)

| ID | Severity | Role | Page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|---|
| QA13-01 | Low | BDM, manager | `/bdm/calendar`, `/bdm/manager/calendar` | Open a week with items | Item titles look clickable | Links rendered as plain text (screenshot `week-1366`) | Shared `LINK_STYLE` (blue, underlined) on every item link; test `styles every item link as a link (QA13-01)` |
| QA13-02 | Low (a11y) | both | both | Read the heading outline | Days nest under the range title | Day headings were `h3`, the same level as the range title | Day headings are `h4`; component test + e2e select `section h4` |

**Script artefacts (not product defects):** the first-pass script read the DOM once, straight after client navigations. That reported
Q7-back, Q15-manager-choose, Q14-manager-nav-keeps-bdm and AC5 as failures. Waiting assertions (`qa-recheck`, `qa-keyboard`) pass
all four on the same build.

## Final run on `db50ef8c`

First pass 44 PASS (plus the 4 artefacts above), re-check 3/3, keyboard 3/3, layout 7/7. Playwright `--workers=1`:
`bdm-013-calendar`, `bdm-008-follow-ups`, `bdm-010-travel` (5): **7 passed**.
