# ENH-025 — Exploratory QA record (2026-09-23)

**Feature:** ENH-025 Student Master field coverage (`DEC-SCOPE-027`).
**Pass 1 (find, no code changes):** build `8ecb042`. **Fix pass:** commit `52929b3`.
**Environment:** isolated Docker stack `enh025` (web `http://localhost:3025`, API `:8025`), seeded; Microsoft Edge 153 in
an isolated InPrivate instance (own profile, sync and extensions disabled, occlusion tracking off), driven by Browser Use
over CDP. Viewports 1366×900, 768×1024, 375×812. A fresh world per pass: school A (coordinator, principal, teacher,
parent, counsellor) and school B (coordinator, counsellor with an empty portfolio).
**Method:** an independent exploratory pass across the twenty requested areas (happy path, invalid inputs, empty states,
server errors, loading, cancel/back, refresh, duplicate submission, unauthorized, incorrect role, three layouts,
navigation, success/error messages, broken images, console errors, failed network calls, unexpected redirects), with
console, exception and network events captured from CDP for every step.

## Result

No Critical or High findings. Every server-side authorization check held in pass 1 (403/401/422 for every cross-role,
cross-school, logged-out and extra-field attempt). **7 findings fixed** in this item (3 Medium, 4 Low), each reproduced
first by a failing vitest or browser check; **9 logged as follow-ups** (outside ENH-025's change or by design).

### Fixed in ENH-025

| ID | Sev | Finding | Fix | Verified by |
|---|---|---|---|---|
| QA2-01 | Medium | A photo that failed on page load showed the browser's broken-image icon, not the initials (the `<img>` failed before hydration, so `onError` never ran) | The image is created only once the component is live; the server HTML carries the placeholder | `SchoolStudentPhoto.test.tsx` (server-render has no `<img>`); Edge: photo request blocked → "AN" placeholder; normal load → image |
| QA2-02 | Medium | A teacher opening `/school/coordinator/students/{id}` got the coordinator shell, the transfer disclosure and a photo control that failed with 403 | The page is coordinator-only, checked before the student is read (same pattern as `/school/coordinator/transfers`) | `SchoolCoordinatorStudentPage.test.tsx`; Edge: teacher → "Access unavailable / School Coordinator role required", no file input; teacher's own page unchanged |
| QA2-03 | Medium | The profile and photo were reachable only through a roster button labelled "Timeline" | Renamed to "Profile & timeline" | `SchoolStudentsPanel.test.tsx`; Edge row actions `Edit / Link parent / Profile & timeline` |
| QA2-05 | Low | Messages exposed API field names (`roll_number '12'…`, `student_mobile…`, `subjects items…`); photo wording differed client vs server | Messages shown with the form's labels ("Roll number 12 is already used…", "Each subject must be…"); photo type/size wording identical on both sides; bulk report uses the same wording | `schoolStudents.test.ts` (10 cases), panel, card, photo and bulk tests; Edge |
| QA2-06 | Low (a11y) | An error was not tied to the field it was about | The rejected input gets `aria-invalid`, is described by the error (`aria-describedby`), receives focus, and is bordered in the error colour | panel and card tests; Edge: `#edit-roll` `aria-invalid=true`, described by `edit-form-error`, focused, border `rgb(185, 28, 28)` |
| QA2-08 | Low | Empty Grade/Class and Date of birth showed "-" while every other field showed "Not recorded" | Both are profile rows like the rest | `SchoolStudentDetailPanel.test.tsx`; Edge |
| QA2-09 | Low | "Remove photo" rendered full width like an input | Photo buttons keep their natural width | Edge: 120 px |

After the fixes: web unit **55 files / 510 tests**; `tsc` 0; lint clean on every touched file; browser QA
(`docs/quality/ENH-025_browser_qa.py`) **18/18**; Playwright (serial) `enh-025`, `sch-002`, `sch-team-management`,
`sch-008`, `enh-012`, `sch-009`, `sch-010`, `enh-004`, `enh-005` pass. `sch-001` passes functionally (20.6 s and 15.1 s)
but exceeded its fixed 15-second test budget on this loaded machine (another stack's API at ~48% CPU); its flow
(login, invites, dashboards) touches none of the changed code. The `sch-002` ENH-025 spec was updated to the new
message wording (an intended behaviour change, not a test adapted to hide a defect).

### Logged as follow-ups (not changed here)

| ID | Sev | Finding | Why not in ENH-025 |
|---|---|---|---|
| QA2-04 | Low | Counsellor dashboard is 395 px wide at 375 px: long student labels ("Name — School 1790156347") widen both cards' selects | Root cause is the existing records card's option labels; the new card inherits it |
| QA2-07 | Low | Network failure and HTTP 500 both show "Something went wrong."; for a network failure the save may or may not have happened | Existing error-handling pattern across the portal |
| QA2-10 | Low | Unsaved edits are discarded without warning (refresh during roster edit; switching student in the counsellor card) | Optional in scope review; no unsaved-changes pattern exists in the app |
| QA2-11 | Low | Empty / header-only / non-CSV upload reports "0 of 0 rows accepted. Rows that succeeded are kept…" | SCH-002 behaviour |
| QA2-12 | Info | Semicolon-delimited CSV (EU-locale Excel) → every row "full_name is required" | SCH-002 parsing |
| QA2-13 | Info | Uploading the same file twice duplicates rows without a roll number (new Idempotency-Key per submit) | SCH-002 behaviour |
| QA2-14 | Info | Malformed student id → "[object Object]" | Error rendering in a page ENH-025 did not change |
| QA2-15 | Info | Expired session: "Not authenticated" with no route back to sign-in | Portal-wide pattern |
| QA2-16 | Info | iPhone HEIC photos rejected without guidance | By design (`DEC-SCOPE-027` item 3); guidance text is a product decision |

## Verified with no issue (pass 1)

Happy path (every field stored exactly, API read-back); invalid inputs (empty name native-required, roll clash
case-insensitive, bad mobile, 21 subjects, 81-char item, bidi override, 120-char cap — values kept, nothing created);
empty states; loading ("Saving…", disabled fieldset, `aria-busy`; counsellor "Loading…"); cancel/back; refresh; duplicate
submission (double-click, 3×Enter, double Save → one record / one PATCH); unauthorized (401); incorrect role (every
server write refused); roster, student and bulk pages at 1366/768/375 with no overflow; navigation and Back links; real
JPEG uploads (36 KB, 1.5 MB) rendered; fake `.jpg` rejected server-side; >2 MB and HEIC rejected client-side; console
clean apart from the browser's automatic lines for deliberately provoked 4xx/5xx; no unexpected redirects.

## Harness notes (not product issues)

- The first Edge instance auto-enabled Microsoft-account sync and a policy-installed password-manager extension that
  swallowed synthetic typing; replaced by an InPrivate instance with sync and extensions disabled before any finding.
- With other windows on top, Windows occlusion marked the QA tab `hidden` and Edge dropped synthetic input; relaunched
  with occlusion tracking and background throttling disabled.
- The app's `scroll-behavior: smooth` made one early coordinate click land on the wrong field (student "Meera Iyer" was
  created with scrambled values); the helper was fixed to scroll instantly and verify every typed value. All findings
  come from verified steps.
