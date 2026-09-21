# ENH-005 — final browser verification (2026-09-21)

**Result: not COMPLETE.** *The latest evidence is the "Final gate" section at the end (a fresh run at HEAD `71c371e`: Playwright 29 passed / 4 failed, Browser Use 90 PASS / 12 NOT TESTABLE / 1 FAIL); the tables below record the earlier pass at `82cfae6`.* Originally 3 findings FAILED (AC-18, AC-24 ×2 parts). **The two AC-24 parts were fixed the same day and re-verified in the browser on a rebuilt `web` (see "AC-24 fixes" at the end); AC-18 was resolved afterwards as no regression (see "Baseline comparison" at the end)**. 13 checks are NOT TESTABLE from a browser. Everything else observed passes.

## Method and build under test

- **Build:** the isolated `enh005-e2e` stack, rebuilt from HEAD `82cfae6`: `api` created 11:27:03Z and `web` 11:27:07Z, both after the commit (11:07:10Z). An earlier "rebuilt" stack was found to be stale (unchanged creation times) and was not used.
- **Tool:** Browser Use (CDP) driving headless Chrome. Setup and API probes were made from inside the page with the signed-in user's own cookies; UI actions (filing, cancel, approve by keyboard, reject, filters, navigation) were made through the real screens. Source code was not modified.
- **Data:** a fresh world per run (tagged `1789990349`): Sunrise (losing) and QA Lakeview (gaining) schools, two extra schools, seven roles, parents (one with a sibling, one only-child, one unaccepted invite), a Lake-only academic-team member, and Draft/Verified/Published results, test-prep, language, career and psychometric records on the student that moved.
- **Widths:** 320, 375, 768, 1024, 1440.
- **Not covered:** browsers other than Chrome, screen readers, real touch devices.
- **Invalid runs kept in the record (7):** each was a flaw in my check, not a product defect: a throttle premise (two earlier refused cancels count toward the limit), a whole-page text match, a non-uploader editing a result (403 before status, existing DEC-ROLE-007), an invalid page size, a lazy-loaded logo in the collapsed mobile nav, an over-broad live-region count, and a first audit read.

## Verdict per acceptance criterion

