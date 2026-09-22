# ENH-011 — Browser QA and fixes (2026-09-22)

**Scope:** first exploratory QA pass of ENH-011 (`DEC-SCOPE-023`), then test-first fixes.

**Environment:**
- **Build:** branch `feature/enh-011-skills-tracker-generalization`. QA ran on `ea90fa5`; fixes are `4604dd8`…`dfbc02b`.
- **Stack:** isolated Compose project `enh011` — web on :3411, API on :8411, seeded and migrated Postgres.
- **Browser:** a separate local Chrome 153 with a throwaway profile, driven over CDP (Browser Use). The window was kept visible; see the harness notes.

**Accounts:** created through the public API:
- school A (Silver) and school B (Bronze), each with a coordinator;
- Career Counselors for A, for A and B, and for B;
- an Academic Team member at A;
- four students;
- a parent linked to one student.

**Not committed:** the raw screenshots and scripts.

## Findings and resolution

| ID | Severity | Finding | Status | Evidence of the fix |
|---|---|---|---|---|
| QA-01 | High | Batch page at 390 px: layout viewport 713 px; title, "Change" column and Enrol button cut off | **Fixed** `81bd362` | Page grid uses `minmax(0, 1fr)`. The E2E spec asserts `scrollWidth <= 390` (RED 714 → GREEN); Chrome re-check shows 390/390 |
| QA-02 | Medium | Unsaved attendance silently lost on in-app navigation (Next `<Link>` does not fire `beforeunload`) | **Fixed** `edd6a79` | Capture-phase link guard while dirty. Unit test; in Chrome a `confirm` opens, "Stay" keeps the page and the marks, "Leave" navigates |
| QA-03 | Medium (a11y) | Focus dropped to `<body>` after Certify / Cancel / a status change | **Fixed** `f888796` | Unit tests; in Chrome focus goes to Confirm → back to Certify → to the row header after a change |
| QA-04 | Medium | Attendance and score lists returned unordered; an upsert reordered them (the full backend run failed once) | **Fixed** `4604dd8` | `ORDER BY` enrolment ID (and assessment ID). Deterministic RED: update the row whose ID sorts first |
| QA-05 | Low/Med | End-before-start error not tied to a field; message "End_date must be on or after start_date" | **Fixed** `45122d8`, `c4bb74f` | Browser-side check marks End date; server message is now "The end date must be on or after the start date" |
| QA-06 | Low | Raw Pydantic text ("Input should be a valid date or datetime, input is too short") | **Fixed** `c4bb74f` | Browser-side "Enter a title" / "Choose a start date"; focus goes to the first invalid field; no request sent |
| QA-07 | Low | Each 422 message shown twice (field and alert) | **Fixed** `c4bb74f` | With field messages shown, the alert says "Check the highlighted fields." |
| QA-08 | Low | Success messages accumulate across sections | **Fixed** `c4bb74f` | Messages clear after 8 s (unit test; Chrome: present at 2 s, gone at 11 s) |
| QA-09 | Low | Duplicate-session message used "2026-10-06" | **Fixed** `45122d8` | "This batch already has a session on 05 Oct 2026" |
| QA-10 | Low | 5xx showed only "Something went wrong." | **Fixed** `c4bb74f` | "The change was not saved because of a problem on our side. Your entry is kept; please try again in a moment." |
| QA-11 | Low | Buttons under 40 px on a phone | **Fixed** `dfbc02b` | Phone-only rule scoped to `.skills-page`. The E2E spec asserts every visible button is at least 44 px at 390 px (RED: 4 buttons → GREEN) |
| QA-12 | Low | Certified row had a blank "Change" cell | **Fixed** `c4bb74f` | "No further changes" |
| QA-13 | Low | List page had no `<h1>` | **Fixed** `c4bb74f` | "Skills batches" is the `h1` |
| QA-14 | Low | Wrong role or signed out: the access card offers "Return to login" even to a signed-in user | **Fixed app-wide** `58245c5` (on the owner's instruction) | One shared helper replaces the 23 copies (21 school pages, the admin transfers page, `PortalPage`): 401 → "Return to login"; signed in → "Go to your dashboard" (`ROLE_DASHBOARD_PATH`). Unit tests; on the running app a signed-in Academic Team user gets `/school/academic-team/dashboard` on a skills page, a coordinator page and the admin transfers page, and a signed-out visitor gets `/overseas/login` |

## Observations (by design, for review)

- **O-1:** coordinators and teachers see Skills only as timeline events. There is no Skills card with attendance or scores on their student pages (spec §5.2).
- **O-2:** after a transfer, the losing school's counselor keeps a read-only view of the student's batch history (`DEC-SCOPE-023` D9).

## Passed in the first pass (unchanged by the fixes)

- **Happy path:** keyboard create, enrol with filter, add session, attendance, assessment, scores, certify with confirm/cancel.
- **Parent:** dashboard chips, Skills card, timeline events, notifications (enrolled, certified).
- **Coordinator:** timeline events; entitlements show real counts.
- **Transfer (via ENH-005):** the enrolment shows as "Transferred out", read-only and left out of the inputs.
- **Access:**
  - another portfolio's batch and a malformed ID both give "Batch not found" (masked);
  - a parent cannot open an unlinked child;
  - wrong roles are refused.
- **Duplicate submission:**
  - double-click on Enrol sends 1 POST;
  - double Enter on Create sends 1 POST;
  - a score above the maximum is blocked in the browser.
- **Error states:**
  - an expired session shows "Sign in again";
  - a network failure keeps the entry;
  - an injected 500 keeps the entry.
- **Loading and states:**
  - the loading skeleton shows on a slow network;
  - the closed batch hides write controls and reopening works;
  - refresh and Back work.
- **Layout and page health:**
  - desktop and tablet are clean;
  - no broken images;
  - no JavaScript errors;
  - no unexpected redirects.

## Targeted Playwright run after QA-14 (2026-09-22)

The specs that assert "Access unavailable", plus ENH-011's own, were run on the rebuilt stack: `agt-001`, `auth-002`, `sch-001`, `sch-007`, `sch-008`, `sch-reports`, `enh-011`. Result: **11 passed, 1 failed**.

The failure is `sch-001:63`, which timed out on `page.request.post("/api/v1/auth/logout")` (line 92). It failed on 3 of 3 attempts; a repeated run also failed `sch-001` AC03 once, which passes alone.

Why it is not attributed to QA-14:
- The hang happens before the test reaches any "Access unavailable" page.
- The API logged every logout it received as `200` in a few milliseconds, with no errors.
- The same logout takes 6–20 ms when called directly on the API.

So the request is lost on the Next.js rewrite / CI proxy path. This matches the unexplained intermittent logout hang already recorded by ENH-004.

**Not proven by an A/B run:** the same spec has not been run against a build without `58245c5`.

## Harness notes (not app defects)

- A hidden Chrome window does not paint. React 19 reveals streamed Suspense content (the `loading.tsx` routes) on a painted frame, so while the QA window was hidden the skills pages did not hydrate and a click did a native GET submit. With the window visible, hydration took 0.4 s.
- The QA machine's antivirus (Kaspersky) injects a script that makes its own background requests (`gc.kis.v2.scr.kaspersky-labs.com`). They are not app traffic and were excluded from the request counts.
