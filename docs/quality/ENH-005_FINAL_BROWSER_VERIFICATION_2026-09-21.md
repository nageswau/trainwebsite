# ENH-005 — final browser verification (2026-09-21)

**Result: not COMPLETE.** 3 findings FAIL (AC-18, AC-24 ×2 parts); 13 checks are NOT TESTABLE from a browser. Everything else observed passes.

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
| **AC-18** | **FAIL** | 31 of 33 existing Playwright specs pass; `sch-team-management:79` fails 3/3 (details below); `enh-003` flaked once and passed 2/2 alone |
| AC-19 | PASS | Loading, empty, error (500/401/network), success, two-step confirm, plain-text rendering |
| AC-20 | NOT TESTABLE | 50 open requests cannot exist in a browser: the 30/hour throttle stops a coordinator first |
| AC-21 | PASS | Both lists: defaults, 422 validation, total, newest first |
| AC-22 | PASS | Incoming rejection notice carries the code only; approval/outgoing notices name the student |
| AC-23 | NOT TESTABLE | Query-count assertion |
| **AC-24** | **FAIL (2 parts)** | See below; the rest passes (320–1440 no overflow, images, labels, names, keyboard, status as text) |
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

## Failures, with reproduction

**AC-24 (a): a table on a new screen.** The criterion says the new screens render no table. The coordinator Notifications screen (added after the spec, mirroring the Parent notifications page) renders one. Repro: sign in as a school coordinator, open `/school/coordinator/notifications`, `document.querySelectorAll('.portal-content table').length === 1`. The transfers screen, the admin queue and the student-page form have none.

**AC-24 (b): live region not mounted before the result.** The outgoing request form's confirmation is inserted as `<div role="status">` when it succeeds; there is no pre-mounted status region for it. (The Transfers page has 3 live regions on load and the admin queue 2.) Repro: coordinator, `/school/coordinator/students/<id>`, open "Request a transfer", count `[role=status]` (none belongs to the form), submit. Whether assistive technology announces an inserted region could not be tested here.

**AC-18: `sch-team-management.spec.ts:79`** (SCH-001 addendum) fails 3 of 3: `#edit-teacher` has value `""` when Edit is clicked. **The cause is not shown to be ENH-005**: `SchoolStudentsPanel.tsx` is untouched by this branch and nothing in this branch's `schools.py` diff touches teachers or the roster. The teacher options are fetched by the client from `/school/team` (about 300 ms here against about 15 ms for other calls, because the shared test database holds thousands of accumulated users) into an uncontrolled `<select defaultValue>`, so an early click leaves the value empty. It was not compared against the base commit. Repro: `run_e2e.ps1 sch-team-management` on this stack.
