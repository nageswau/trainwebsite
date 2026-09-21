# ENH-005 — browser QA record (2026-09-21)

Feature: student school transfer / reassignment (`ENH-005`, `DEC-SCOPE-021`).
Tool: Browser Use (CDP) against a separate headless Chrome driving the running web app, plus Playwright (`enh-005-school-transfer.spec.ts`).

**Status of this record: NOT a completion record.** See "Open items". (The independent code review was run after this record was written; see `ENH-005_CODEX_REVIEW_2026-09-21.md`.)

## Method and environment (read this before trusting the results)

- **Stack:** an isolated compose project (`enh005-e2e`: web `:3300`, API `:8300`, its own Postgres/Redis volumes, migration `0034`, seeded with
  `python -m app.seed`). It is not the developer's `:3000` stack. Every rebuild of `web` was proved by the container's creation time,
  because an earlier "healthy" report came from stale containers while the new build was failing.
- **Two passes.** The first pass (before implementation) found the feature absent, which is what the user expected of an unbuilt feature and
  is not a defect list. The second pass was run by the implementer after implementation, on the same checklist (happy path, invalid input,
  empty/server-error/loading states, cancel, refresh, duplicate submission, wrong role, unauthorised, three viewports, keyboard, console and
  network). It is **not independent** in the sense the user meant: the same agent built and tested the feature.
- **Data:** the shared test database accumulated schools and requests from the suites (the admin queue holds well over 100 rows; the destination
  list holds hundreds of schools, including one with a 200-character name created on purpose). Nothing here touches a real database.
- **Not covered:** browsers other than Chrome, screen readers, real touch devices, a production build behind a real proxy.

## Findings

| ID | Severity | Role | Page | Finding | Status |
|---|---|---|---|---|---|
| D1 | Medium | Coordinator | `/school/coordinator/students/[id]` | The destination `<select>` sizes itself to its longest option; with a 200-character school name the student page was about 2,600px wide in a 1,424px window (horizontal scroll). | **Fixed `96d18f4`, verified in the browser.** The first fix (`max-width: 100%`) was declared done on a jsdom-only test and was still broken: the grid field around the select had itself grown to the content width, so the percentage resolved against the wrong parent. A live CSS probe showed `width: 100%` on the select plus `min-width: 0` on the field contains it. The Playwright spec now creates a 200-character school name and asserts `scrollWidth <= innerWidth` with the form open; it failed on the unfixed build and passes on the fixed one. |
| D2 | Medium | Coordinator | (no page) | A coordinator was notified when a transfer was decided or a student joined, but no coordinator screen could show those notices. | Fixed `f27ff30`: `/school/coordinator/notifications` and a nav item; the Playwright spec asserts both the requester's and the gaining school's notice. |
| D3 | Low | Coordinator | student page | Two clicks in the same task on "Request transfer" could send two requests (a React state guard does not see the second click). | Fixed `f27ff30`: a ref guard. Re-checked in the browser: one POST for a same-task double click. |
| D4 | Low | Admin | `/overseas/admin/school-transfers` | The "Confirm approval" and "Cancel" buttons rendered as full-width stretched bars. | Fixed `f27ff30`, verified in the browser. |

## Third pass (2026-09-21, after the D1 fix; report only, nothing was changed in this pass)

Run on the same isolated stack against the build containing `96d18f4`. Still the implementer's own pass, not an independent one. Chrome headless via
CDP; server failures were **simulated in the page** (`fetch` replaced for one call), because the stack's lifecycle belongs to the user, so they show
how the UI handles each response, not that the server produces it.

