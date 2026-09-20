# ENH-004 — independent exploratory browser QA (2026-09-20)

Feature: student promotion at academic-year rollover (`ENH-004`, `DEC-SCOPE-020`).
Tool: Browser Use (CDP) against a separate Chrome, driving the running web app; plus targeted API calls from the page.

## Method and environment (read this before trusting the results)

- **Stack:** an isolated compose project (`enh004-e2e`: web `:3100`, API `:8100`, its own Postgres/Redis volumes, migration `0033`,
  freshly seeded with `python -m app.seed`). It was **not** the developer's `:3000` stack, which does not contain ENH-004 (the
  promotion page is a 404 there and the route is 405). Read-only checks on `:3000` confirmed the feature is absent and that the
  student-page crash below pre-exists.
- **Data written on the isolated stack only:** `QA-*` academic years, `QA …` students, one throwaway school; the API container was
  stopped and started once for the outage check. None of it touches a real database.
- **Roles used:** School Coordinator, Parent, Teacher, Principal, Overseas Admin, signed-out.
- **Not covered:** browsers other than Chrome, screen readers, real touch devices.
- **Evidence you can re-run:** `apps/web/tests/e2e/enh-004-student-promotion.spec.ts`. **Not committed:** the exploratory scripts,
  raw console/network capture and ~50 screenshots (they live in a local scratch folder). This file is the summary of record.

## Coverage (20 requested areas)

Happy path, invalid input (HTML label escaped, 61-char and control-character labels give a readable 422), empty states (no
match / no students / no active year), server errors (500 JSON and text, 502, 403, 401, 409, dropped connection, malformed 200),
loading, cancel/back, refresh, duplicate submission (one POST on a double-click; a stale confirm after a concurrent promotion
reports "skipped" and promotes once), unauthorized and wrong-role users, desktop/tablet/mobile (1440, 1280, 1024, 768, 390, 320: no
overflow), navigation and keyboard, success and error messages, broken images (none), console and network errors (only the
deliberate ones), redirects (none unexpected).

## Findings

| ID | Severity | Role | Finding | Status |
|---|---|---|---|---|
| QA-001 | High (pre-existing) | Coordinator, Parent | Student pages crashed for any student whose timeline had `test_prep`, `foreign_language` or `global_education` events (no entry in the frontend category map); hid the new Grade history card | Fixed `70f2cf6`, verified in browser |
| QA-002 | Medium | Parent, Teacher, Principal | Promotion page rendered for roles that can never promote (submit failed with 403) | Fixed `70f2cf6`, verified |
| QA-003 | Medium | Coordinator | After a failed submit the error banner could be above the viewport and took no focus | Fixed `70f2cf6`, verified |
| QA-004 | Low | Coordinator | A `200` whose body is not a report (empty object, proxy page) replaced the page with a crash screen | Fixed `82b9046`, verified |
| QA-005 | Low | Coordinator | Failed rows showed the API's field names (`grade_or_class …`); no pre-submit hint for unparseable labels | Wording fixed `82b9046`; a pre-submit hint would need a dry-run endpoint or duplicated parsing rules, not built |
| QA-006 | Low | Coordinator | List stayed editable while a request was in flight | Fixed `82b9046`, verified |
| QA-007 | Low | Coordinator | A 401 on submit left no way back to sign in | Fixed `82b9046`, verified |
| QA-008 | Low (pre-existing, app-wide) | Any school role | Guarded pages show the raw text "fetch failed" when the API is down | Open, not ENH-004 |
| QA-009 | Low (app-wide) | Coordinator | Active nav link has no `aria-current`; pages have no `h1`; one generic `<title>` (not compared with other pages) | Open, not ENH-004 |

## Re-run and regression notes

- After the fixes the ENH-004 e2e passed repeatedly. Related specs (`enh-002`, `sch-001`, `sch-007`, `sch-008`, `sch-009`,
  `sch-roster-parent-invite`) each pass **when run alone**. Run back to back, an intermittent `POST /api/v1/auth/logout` from
  Playwright's request context hung past the test timeout, on a different spec each run. The API log showed normal 200s, logout
  takes ~10 ms when called directly, and a keep-alive race was tested and not reproduced. **Cause unknown**; not shown to be caused
  or excluded by ENH-004. A full Playwright and backend regression has not been run on this branch.
- The e2e spec initially failed once because exploratory `QA-*` years outranked its own year; that was contamination from the QA
  runs, and the spec now closes its own year and asserts the active years are restored.
