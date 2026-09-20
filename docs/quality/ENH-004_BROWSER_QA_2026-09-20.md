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

## Final verification (2026-09-20, fresh runs on the final build, after the code review)

Every result below was produced by a command run during this verification, not carried over from earlier. Base = `0bfba40`.

| Gate | Result |
|---|---|
| Backend, full suite (`pytest`, throwaway Postgres) | **875 passed, 22 failed.** The 22 are the *identical test IDs* that fail on the base commit (Razorpay/Zoho credentials unset, public-content tests needing a seeded DB); 0 failures in ENH-004's file. |
| Frontend unit (`npm test`) | 17 files, 129 tests, all pass |
| Type check (`npm run typecheck`) | exit 0 |
| Lint (`npm run lint`) | exit 0, 0 errors; 31 warnings, none in an ENH-004 file |
| Production build (`npm run build`) | exit 0, `/school/coordinator/promotion` compiled |
| `ruff check .` / `mypy app` | 33 findings / 154 errors: identical to base |
| `ruff format --check app tests` | 55 files unformatted: identical to base (the gate was already red; this branch adds none after formatting its own test file) |
| `alembic heads` / `alembic check` | single head `0033_student_grade_history`; "No new upgrade operations detected" |
| Playwright, every `sch-*` and `enh-*` spec, one process each | 16 files, 31 tests, all pass |
| Playwright, same specs in one process (`--workers=1`) | 27/27 pass (excluding `sch-004-005-006`, see below) |
| Browser Use (fresh data, isolated stack) | 156 distinct checks; all AC-01..AC-11 pass; the only two FAIL rows are known faulty assertions of the script itself (superseded by corrected checks that pass) |
| Responsive (14 widths, 320..1920px incl. 640x400 and 844x390) | 14/14 pass after two layout fixes below |

Found and fixed during this verification:

- **Test-order bug in ENH-004's own tests:** four log-assertion tests passed alone but failed in the full suite, because ENH-001's in-process migration disables `app.*` loggers. Fixed with an autouse fixture, the convention `test_enh_003_*` already uses; reproduced red (ENH-001 first) then green.
- **Format gate:** ENH-004's new test file was unformatted; formatted (no pre-existing file reformatted).
- **Two responsive defects** (visible in screenshots, invisible to the earlier overflow metrics): the global `.search { min-width: 240px }` pushed the label input 13px out of its card at 320px and over the status text in the columned layout at 844x390; controls were 15px on touch devices (iOS zooms on focus). Fixed in the screen's own stylesheet. A method error was also caught: scripted `.focus()` is not keyboard focus; with real Tab presses the focus ring is present.

Known limits, stated plainly:

- `sch-004-005-006-service-delivery.spec.ts` is **not repeatable on a database it has already run against** (it searches for "Search Alpha" and expects one school). It is not in this branch's diff and passes on a fresh database, which is how CI runs it. Two of its tests failed in a second run here for that reason.
- The intermittent Playwright `POST /auth/logout` hang seen earlier when many specs run in one process was **not observed** in the final runs, and remains **unexplained**.
- The full Playwright suite (non-school specs) was not run. The lock-timeout `409` (AC-07) is not reachable from a browser and is covered by a backend test that passes.
- "Student dashboard" (original brief) is not applicable: `DEC-ROLE-004`, school students never log in; the approved spec maps it to the parent view, which passes.
- QA-008 (raw "fetch failed" text when the API is down) and QA-009 (no `aria-current`, no `h1`) are app-wide, open, and not ENH-004.
