# bdm-022 — Browser QA (2026-10-07)

Stack: Docker Compose project `bdm022` (web `127.0.0.1:13022`, api `127.0.0.1:18022`), seeded (`python -m app.seed`). Driver: scripted
Playwright Chromium session (exploratory scenarios, screenshots, console and failed-request capture), plus the committed e2e
`tests/e2e/bdm-022-agent-performance.spec.ts`. World per run: an Agent BDM, a College BDM, their manager; a linked Agent organization
(agency approved, 3 students, 6 applications: 2 enquiry, 2 offer, 2 withdrawn) and an unlinked one.

## First pass (no code changes)

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path, BDM, 1280 px | Chain Students 3 · Applications 4 · Offers 2 · Visa 0 · Enrolled 0 · Revenue "Not tracked yet"; definitions shown |
| 2 | Keyboard disclosure (Enter / Space) | `aria-expanded` toggles, focus stays on the button, stage table shown/hidden |
| 3 | No student data (AC4) | Student names and the agency owner never on the page |
| 4 | Tablet 768 / mobile 375 / 320 | No horizontal overflow; panel readable |
| 5 | Refresh | Panel re-renders collapsed; no errors |
| 6 | Back navigation | Panel visible again |
| 7 | Unlinked organization | "Not onboarded yet. Figures appear once Overseas Admin links the agent organization." |
| 8 | Other-module BDM (College) | Page "Organization not found", API 404 |
| 9 | College organization | No panel; API 404 |
| 10 | Wrong role / anonymous | Overseas Admin API 403; anonymous 401 |
| 11 | Suspended agency | Figures shown with the text flag "Suspended — … not changing." |
| 12 | Manager page / super_admin | Same panel on `/bdm/manager/organizations/[id]` |
| 13 | Console errors / failed requests | None |
| 14 | Server error | The first read is server-side, so it can't be forced from the browser; the "Unable to load … Try again" state is covered by vitest |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA22-01 | Low | bdm | org detail | Agency with 3 students, 4 applications | Bars proportional | Bars sized against Students: Applications capped at 100 % | **Fixed** — sized against the largest figure; vitest `QA22-01`; re-verified (Students bar 75 %) |
| QA22-02 | Low | bdm | org detail | Agency with no visa case | Plain wording | "0 approved of 0 visa applications" | **Fixed** — "No visa applications yet."; vitest `QA22-02`; re-verified |
| QA22-03 | Low | bdm | org detail | Expand applications by stage | Rows reconcile with the Applications figure | Withdrawn listed with open stages; rows total 6 vs 4 | **Fixed** — note "Withdrawn applications are not counted in Applications."; vitest `QA22-03`; re-verified |

Second pass after the fixes (rebuilt `web`): all scenarios above unchanged and passing; 0 console errors, 0 failed requests.
