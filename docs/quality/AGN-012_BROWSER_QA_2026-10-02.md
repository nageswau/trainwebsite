# AGN-012 — Browser QA (first pass, 2026-10-02)

**Build:** `feature/agn-012-agent-visa` @ `1733b09` (the stack was built from this tree). **Stack:** isolated compose project `agn012qa`
— web http://localhost:13012, API 18012, `alembic current` = `0061_agent_visa_details (head)`, `python -m app.seed` applied.
**Browser:** no Browser Use tool is available in this environment (no `browser-use` CLI, no browser MCP), so the pass used headless
Chromium from the project's own Playwright (`@playwright/test`, no new dependency) with an **isolated browser context per role** and a
throwaway QA script kept outside the repository (`.superpowers/…/qa/`, git-ignored). Data was created through the real UI and API: the
seeded Master `agent@edusphere.local`, a new staff member of that agency (activated as the e2e helper does), the seeded `counselor`,
`student.overseas`, `overseasadmin`, a signed-out visitor, and fresh no-login students with applications at `offer`. Console errors,
page errors, failed requests, non-2xx responses, main-frame navigations and broken images were captured for every context.
**No product code was changed during this pass.**

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Start visa case (application date + Passport) → "Visa case started." (focused), badge "Checklist", "Passport: Not uploaded"; gate blocks the move; Passport uploaded to the application and verified → move to Documentation; dates edited; skip to Decision (confirmed); Approved recorded (confirmed) → read-only with the date recorded and the disclaimer. |
| 2 | Invalid inputs | PASS — interview before the application date → field error on "Interview date", `aria-invalid`, focus on the field, value kept; gate refusal → `role=alert` naming Passport, focused. Year 1999: blocked by the browser's date validation, no request sent (QA12-03). |
| 3 | Empty states | PASS — "No visa case yet." + Start; empty checklist "No documents are required on this checklist." |
| 4 | Server errors | PASS — injected plain-text 500 → "Something went wrong on our side. Please try again; your entry is kept."; aborted request → "The request did not complete. Check your connection and try again; your entry is kept."; form and values kept. |
| 5 | Loading states | PASS — 1.5 s latency: "Saving…" disabled. |
| 6 | Cancel / back | PASS — Cancel returns focus to the opener ("Move visa stage"); Escape in the skip confirmation returns focus to "Move". |
| 7 | Refresh | PASS — after reload the decision, dates and checklist persist. |
| 8 | Duplicate submission | PASS — double click on Save and on "Yes, record decision" → exactly 1 PATCH each; a second tab that still showed "No visa case yet." → `409 "A visa case already exists for this application"` and the tab reloads to the case. |
| 9 | Unauthorized | PASS — signed out: `/overseas/agent/applications` → `/overseas/login?next=%2Foverseas%2Fagent%2Fapplications`; API `PATCH`/`POST …/visa` → `401`. |
| 10 | Incorrect role | PASS — counselor, overseas student, overseas admin: API `403`; the agency page shows "Access unavailable — Role/division mismatch" (screenshots `14-role-*.png`). Staff: assigned student's case editable; an unassigned application's `PATCH` → `404`. |
| 11 | Desktop 1280 | PASS — no horizontal overflow (QA12-04 visual note). |
| 12 | Tablet 768 | PASS — no overflow; Visa section 628 px. |
| 13 | Mobile 390 / 320 | PASS — no overflow (scrollWidth − innerWidth = 0) with the edit form open; date inputs and checkboxes usable. |
| 14 | Navigation | PASS with QA12-01 — the uploaded document is listed on Documents › Uploaded; the "Visa" sidebar filter does not list an application whose visa case is under way while the application is at Offer. |
| 15 | Success messages | PASS — "Visa case started.", "Visa details saved.", "Visa case moved to Documentation./Decision.", "Visa decision recorded." (all focused; QA12-05). |
| 16 | Error messages | PASS — server wording for gate, stale and duplicate; field-level date order; generic 500/offline wording. |
| 17 | Broken images | PASS — none on Applications, Documents or any layout. |
| 18 | Console errors | PASS — no app errors or uncaught exceptions; only the browser's "Failed to load resource" lines for the deliberate 422/409 and the injected 500/abort (QA12-07). |
| 19 | Failed network calls | PASS — 188 `net::ERR_ABORTED` GETs are Next.js link prefetches cancelled by navigation; no unexpected failures; non-2xx only the deliberate 422 ×2 and 409. |
| 20 | Unexpected redirects | PASS — only the signed-out redirect to login (with `next=`) and the sign-in landings. |
| — | Legacy (admin-created) case | PASS — a case created by the overseas admin with `["Passport", "Visa form"]` shows "Visa form: Not uploaded" and the note "Also on this checklist: Visa form…"; a dates-only save does not send the checklist; ticking SOP sends `["Passport","SOP"]` → `200`, "Visa form" replaced on screen and server (review I-2 fix confirmed). |
| — | One section form at a time | PASS — Visa form open → Enroll and Update status hidden; Enrollment open → Visa section hidden; a same-stage save closes the Visa form (review I-1 fix confirmed). |
| — | Withdrawn application | PASS — after withdrawal the Visa section shows the case with no buttons. |