| AC | Verdict | Basis |
|---|---|---|
| AC-01 | PASS | Filed through the UI; admin view shows from-school and filing school = Sunrise (server-derived) |
| AC-02 | PASS | Identical 403 for foreign and unknown student; same-school/unknown destination 422; client-supplied fields 422; bad UUID/NUL 422; all non-coordinators 403 |
| AC-03 | PASS (DB-level part NOT TESTABLE) | Second pending request 409 |
| AC-04 | PASS | Identical neutral UI message and identical `202 {accepted:true}`; one row only for a real other-school student; malformed and Unicode look-alike codes 422 |
| AC-05 | PASS | Redacted row (nulls, same keys) then complete after approval; UI never shows name or school before approval |
| AC-06 | PASS | Cancel in the UI; identical 403 for foreign/unknown; re-cancel 409; other schools never see the request |
| AC-07 | PASS | Every non-admin role and unauthenticated refused (403/401); admin (UI, keyboard) and super_admin approve; role matrix on all three screens |
| AC-08 | PASS | Losing coordinator 403 and roster empty of the student; gaining coordinator reads it; portfolio staff flip |
| AC-09 | PASS | Teacher assignment and pending parent email cleared |
| AC-10 | PASS | Parent with a sibling stays and reads both; only-child parent moves and still reads; unlinked student 403 |
| AC-11 | PASS | Withdrawn results vanish from list, progress average and the parent's view; verify/publish 409; uploader's edit 409; published stays |
| AC-12 | PASS | Career, psychometric, test-prep, language and published result all in the gaining timeline (API and UI) |
| AC-13 | PASS (stale-approve part NOT TESTABLE) | Rejection changes only the request; re-approve and re-reject 409 |
| AC-14 | PASS | Coordinator/parent history has no staff IDs or reason; admin history has names and reason |
| AC-15 | PASS (notification-failure part NOT TESTABLE) | Exactly one audit row per step, seen in the Super Admin Security & Audit Logs UI; notices to both coordinators and the parent |
| AC-16 | NOT TESTABLE | Needs fault injection inside the transaction |
| AC-17 | PASS (promotion race NOT TESTABLE) | Two simultaneous approvals: `[200, 409]`, one history row |
| AC-18 | PASS (no regression) | 31 of 33 existing Playwright specs pass at `82cfae6`; the failing ones fail identically on the baseline `550c4fe7` ("Baseline comparison" at the end) |
| AC-19 | PASS | Loading, empty, error (500/401/network), success, two-step confirm, plain-text rendering |
| AC-20 | NOT TESTABLE | 50 open requests cannot exist in a browser: the 30/hour throttle stops a coordinator first |
| AC-21 | PASS | Both lists: defaults, 422 validation, total, newest first |
| AC-22 | PASS | Incoming rejection notice carries the code only; approval/outgoing notices name the student |
| AC-23 | NOT TESTABLE | Query-count assertion |
| AC-24 | PASS after fixes (was FAIL, 2 parts) | The two failing parts were fixed and re-verified (below); the rest passed in the first run (320–1440 no overflow, images, labels, names, keyboard, status as text) |
| AC-25 | PASS | Parent school line only when children span schools; Principal and Teacher pages unchanged |
| AC-26 | PASS (lapse after an hour NOT TESTABLE) | 31st attempt 429 + Retry-After, in the UI too; other coordinator unaffected; 422 still first |
| AC-27 | PASS (metadata content NOT TESTABLE) | One `filed` row per request; `denied` rows exist; the audit screen does not show metadata |
| AC-28 | PASS (non-parent case NOT TESTABLE) | Moved parent: role, division, email unchanged; profile is only `school_id` |
| AC-29 | PASS (data query is the owner's) | Cross-school parent link 422; that parent still 403 |
| AC-30 | NOT TESTABLE | E-mail body is not visible in a browser |
| AC-31 | NOT TESTABLE | Logs are not visible in a browser. Supplementary read-only inspection of the API container log: 0 occurrences of any name, code, e-mail, reason or note from this run across 437 transfer lines |
| AC-32 | PASS | U+202E and U+2066 422, U+200D accepted; every mutation route rejects GET (405) |

## Previously found defects, retested on the final build

D1 (long school name overflow) PASS at all five widths; D2 (coordinator notices reachable, nav) PASS; D3 (double click sends one POST) PASS; D4 (confirm buttons side by side) PASS; N1 (readable 422) PASS; N2 (2xx that is not the request: outgoing form, cancel, admin decision) PASS; N3 (queue on its own page, first action at 603 px on 1440×900, counts agree) PASS; N4 (form collapsed above the record) PASS; invite warning PASS; console and page errors none; failed network calls none other than the deliberately simulated ones.

## Failures, with reproduction (as found; AC-24 (a) and (b) are fixed, see the end)

**AC-24 (a): a table on a new screen.** The criterion says the new screens render no table. The coordinator Notifications screen (added after the spec, mirroring the Parent notifications page) renders one. Repro: sign in as a school coordinator, open `/school/coordinator/notifications`, `document.querySelectorAll('.portal-content table').length === 1`. The transfers screen, the admin queue and the student-page form have none.

**AC-24 (b): live region not mounted before the result.** The outgoing request form's confirmation is inserted as `<div role="status">` when it succeeds; there is no pre-mounted status region for it. (The Transfers page has 3 live regions on load and the admin queue 2.) Repro: coordinator, `/school/coordinator/students/<id>`, open "Request a transfer", count `[role=status]` (none belongs to the form), submit. Whether assistive technology announces an inserted region could not be tested here.

**AC-18: `sch-team-management.spec.ts:79`** (SCH-001 addendum) fails 3 of 3: `#edit-teacher` has value `""` when Edit is clicked. **The cause is not shown to be ENH-005**: `SchoolStudentsPanel.tsx` is untouched by this branch and nothing in this branch's `schools.py` diff touches teachers or the roster. The teacher options are fetched by the client from `/school/team` (about 300 ms here against about 15 ms for other calls, because the shared test database holds thousands of accumulated users) into an uncontrolled `<select defaultValue>`, so an early click leaves the value empty. It was then run on the baseline (`550c4fe7`) against the same database and fails identically ("Baseline comparison" at the end), so it is not an ENH-005 regression. Repro: `run_e2e.ps1 sch-team-management` on this stack.

## AC-24 fixes (same day, after the verification above)

Both were fixed test-first (each new test was seen to fail, then pass) and re-verified in the browser on a `web` container rebuilt at 12:35:31Z, after the last edit.

- **(a) Table on the Notifications screen.** `SchoolNotificationList` now renders a labelled list (`ul.link-list`, `aria-label="Notifications"`) in the same rows the transfers screen uses. Browser: 0 tables and 8 notices at 320/375/768/1024/1440 with no horizontal overflow; title, body, date, "new" badge and Open link present; the empty text is unchanged for a school with no notices; no console errors.
- **(b) Live region.** `SchoolTransferRequestForm` renders its `role="status" aria-live="polite"` region together with the form. Browser: before submitting, the region exists, is empty and is `aria-live=polite`; after a successful filing the confirmation appears in that same DOM element (verified by marking the node before the submit) and the form is gone; after a refresh the pending text is in the region and no form is offered; the error path is unchanged (alert, form and entry kept).
- **Checks:** 291 web tests, `tsc` and `eslint` clean; the ENH-005, `sch-007` and `sch-008` Playwright specs pass (4/4). The API was not changed.

## Final gate (fresh run at HEAD `71c371e`, after the AC-24 fixes; backend lint/type follow-up at `5aa27bf` below)

Everything below was produced by commands run for this gate, not carried over. **Verdict: ENH-005 is NOT COMPLETE.**

| Gate | Command / method | Result |
|---|---|---|
| Tree state | `git status`, containers' creation times | clean; `web` built 12:35:31Z after the newest web source (12:33:03Z); no API change since the `api` container's build |
| Web unit tests | `vitest run` | **PASS** 28 files / 291 tests |
| Web type check | `tsc --noEmit` | **PASS** exit 0 |
| Web lint | `eslint .` | **PASS** 0 errors; 31 warnings, none in a file this branch changed |
| Production build | `next build` | **PASS** exit 0; `/overseas/admin/school-transfers`, `/school/coordinator/transfers`, `/school/coordinator/notifications` built |
| Backend tests | full `pytest` | **977 passed / 14 failed**; the 14 (Razorpay 11, Zoho 3, credentials not configured) fail identically on `main`'s code (14 failed / 11 passed in those two files); 0 of 94 ENH-005 tests failed |
| Backend lint | `ruff check .` | 33 errors, **equal to `main`**; none in an ENH-005 line (`schools.py:1890` B904 is pre-existing) |
| Backend types | `mypy app` | at `71c371e`: **FAIL vs base** (195 errors vs `main`'s 154, all 41 new ones in `school_transfers.py`); **cleared at `5aa27bf`: 154 errors in 11 files = `main`** |
| Backend format | `ruff format --check .` | at `71c371e`: **FAIL vs base** (64 files vs `main`'s 56); **cleared at `5aa27bf`: 55 files, below `main`'s 56; every ENH-005 file formatted** |
| Migration | scratch DB: upgrade from empty, downgrade to `0033`, re-upgrade, `alembic check` | **PASS**: create-table only; downgrade removed only the ENH-005 table; no drift; scratch DB dropped |
| Disabled tests / debug code / TODO | scan of the 4,723 added lines under `apps/` | **PASS**: none. 5 suppressions, all justified (`BLE001` after commit ×2, `E731` in tests ×3) |
| Secrets | pattern scan of added lines | **PASS**: no keys, tokens or real hosts; test fixtures only (`Demo@123`, the existing seed password; `Sup3r-Secret-Pass!`, a test password) |
| Unrelated files | 65 changed files listed and the pre-existing ones' diffs read | **PASS**: all ENH-005 code, tests or docs |
| Playwright | all `enh-*` and `sch-*` specs | **29 passed / 4 failed**; ENH-005's 2 specs pass; see AC-18 |
| Browser Use | 13 scripts, fresh world (tag `1789996508`), 5 widths, all roles | **90 PASS / 1 FAIL (AC-18, resolved by the baseline comparison) / 12 NOT TESTABLE**; 3 invalid runs of my own flawed checks kept in the record |
| API log hygiene (AC-31, supplementary) | read-only grep of the API container log | 0 occurrences of any name, code, e-mail, reason or note from this run (1,043 transfer lines) |

**AC-18 in detail.** (1) `sch-004-005-006:189` and `:241` fail 2/2 in isolation because the spec is not idempotent: it searches `Search Alpha` and expects one school, and the shared database now holds four `E2E Search Alpha School <ts>` (one per past run); the ENH-004 record already noted it is "not repeatable on a used database". (2) `sch-team-management:79` fails every time: the roster's edit `<select>` uses `defaultValue` with options fetched by the client from `/school/team` (about 300 ms here); with that fetch delayed 2 s the value stays `""` after the options arrive, demonstrated in the browser on this build. `SchoolStudentsPanel.tsx` is untouched by this branch. (3) `enh-003:91` fails in full runs and passed 2/2 in isolation. All four were then run on the baseline ("Baseline comparison" at the end) and fail identically there, so AC-18 is a no-regression PASS.

**Open, so not COMPLETE:** the owner decision on unaccepted parent invites; the full Playwright suite beyond `enh-*`/`sch-*`.

## Follow-up: backend type check and formatting (`5aa27bf`)

The two backend gates that failed at `71c371e` were fixed with no behavior change and re-measured with the same commands on `main` and on this branch.

- **`mypy app`:** 154 errors in 11 files, equal to `main` (was 195). The 41 errors were `Optional` results of `db.scalar`/`db.get`, plain `dict`/`str` passed where the response models want `SchoolRef`/`UserRef`/`Literal`, and two unannotated dicts. `_ref` and `_direction` now return the real types, rows guaranteed by a foreign key are fetched through one narrowing helper, and `count()` results default to 0. The helper uses Python 3.12 type-parameter syntax; both Dockerfiles are `python:3.12-slim` and `pyproject.toml` targets `py312`.
- **`ruff check`:** 33 errors, equal to `main`; clean on every ENH-005 file. (A first pass had added 2 errors, an import order and the generic-helper style, and both were fixed.)
- **`ruff format`:** applied to the 9 new ENH-005 python files only; 55 files would still be reformatted against `main`'s 56, all of them files `main` already had unformatted.
- **Behavior:** the 94 ENH-005 backend tests pass; the full backend suite is **977 passed / 14 failed**, and the 14 failures are the same Razorpay (11) and Zoho (3) tests that fail on `main`, with none in an ENH-005 file.
- **Not re-run after this change:** the Browser Use pass and the Playwright specs ran against the `api` container built before this refactor (it was not rebuilt), so they are evidence for the code before `5aa27bf`; the backend tests above are the evidence for the refactor.

**Still open, so ENH-005 is not COMPLETE:** the owner decision on unaccepted parent invites; the full Playwright suite beyond `enh-*`/`sch-*`.

## Baseline comparison for AC-18 (2026-09-21)

**Question.** Do the 4 existing Playwright tests that fail on the branch also fail without ENH-005?

**Baseline.** `550c4fe7`, the merge commit ENH-005 was cut from (`git merge-base main HEAD`). Not today's `main`, which has since gained ENH-006 (23 commits), so the comparison isolates ENH-005 alone. The baseline has no `school_transfers.py`; its API exposes 0 paths containing "transfer" against the branch's 10 (checked in the running containers). The 3 spec files and `SchoolStudentsPanel.tsx` are byte-identical to the branch's.

**Method.** Images built from an extract of the baseline (`docker build`, api and web; the web image's backend URL points at the baseline api). Both containers ran on the existing test network with their own network aliases, against **the same database** as the branch stack (the one holding thousands of accumulated users and four `E2E Search Alpha` schools), with the baseline's API started without its migration step because the database is already at revision `0034`. The tests ran in the same Playwright image with the baseline's own `tests/` mounted. The baseline containers were removed afterwards; the branch stack was not touched.

| Test | Branch (this database) | Baseline (same database) |
|---|---|---|
| `sch-004-005-006:189` (portfolio search) | fails 2/2 | fails 2/2: `toHaveCount(1)` received 5, then 6 (one more `Search Alpha` school per run) |
| `sch-004-005-006:241` (select all / clear) | fails 2/2 | fails 2/2 |
| `sch-team-management:79` (deactivated teacher) | fails every run | fails 3/3: `#edit-teacher` expected a value, received `""` (line 101); test timeout 15 s |
| `enh-003:91` (Re-send from the keyboard) | fails in full runs, passes alone | 1 pass, 1 fail of 2 (`toBeFocused`: inactive) |

**Conclusion.** All four reproduce on the baseline with the same database, so none is caused by ENH-005. They are pre-existing under used-database conditions: two are non-idempotent specs, one is a timing race in the roster edit form (client-fetched options with `defaultValue`), one is flaky. **AC-18 (existing behavior preserved) is a no-regression PASS.** The database state, not the code, is what makes them fail; a fresh database was not tried.

**Still open, so ENH-005 is not COMPLETE:** the owner decision on unaccepted parent invites; the full Playwright suite beyond `enh-*`/`sch-*`.
