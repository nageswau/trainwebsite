# rec-006 Skills Master — exploratory QA (2026-10-08)

**Environment:**
- Stack: isolated compose project `rec006` (web :3106, API :8106), seeded with `python -m app.seed`.
- Browser: headless Chromium (Playwright in the `web-test` container). Viewports: 1366×900, 820×1180 and 375×812.
- Accounts: `placement.manager@edusphere.local`, `placement@edusphere.local`, `superadmin@`, `hr@` and `itadmin@`.
- Data caveat: the shared dev/test database also holds pytest-created "Cat …" and "Sk …" rows.

## Scenarios checked (pass 1, no code changes)

| # | Area | Result |
|---|---|---|
| 1 | Happy path: add category, create skill (with tag), add alias, add related skill, rename, deactivate/reactivate | Pass |
| 2 | Invalid input: empty (native validation), whitespace-only → "Name is required", own-name alias → 422 sentence | Pass |
| 3 | Conflicts: duplicate skill in any case → 409; name equal to an alias → 409; duplicate category → 409; alias equal to a skill name → 409 | Pass |
| 4 | Double submit: double-clicking Create skill → exactly one row | Pass |
| 5 | Empty / no-match / past-the-end / load-error states | Pass (unit tests cover the 500 path) |
| 6 | URL state: search → `?q=`; refresh keeps it; Back/Forward | Pass |
| 7 | Keyboard: Esc cancels a category rename and returns focus; detail heading focused on open; focus returns to Manage on Close | Pass |
| 8 | Roles: a recruiter sees a read-only page (no Manage/Add), only active rows, and the manager page gives "Placement manager role required"; `hr_team` and `it_admin` see "Recruiter role required"; `super_admin` is redirected to the editable page | Pass |
| 9 | Signed out: `/recruiter/skills` → `/it/login`, `/recruiter/manager/skills` → `/admin/login` | Pass |
| 10 | Layout: no horizontal scroll on desktop, tablet or mobile (list and detail); chips wrap | Pass |
| 11 | Console and network: no page errors and no 5xx. The 409/422 console lines come from the deliberate invalid inputs; one aborted list request is the intended AbortController cancel | Pass |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | — | Manager / skills | Search, then immediately read the URL | — | QA-script timing artifact (the URL was read before the client-side push completed) | Withdrawn; re-verified correct |
| QA-02 | Minor | Manager + recruiter / both pages | Have more than 100 categories, then open the category filter | Every category is listed | Only the first 100 were loaded (single `limit=100` read) | **Fixed** (`allCategories` pages through; unit test + browser re-check with 106 categories) |
| QA-05 | Minor | Any / `?category=zzz` | Open a hand-edited URL | The list loads unfiltered | 422 → "Unable to load skills" with a Retry that cannot succeed | **Fixed** (non-id ignored; unit test + browser re-check) |

Automated: `tests/e2e/rec-006-skills-master.spec.ts` (2 passed) and the neighbour `rec-001-recruiter-roles.spec.ts` (4 passed).