**Checked and behaving as designed** (each was run, not inferred): empty submit gives a field error tied by `aria-invalid`/`aria-describedby` and
sends nothing; a 501-character reason, a NUL character and a bidi/control character each give a 422 that is shown and keeps the entry; an HTML/`<script>`
reason is stored and shown as text on the coordinator list, the admin row and the rejection note (no element created, no script run); the pending state
survives a refresh and replaces the form; a second filing for the same student answers `409 A transfer request is already pending`; Cancel returns the
form; back/forward and refresh behave; the Student ID field rejects 0, 3, 7 and 9 characters, non-hex, an Arabic-Indic digit and HTML with a field
error and no request; a real code and an unknown code get the identical `202 {"accepted": true}` and the identical on-screen message; lower-case is
accepted; a repeat by the same school adds no second row; all five status filters (a `<select>`) give correct counts and empty states; the admin
reject flow (Escape returns focus to the button, one POST for a same-task double click, the note is escaped, the requester's notice reads "was not
approved" and names no student) and its failure states (409 lock, 500, 401 with a sign-in link, focus moves to the alert, the row stays); a 429, 401,
409, 422-array and empty-500 response each give a readable alert that takes focus and keeps the entry; in-flight state disables the button, select and
textarea and reads "Sending request…"; tab order is summary → destination → reason → submit; Parent, Teacher, Coordinator and Admin each see the right
screens and `403` from the wrong API; a signed-out visitor gets "Access unavailable — Not authenticated" (coordinator pages) or the login redirect with
`next=` (admin page); no horizontal overflow at 320/375/768/1024/1440 on the four screens; zero console errors, page errors and unexpected failed
requests across the pass. The "broken image" a first script flagged was a lazy-loaded logo in a background tab; it loads (640px) once the tab is
foreground, on pages ENH-005 did not touch.

| ID | Severity | Role | Page | Finding | Status |
|---|---|---|---|---|---|
| N1 | Low | Coordinator | student page, transfers page | Validation errors show the framework's wording: "Value error, must be 500 characters or fewer" and "Value error, must not contain control or bidirectional-override characters". The prefix is noise to a coordinator. | **Fixed, verified in the browser** (commit after `796383c`): `detailMessage` drops the prefix from the 422 list and capitalises ("Must be 500 characters or fewer"); a string `detail` is untouched. Confirmed against the real API for a 501-character reason and a NUL character. |
| N2 | Low | Coordinator | student page | A `200` whose body is not a request (a proxy's HTML page, simulated) is reported as "Transfer request sent for review", so the coordinator is told it was filed when nothing was. `ENH-004` QA-004 fixed the same class on its form ("could not be read, repeating it is safe"). Checked afterwards: the Student-ID form already refused it; **Cancel had the same flaw, and the admin Approve/Reject would have crashed** on the missing outcome. | **Fixed for all three, verified in the browser:** a 2xx whose body has no string `id` (`isRequestBody`) is no longer reported as a success. The filing form keeps the entry and says the reply could not be confirmed and that repeating is safe; Cancel keeps the row and offers a reload; the admin decision re-reads the queue. Simulated with a proxy page, an empty body and `{}`. |
| N3 | Low–Medium | Admin | `/overseas/admin/school-transfers` | The page opens with the generic read-only "School Transfers" table (raw reference UUIDs, ISO timestamps such as `2026-09-21T09:43:43.167562+00:00`, capped at 200 records) **above** the actionable queue, so the approve/reject controls start below the fold and the two lists disagree ("200 role-scoped records" against "Transfer requests (201)"). | **Fixed** (owner asked for it): a dedicated page, `/overseas/admin/school-transfers`, with an admin-role guard, a title and the queue only; the portal payload, its test and the `WorkflowPanel` wiring were removed. Verified by unit tests (roles allowed and denied, no table, queue straight after the title); **browser re-check pending a rebuild of the isolated stack**. |
| N4 | Low | Coordinator | student page | "Request a transfer" is the last item on a long page (after the Journey timeline), so on a phone it is a long scroll to find. | **Fixed** (owner asked for it): the collapsed disclosure is now the card directly under the student header, ahead of Grade history and the timeline. Verified by a unit test on the order and the collapsed state; **browser re-check pending a rebuild**. |

Not exercised in this pass: a real `429` from the 30-per-hour limit (it would lock the QA coordinator for an hour; the UI's handling of a `429` was
simulated), a successful approval (the Playwright spec covers it by keyboard), the parent-facing history in the browser (also the Playwright spec).

## Observations, not defects of ENH-005 (recorded, not changed)

- The destination list is unpaginated and, in the shared test database, has hundreds of options. Real deployments have few partner schools; a
  searchable picker is a product choice, not decided here.
- At or below 768px the shared admin `DataTable` scrolled inside its own container (no page-level overflow). Pre-existing component; no longer on this page since the N3 fix.
- A single `409` was seen on one POST during the D3 re-check. The admin queue afterwards held an earlier pending request for the same demo
  student (`Kabir Nair`, created 09:03 the same day by an earlier check), which is the documented "already pending" refusal. This was inferred from
  that row, not reproduced under a controlled sequence.
- Leftover `pending` rows from QA runs remain in the isolated database.

## Regression runs on this branch

- `enh-005-school-transfer.spec.ts` (2 tests) passes, with the new overflow assertion, against a freshly rebuilt `web` (container created
  09:23:28Z), together with `enh-004`, `sch-003`, `sch-007`, `sch-008` and `sch-roster-*`.
- `sch-001-school-portal-access.spec.ts` › "coordinator adds a student…" **failed on its 15-second test timeout** in the first run right after the
  rebuild (and once more when run alone), and **passed 3 of 3 when repeated** at 11.1–11.9 seconds. The test performs several logins and sits
  close to its own limit, so this is timing under load, not a failed assertion. It was not measured against the base commit, so it is **not**
  shown that ENH-005 did not slow it. `sch-001`'s second test failed on the first run and passed on the rerun.

- Full backend suite on this branch (throwaway Postgres in the isolated stack, run 2026-09-21 on HEAD `d06682f`): **975 passed, 14 failed** in
  14 minutes. All 14 are in `test_pay_001_stu_010_payment_gateway.py` (11) and `test_zoho_meeting_integration.py` (3), the provider-credential tests;
  none is in an ENH-005 file. The same suites failed on the base commit in the `ENH-004` record (there 22, including tests needing a seeded DB; this
  database is seeded), but this run did not re-run the base commit, so "identical to base" is **not** claimed for these 14.
- Frontend: 27 files, 282 tests passed (273 before the N1/N2 fix, 280 before the invite warning); `tsc --noEmit` and `eslint` on the changed files clean.

## Open items (must be decided or done; not hidden)

1. **A parent invited but not yet accepted when the student transfers is left with no child** after accepting (spec §13, `DEC-SCOPE-021`).
   **Mitigated 2026-09-21, then decided by the owner (keep the admin warning):** the admin's preview now has a boolean `pending_parent_invite`; the queue row and the confirm step both
   warn in words. Verified in the browser with a real student created with a parent email (warning shown, the same page for a student without an
   invite shows none, the confirm step repeats it, the address is not in the payload, no overflow at 375px). The invite still does not survive a
   transfer, by the owner's decision of 2026-09-21 (`DEC-SCOPE-021`): the admin warning is kept; carrying the invite over and blocking were not chosen.
2. The independent code review (Codex) has been run and its findings dispositioned: `ENH-005_CODEX_REVIEW_2026-09-21.md`.
3. N1–N4 are all fixed and were re-verified in the browser (`ENH-005_FINAL_BROWSER_VERIFICATION_2026-09-21.md`).
4. The full Playwright suite was not run (only the school and enhancement specs).
5. Raw screenshots, exploratory scripts and console/network captures are not committed.
