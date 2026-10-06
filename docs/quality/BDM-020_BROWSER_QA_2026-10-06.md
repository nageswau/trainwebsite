# bdm-020 — browser QA log (2026-10-06)

**Feature:** School activity tracking, live per school (`DEC-SCOPE-089`, no migration).
**Environment:** isolated compose project `bdm020qa` (web :13020, API :18020, `app.seed` demo data); isolated Playwright Chromium in
the `bdm020qa` web-test container (Browser Use is not installed in this environment). Script: an exploratory Playwright pass driven as a
QA engineer (scratch, not committed). Screenshots were kept in the session scratchpad (not committed).
**Data:** "ABC International School" (the source example) seeded with 800 students: 650 guidance sessions completed and 50 scheduled,
580 psychometric completed, 300 language certified, 120 IELTS completed, 150 applications at University Selection and 20 at Enquiry.
Also a linked School with no students, an unlinked School organization, and a College organization.

## Pass 1 — independent exploratory QA (no code changes)

Covered:
- the happy path, checked against the API and the School's own `/school/analytics/student-development`;
- the empty states: a linked School with no students, and an unlinked organization;
- refresh and Back;
- roles: own School BDM, manager, other manager, College BDM, super_admin, School Coordinator (API and page), signed out;
- a manager opening a College organization;
- a malformed id;
- table semantics (column and row headers);
- 320 / 375 / 768 / 1366 px;
- console errors and failed network calls.

Duplicate submission is not applicable: the panel is read-only.

Results:
- AC1: the panel and API read **800 · 650/150 · 580/220 · 300/500 · 120/680 · 150/650**, identical to the School module. The
  scheduled sessions and enquiries were not counted.
- AC2: Student Profile Completion reads "Not tracked".
- AC3: no student name or id appears in the panel or in the API body.
- An unlinked organization reads "Not onboarded yet. Counts appear once Overseas Admin links the School."; the empty School reads 0 / 0.
- Other manager and College BDM get "Organization not found" with API 404; a Coordinator gets API 403 and the page shows "Access
  unavailable"; signed out gets 401 and is sent to the BDM sign-in. A manager opening a College organization sees no panel (API 404).
- There were no console errors, no failed requests, and no page overflow at any width.

| ID | Severity | Role / page | Steps | Expected | Actual | Outcome |
|---|---|---|---|---|---|---|
| QA20-01 | Medium | School BDM / manager, organization page, 320–375 px | Open a linked School organization on a phone | The Completed / Pending counts are visible | The table kept the global 650 px minimum: it scrolled inside a 246 px box with no visible cue, so only the metric names showed | **Fixed** (test-first, the e2e asserts the table fits and the last cell is fully in view at 320 / 375 px): `.bdm-school-activity .table { min-width: 0 }`, plus tighter padding and sentence-case headers at ≤ 640 px (the `.tel-targets` precedent) |

Not exercised in the browser: a failed server-side read of the panel. The page reads it on the server, so a client-side intercept
cannot cause it. The error card and its "Try again" are covered by `BdmOrganizationSchoolActivity.test.tsx` (failure, failed retry,
malformed answer, successful retry).

## Pass 2 — re-verification on the final build

QA20-01: at 320 px the table measures 246 / 246 and at 375 px 301 / 301, with every count visible. The full pass-1 scenario set gave
the same results. Playwright `bdm-020-school-activity.spec.ts` passed together with bdm-002/003/004/005/017/018 (8 passed, one worker).
