# rec-036 exploratory QA — 2026-10-11

Stack: `docker compose -p rec036` (web `localhost:13336`, api `127.0.0.1:18336`), seeded demo accounts. Headless Chromium (Playwright)
at 1366×900, 768×1024, 375×800 and 320×700. Scripts kept outside the repo (session scratchpad); the regression parts are in
`apps/web/tests/e2e/rec-036-it-integration.spec.ts` and the vitest suites.

## First pass (no code changes)

| Area | Result |
|---|---|
| IT admin → Programs → Skills → add (keyboard: type, ↓, Enter) → Save | Pass; one `PUT` on a double click; "Skills saved." / "N candidates were updated." |
| Refresh after save | Pass; tags persist |
| Toggle Skills twice | Pass; closes |
| Recruiter → candidate (opted-in seeded student) → Skills | Pass; the course skill shows Course completed, Verified by the IT admin who issued the certificate |
| Journey at three widths | Pass; five stages with dates; no horizontal page overflow |
| Roles | Pass; recruiter/trainer `PUT` 403, recruiter options 403, anonymous 401, hr_team journey 200, it_admin journey 403; the recruiter's Programs page has no Skills buttons |
| Console / failed calls | None |

### Issues

| ID | Severity | Role / page | Steps | Expected | Actual |
|---|---|---|---|---|---|
| QA36-01 | Medium (a11y/UX) | it_admin, `/it/admin/programs` | Click Skills on a program near the top of a 130-row list, then Close | The editor opens by its row; Close returns focus to that row | The editor rendered after the whole table (≈14,000 px away); Close left focus on `<body>` |
| QA36-02 | Low | it_admin, `/it/admin/programs` | Open Skills, then type a search that hides that program | The editor closes with its row | The editor stayed open for a program no longer listed |
| QA36-03 | Medium (responsive) | it_admin, `/it/admin/programs` at 375/320 px (and on desktop once the table is scrolled) | Open Skills on a row (the table scrolls sideways inside its card) | The editor sits in the visible part | The editor scrolled with the table: heading and Save at x ≈ −257 px (found while re-testing the QA36-01 fix) |

## Fixes (Phase 6, TDD)

- QA36-01/02: the editor is an expansion row right under its program (`aria-expanded` on the button); Close focuses the row's Skills button;
  a search that hides the open program closes it. `tests/components/AdminProgramManagementPanel.test.tsx` (RED → GREEN).
- QA36-03: the table wrap is an inline-size container; the editor is `position: sticky; left: 0` and `min(40rem, 100cqw − 32px)` wide.
  e2e assertion at 375 px (RED on the old build: heading right edge 648 > 375 → GREEN).

## Re-test

All three widths plus 320 px: editor inside the visible table (desktop 323–754 within 301–1335; 320 px 37–251 within 15–305), 65 px under
its button, focus returns on Close, closed by a hiding search; first-pass checks repeated with no console errors or 5xx.

Neighbouring e2e: rec-010 and rec-011 pass; `adm-001` "Super Admin create user" fails on its role list (expects no `placement manager` /
`partnership head`), a stale pre-existing assertion from earlier items, outside rec-036 (the Create User form is untouched).
