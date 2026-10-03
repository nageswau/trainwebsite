# AGN-015 — Exploratory browser QA (first pass, 2026-10-03)

**Build:** `feature/agn-015-student-journey` @ `1f34a2a` (the stack was built from this worktree). **Stack:** isolated compose project
`agn015qa` — web http://localhost:13015, API 18015, `alembic` head `0066_audit_entity_index`, `python -m app.seed` applied.
**Browser:** Browser Use (`uvx browser-use`), attached over CDP (port 9315) to an isolated headless Chromium 153 with a fresh profile.
Trusted input was verified before each scenario (capture-phase `mousedown`/`click` with `isTrusted: true`). Console errors,
exceptions, HTTP ≥ 400 and failed requests were collected from CDP (`Runtime`, `Log`, `Network`) on every step. Failures were injected
with CDP `Fetch` (500, 401, connection refused / disconnected, held request). **No product code was changed during this pass.**

**Data** (created through the running app's API only; no direct database writes): seeded Master `agent@edusphere.local`; staff
`QA Staff One` (`EDU-S001`) and `QA Staff Two` (`EDU-S002`) activated through the Overseas Admin welcome link; students
`QA Journey Full 045927` (assigned to Staff One: counseling completed, one shortlist entry, Passport requested → uploaded against the
request → verified by the Master → downloaded ×6, application A at stage `visa_documentation` with a conditional offer, a pending
deposit and a visa case, application B withdrawn, one task; 23 history events), `QA Journey Empty 045927` (assigned to Staff One;
nothing recorded) and `QA Journey Unassigned 045927`. One status note carries an HTML/script payload.

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Master and Staff One: the Journey shows Create/Counseling/Shortlist/Documents Done; application A Offer Done, Deposit and Visa In progress, Enrollment Not started; application B every step Withdrawn; captions "University · intake · stage". History lists all 23 source events once, newest first, each with its actor (agency members by name). Duplicated audit rows (create/advance/offer/upload) do not appear twice. See QA15-02. |
| 2 | Invalid inputs | PASS — a status note `<img onerror…><script>…</script>` renders as text (no element created, `window.__xss` undefined). Read-only feature: `limit`/`offset` bounds are covered by API tests (422). |
| 3 | Empty states | PASS — student with nothing: Counseling/Shortlist/Documents Not started, "No applications yet."; history "Assigned to staff", "Student created". |
| 4 | Server errors | PASS — journey 500 → "Unable to load the journey." + Try again → recovers; history 500 → "Unable to load history." (`role=alert`) + Try again → recovers. See QA15-07. |
| 5 | Loading states | PASS — held request: "Loading journey…" / "Loading history…" (`role=status`); while paging, "Updating history…" and `aria-busy`. |
| 6 | Cancel / back | PASS — Edit counseling → Cancel: the Journey returns unchanged. Browser Back from Applications → Students with the search kept. See QA15-04. |
| 7 | Refresh | PASS (existing behaviour) — reload closes the detail panel (it is not URL state, as before AGN-015); reopening re-reads both endpoints. History has its own Refresh button. |
| 8 | Duplicate submission | PASS — double-click on the history Next: one `/timeline?offset=20` request (button disabled while loading). Show history twice toggles open/closed; no duplicate request when closed. |
| 9 | Unauthorized user | PASS — Staff Two (not assigned): student not listed; `/journey` and `/timeline` → 404 `{"detail":"Student not found"}`. Signed out: `/overseas/agent/students` → `/overseas/login?next=…`; API 401. |
| 10 | Incorrect role | PASS — counselor and overseas student: API 403 "This role cannot perform this operation" on both routes. |
| 11 | Desktop layout | PASS — 1440 and 1024: steps in one wrapped row per list, current step outlined, no overflow. |
| 12 | Tablet layout | PASS — 768 and 820: steps wrap to two rows per application, no overflow, history full width. |
| 13 | Mobile layout | PASS with QA15-06 — 375 and 320: one step per row, no horizontal overflow, history toggle 44 px tall. |
| 14 | Navigation | PASS — keyboard: from the student heading, Tab reaches Show history (10 stops), Enter opens, Space toggles, visible focus ring; step items are not tab stops; Escape closes the panel (existing). See QA15-03. |
| 15 | Success messages | N/A for the feature (read-only). The counseling save notice still appears, and the Journey updates without reopening. |
| 16 | Error messages | See 4; 401 → "Your session has expired. Sign in again" with a link (QA15-08). |
| 17 | Broken images | PASS — none. |
| 18 | Console errors | PASS — none, except the requests a step deliberately provoked (401/403/404/500). |
| 19 | Failed network calls | PASS — none outside the injected failures. |
| 20 | Unexpected redirects | PASS — only the expected sign-in redirect with `next=`. |

Archived student (extra): the Journey and history stay readable; the history gains "Archived · Global Admissions Agent".

## Issues

| ID | Severity | Role | Page | Reproduction | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA15-01 | **Medium** | Master, Staff | Students → View (detail panel) | Open `QA Journey Empty` (Shortlist "Not started") → Add university to shortlist → choose Monash → Save to shortlist. (Same for Remove, and for tasks/history.) | The tracker shows Shortlist "Done" (acceptance: "the step tracker matches the stored data"); an open history shows the new event. | Tracker still "Shortlist Not started"; no `/journey` request after the `POST …/shortlist` 201; the open history is unchanged until Refresh. Reopening the student shows "Done". The tracker only reloads when the student record's `updated_at` changes (counseling/edit do; shortlist and tasks do not). | Network: `POST /crm/students/{id}/shortlist` 201, no `GET …/journey` afterwards; reopen → `GET …/journey` → Shortlist `done`. Screenshot `13-after-reopen.png`. |
| QA15-02 | Low (needs product decision) | Master, Staff | Detail → Journey | Full student, application A (no submission date recorded, stage `visa_documentation`, offer recorded). | Step order reads as progress. | "Application In progress" next to "Offer Done", and the current-step outline sits on Application. Follows the approved J3 rule (Application done only when a submission date exists) — the CRM create form does not require one. | Screenshots `20-desktop-1440-journey.png`, `22-tablet-768-journey.png`. |
| QA15-03 | Low (a11y) | Master, Staff | Students page with a student open and history shown | List buttons by accessible name. | Unique names per control. | Two "Next page" and two "Previous page" buttons (students-list pager and history pager). They sit in differently labelled navs, but a screen-reader button list cannot tell them apart. | AX tree: 2 × `button "Next page"`, 2 × `button "Previous page"`. |
| QA15-04 | Low (UX) | Master, Staff | Detail panel | Show history (page 2) → Edit counseling → Cancel. | The page keeps its place; history stays as it was. | The Journey and history are removed while any form is open (one-form-at-a-time, by design), so the content jumps up; after Cancel the history is collapsed again and back on page 1. | Observed in steps 6/14. |
| QA15-05 | Low (copy) | Master, Staff | History | Show history on the full student. | Readable field names. | Raw column names: "university id", "due at, title", "budget currency", "counseling completed" (listed on a first save even when left unticked — AGN-006's audit lists every field set). | History rows 9, 14, 15. |
| QA15-06 | Low (mobile) | Master, Staff | Detail → Journey at 320/375 px | Open the full student on a phone. | A compact tracker. | Every step is a full-width row: 4 + 5 per application (14 rows for two applications, ~550 px) before Counseling. No overflow. | Screenshot `20-mobile-320-journey.png`. |
| QA15-07 | Low (a11y) | Master, Staff | Detail → Journey | Force the journey request to fail (500 or offline). | The failure is announced to assistive technology. | Inline text + Try again with no live region (spec §7 chose no `role="alert"` to keep the panel's alerts unique); a screen-reader user is not told. History errors are announced (`role=alert`). | DOM: `.jny p.form-error` without `role`/`aria-live`. |
| QA15-08 | Info | Master, Staff | Detail → Journey / history | Expire the session (forced 401). | Sign in returns to the page. | "Sign in again" links to `/overseas/login` with no `next=` (the existing `SIGN_IN_PATH` convention, as AGN-021). | `href="/overseas/login"`. |

## Test-environment notes (not product defects)

- In this headless Chromium 153 build, a long-lived tab intermittently stopped receiving CDP mouse input and `Page.captureScreenshot`
  timed out; a fresh tab always recovered. Every scenario therefore ran in a new tab after a trusted-input probe. Five screenshots
  timed out (`15`, `16`, `20-tablet-landscape-1024`, `21-mobile-320-history`, `22-tablet-820`); the measurements for those steps were
  still taken from the DOM.
- `Emulation.setDeviceMetricsOverride` stopped input delivery in the tab that used it, and `Browser.setWindowBounds` had no effect on
  the headless viewport; layouts were measured under emulation with no further clicks in that tab.
- The site sets `scroll-behavior: smooth`; element centres were measured after an instant scroll.

Screenshots: session scratchpad `shots/` (not committed).

**Status:** first QA pass complete — 1 Medium, 6 Low, 1 Info. Nothing fixed yet.