## Findings

| ID | Severity | Role | Page | Reproduction | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA12-01 | Low (UX / product) | Master, Staff | Applications › sidebar "Visa" (`?status=visa`) | 1. Application at Offer. 2. Start a visa case (any stage). 3. Click "Visa" under Applications. | An agency looking for its visa work would expect applications with a visa case in progress to be listed. | Not listed: the filter is the application stage (`visa_documentation`/`status_tracking`, AGN-008 D7); the visa case does not move the application stage (DEC-SCOPE-055 V5). Needs an owner decision (filter by case, or move the stage), not a defect against the spec. | QA C15: count 0 for the started application. |
| QA12-02 | Low | Master | Application detail › Visa | 1. Start a case with Passport. 2. Upload and verify a Passport for this application (Documents page or another tab). 3. Look at the open detail. | Checklist status current, or a hint that it changes when documents are verified. | Still "Passport: Not uploaded" until the detail reloads; "Move visa stage" then succeeds (the server reads the real status) and the list updates to "Verified". | QA C06. |
| QA12-03 | Low (consistency / a11y) | Master | Visa › Start / Edit form | Type 1999-01-01 in "Visa application date" and submit. | The same inline, announced field error as the other date errors. | Only the browser's native date-range bubble; no inline message, no `aria-invalid`; no request sent. | QA C03: 0 requests, `validity.valid=false`, no `.form-error`; `02-invalid-year.png`. |
| QA12-04 | Low (visual hierarchy) | Master | Visa section | Open an application with a case. | Sub-heading at least as prominent as the text it labels. | "Document checklist" (`h6`) renders smaller than the list items under it. | `08-decided.png`. |
| QA12-05 | Info (UX) | Master | Application detail | Save anything in the Visa section while scrolled down to it. | Feedback near the action. | The success notice is at the top of the application detail and takes focus, so the page scrolls up away from the Visa section (the AGN-013 Enrollment pattern). | `08-decided.png` (notice above the fields). |
| QA12-06 | Info (product) | Master | Application detail › Status history | Move the visa case or record a decision. | — | Visa changes appear only in the audit log and the AGN-021 activity view, not in "Status history" (by design, spec §4). Noted for the owner. | — |
| QA12-07 | Info | — | — | Trigger a validation refusal. | — | The browser logs "Failed to load resource: 422/409" for expected refusals; Next.js prefetch aborts (`ERR_ABORTED`) on navigation. Not app errors. | `results.json` evidence. |

No Critical, High or Medium findings. The two Important issues from the whole-branch review (I-1, I-2) are confirmed fixed in the browser.

## Not covered in this pass

- The Browser Use tool itself (unavailable here; Playwright Chromium used, as in AGN-013).
- Screen-reader announcement order (roles, labels, focus and `aria-invalid` were checked), and a real (not injected) server failure.
- The committed Playwright spec `agn-012-visa.spec.ts` was not run in this pass (the exploratory script covered the same flow).
