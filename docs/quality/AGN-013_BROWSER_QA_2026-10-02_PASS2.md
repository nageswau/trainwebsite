# AGN-013 — Exploratory browser QA (independent pass 2, 2026-10-02)

**Build:** `feature/agn-013-enrollment-confirmation` @ `ad3e39b` (web container rebuilt from this tree; API unchanged since `4cd29b7`).
**Stack:** isolated compose project `agn013qa` — web http://localhost:13013, API 18013, `python -m app.seed` applied.
**Browser:** isolated headless Chromium 151 (fresh profile / fresh context per role), trusted input.
**No code was changed during this pass.**

**Tooling note.** Browser Use 0.13.10 (run ephemerally with `uvx`, attached to an isolated Chromium on CDP 9313) was tried first.
JavaScript evaluation worked, but trusted input (`Input.dispatchMouseEvent` / `dispatchKeyEvent`) reached the page only on the first
page loaded into its tab; after the first navigation no mouse, move or key event arrived (verified with capture-phase listeners; tried
background vs activated tab, no device emulation, event domains off, mouse-state reset, a fresh profile). Rather than fake clicks
with JavaScript, the pass was run with Playwright (the project's `@playwright/test`, no new dependency) in the same kind of isolated
headless Chromium: real clicks and typing, `page.route` for failure injection, console / page-error / HTTP ≥ 400 / failed-request /
main-frame-navigation capture on every page.

**Roles and data.** Seeded Master `agent@edusphere.local`; a newly registered and approved agency (Master + one staff member, two
assigned students); seeded `counselor`, `student.overseas`, `overseasadmin`; signed-out visitor. Fresh no-login students with
applications at offer, visa documentation, status tracking ("Next intake"), enquiry, and one enrolled by the Overseas Admin.

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Dashboard → Applications → Offer received → View → Enroll student → date, student ID, note → Confirm enrollment → "Confirm enrollment? A commission will be estimated and the application can no longer be withdrawn." (focus on Yes) → Yes → "Enrollment confirmed." (focus on it); header badge "Enrolled"; section shows date, ID, "Confirmed by the agency"; history "Offer → Enrolled" with the note; list card "Enrolled"; exactly one commission `estimated / 0`. Also from visa documentation and status tracking. |
| 2 | Invalid inputs | PASS with QA13-09 — empty date: Confirm disabled; 1999-12-31: native "Value must be 01-01-2000 or later.", no confirmation opened; 70 characters typed → 60 kept; bidi override in the student ID → 422 shown, input kept (QA13-09); API: missing date 422, extra field 422, pre-offer 422 "An offer is needed before enrollment". |
| 3 | Empty states | PASS — enquiry: no Enrollment section; admin-enrolled with no details: "Not recorded" ×2, "—", "Add enrollment details" → saved, still one commission (the admin's); "Next intake": "The intake is not a month and year, so the enrollment date was not checked against it." |
| 4 | Server errors | PASS with QA13-08 — injected 500 / 503 (HTML body) / 502 (empty): alert "Something went wrong.", focus on it, date kept. |
| 5 | Loading states | PASS — 2.5 s latency: "Saving…" disabled. "Go back" stays enabled; using it mid-save closes the confirmation, the form shows "Saving…", the save completes once. |
| 6 | Cancel / back | PASS with QA13-05 — Cancel closes the form, focus returns to "Enroll student"; Go back returns focus to "Confirm enrollment"; Escape (earlier pass) the same; browser Back returns to the applications list. |
| 7 | Refresh | PASS — reload with a half-filled form: back to the list, nothing saved (no warning — acceptable); reload after enrolling: details persist; the application moves from Visa/Offer to Enrolled. |
| 8 | Duplicate submission | PASS — double-click "Yes, confirm enrollment" → 1 PUT, 1 commission; double-click "Save enrollment details" → 1 PUT. |
| 9 | Unauthorized | PASS with QA13-03 — signed out: page → `/overseas/login?next=%2Foverseas%2Fagent%2Fapplications%3Fstatus%3Denrolled`; API 401. Session expired with the form open: see QA13-03. |
| 10 | Incorrect role | PASS — Staff (assigned): offer → "An agency Master confirms enrollment.", no buttons, status options stop at Status tracking; enrolled → details read-only, no buttons; API 403 "Only an agency Master can confirm enrollment" (also 403 for another agency's id). Other agency's Master → 404 "Application not found". Counselor / student / Overseas Admin: API 403; page "Access unavailable — Role/division mismatch". |
| 11 | Desktop 1440 | PASS — 0 px page and section overflow; inputs 1030 px wide. |
| 12 | Tablet 820 | PASS — 0 px overflow; inputs 680 px. |
| 13 | Mobile 390 / 320 | PASS with QA13-06 — 0 px overflow with the form and the confirmation open; inputs 282 / 212 px. Buttons are 38 px tall (shared `btn small`; below a 44 px touch target, app-wide, not AGN-013). |
| 14 | Navigation | PASS with QA13-04 — sidebar Applications / Offer received / Enrolled / Commissions navigate, `aria-current` on the active filter. |
| 15 | Success messages | PASS — "Enrollment confirmed." / "Enrollment details saved." (`role=status`, focused). |
| 16 | Error messages | PASS with QA13-08, QA13-09, QA13-11 — stale (two tabs): 409 "This application changed since you opened it -- reload to see its current status", the detail reloads to the other tab's enrollment, still one commission. |
| 17 | Broken images | PASS — none at any width. |
| 18 | Console errors | PASS — no uncaught exceptions; console errors only for the HTTP 4xx/5xx deliberately provoked (browser "Failed to load resource" lines). |
| 19 | Failed network calls | PASS — only the injected failures and `ERR_ABORTED` Next.js link prefetches cancelled by navigation (framework behaviour, all pages). Offline: "The request did not complete. Check your connection and try again; your entry is kept." |
| 20 | Unexpected redirects | PASS — none; the only redirect is signed-out → login with `next=`. |

## Issues

### QA13-03 — Medium — expired session shows "Not authenticated" with no way to sign in
- **Role / page:** Master — `/overseas/agent/applications` → application detail → Enrollment.
- **Steps:** sign in; open an enrolled application; Edit enrollment details; let the session expire (cookies cleared); change the student ID; Save enrollment details.
- **Expected:** a plain message that the session ended, with a Sign in link (returning here), input kept — the AGN-014 QA14-08 / AGN-006 QA6-02 precedent.
- **Actual:** alert "Not authenticated" (server text), no link; the user stays on the page with no next step.
- **Evidence:** `PUT /api/v1/workflows/overseas/agent/crm/applications/{id}/enrollment` → 401 `{"detail":"Not authenticated"}`; console "Failed to load resource … 401". Screenshot `q09-expired.png`.

### QA13-04 — Low (accessibility) — opening the form drops focus
- **Role / page:** Master — application detail → Enrollment.
- **Steps:** click "Enroll student" (or "Edit enrollment details" / "Add enrollment details").
- **Expected:** focus moves into the form (the date field), so keyboard and screen-reader users know it opened.
- **Actual:** the opener unmounts and focus falls to `<body>`; nothing is announced (the next Tab happens to reach the date field).
- **Evidence:** `document.activeElement` = `BODY` after the click; no console/network effect.

### QA13-05 — Low — Cancel keeps the abandoned input
- **Role / page:** Master — Enrollment form.
- **Steps:** Enroll student → type a date → Cancel → Enroll student.
- **Expected:** the form reopens empty (or with the stored values when correcting); Cancel discards.
- **Actual:** the cancelled date (2027-09-20) is still filled in.
- **Evidence:** date input value after reopening = `2027-09-20`.

### QA13-06 — Low — other actions stay live while the enrollment confirmation is open
- **Role / page:** Master — application at offer / visa / status tracking.
- **Steps:** Enroll student → Confirm enrollment (the "Confirm enrollment?" step is showing); scroll down.
- **Expected:** competing actions on the same application (Change status, Withdraw application) hidden or disabled until the confirmation is answered.
- **Actual:** "Move to … Update status" and "Withdraw application" remain usable directly below "Yes, confirm enrollment" (long, mixed stack on mobile). The server serialises them (a later enrollment would get the stale 409), so this is clarity, not integrity.
- **Evidence:** screenshot `q11-mobile320-confirm.png`.

### QA13-07 — Low — correction mode shows the values twice
- **Role / page:** Master — enrolled application → Edit enrollment details.
- **Expected:** the read-only details give way to the edit form (as the AGN-008 Edit does).
- **Actual:** the read-only "Enrollment date / University student ID / Confirmed by the agency" list stays above the inputs holding the same values.
- **Evidence:** screenshot `q09-expired.png` (lower half).

### QA13-08 — Low — server-error message gives no next step
- **Role / page:** Master — Enrollment confirm / save.
- **Steps:** a 500 / 502 / 503 on the PUT.
- **Expected:** "Something went wrong on our side. Please try again." (AGN-014 wording) — and that the entry is kept, as the offline message says.
- **Actual:** "Something went wrong." only.
- **Evidence:** injected 500/502/503; console "Failed to load resource … 500/503/502". Screenshot `q06-500.png`.

### QA13-09 — Low — the 422 message does not name the field
- **Role / page:** Master — Enrollment form.
- **Steps:** paste a student ID containing a bidirectional-override character → Confirm → Yes.
- **Expected:** the message names the field (University student ID) and the field is marked invalid (`aria-invalid`, described by the message).
- **Actual:** "Must not contain control or bidirectional-override characters" in the detail-level alert; the field is not marked.
- **Evidence:** `PUT …/enrollment` → 422 `{"detail":"Must not contain control or bidirectional-override characters"}` (mapped). Screenshot `q04-422.png`.

### QA13-10 — Low — pre-existing, outside AGN-013: the Commissions page lists commissions by ids only
- **Role / page:** Master — `/overseas/agent/commissions`.
- **Steps:** enroll a student; open Commissions from the sidebar.
- **Expected:** the new estimated commission is identifiable (student, university).
- **Actual:** the generic table shows Reference (commission UUID), Application (UUID), Amount, Status, Claim reference — 20 rows, matching the API, but no names; the API (`GET …/agent/commissions`) does return `student` and `university`.
- **Evidence:** page text sample in this pass; not an AGN-013 regression (the page is AGT-003/AGN-002 era).

### QA13-11 — Info — "--" in the stale message
- The 409 text "This application changed since you opened it -- reload to see its current status" shows a double hyphen to the user (existing AGN-008 copy, shared).

## Fix pass (2026-10-02, owner: "fix the issues") — commit `194e564`

Test first: 7 new component tests (`AgentApplicationEnrollment.test.tsx`, QA13-03…09) failed against the old behaviour, then passed;
`apiErrors.test.ts` updated for the additive `detail` on a failed `sendJson` outcome (+1 test).

| ID | Fix | Re-verified in the browser (rebuilt web container, headless Chromium, trusted input) |
|---|---|---|
| QA13-03 | 401 → "Your session has expired. Your entry is kept; sign in again in a new tab, then save." + "Sign in again" (new tab), the AGN-006 QA6-02 pattern | message + link `/overseas/login` `target=_blank`, date kept; after signing in in another tab, Save → "Enrollment confirmed.", one commission |
| QA13-04 | opening Enroll / Edit / Add focuses the date field | focus on `enrollment-date-…` after opening, also in correction mode |
| QA13-05 | Cancel restores the stored values and clears errors | reopening after Cancel shows an empty date |
| QA13-06 | the status form and Withdraw are hidden while the enrollment form is open | 0 Withdraw / Move to while open; back after Cancel |
| QA13-07 | correction mode shows the inputs in place of the read-only values | "Confirmed by the agency" absent while editing |
| QA13-08 | 5xx → "Something went wrong on our side. Please try again; your entry is kept." | injected 500 → that message, date kept |
| QA13-09 | a 422 on a field is shown on that field (`aria-invalid`, described by the message, focused) | bidi character in the student ID → field invalid, described, focused |
| QA13-10 | not fixed — pre-existing Commissions table (outside AGN-013) | — |
| QA13-11 | not fixed — shared AGN-008 stale message (outside AGN-013) | — |

Also: 0 px overflow at 320 with the form open; no console errors apart from the provoked 401/500. Playwright on the same build:
`agn-013` 2/2, `agn-008` 4/4, `agt-003` 2/2, `agn-014` 1/1, `agn-009` 2/2, `agn-016` 3/3, `agn-006` 2/2 — 16 passed.

## Screenshots

Session scratchpad `qx/`: `q01-offer-detail`, `q02-confirm`, `q03-enrolled`, `q04-422`, `q05-admin-enrolled-empty`, `q06-500`,
`q07-saving`, `q08-stale`, `q09-expired`, `q10-staff-offer`, `q11-{desktop,tablet,mobile390,mobile320}[-confirm]`, `q12-goback-inflight`.
