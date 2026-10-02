# AGN-013 — Browser QA (first pass, 2026-10-02)

**Build:** `feature/agn-013-enrollment-confirmation` @ `4cd29b7` (the stack was built from this tree). **Stack:** isolated compose
project `agn013qa` (web http://localhost:13013, API 18013), `python -m app.seed` applied. **Browser:** headless Chromium driven by the
project's own Playwright (`@playwright/test`, no new dependency): the committed spec, a throwaway QA script, and a temporary QA spec
(deleted, not committed). Data was created through the real UI and API: the seeded Master `agent@edusphere.local`, a new staff member
of that agency, and no-login students with applications at `offer` / `visa_documentation`. Console errors and uncaught exceptions were
captured for the Master flow. **No product code was changed during this pass.**

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Master: Enroll student → form shows University / Course / Intake read-only → date + student ID → Confirm enrollment → "Confirm enrollment? A commission will be estimated and the application can no longer be withdrawn." → Yes → "Enrollment confirmed.", final-status badge, details, status history "Offer → Enrolled". Exactly one commission `estimated / 0` in the Master's commission list. |
| 2 | Re-save / correction | PASS — Edit enrollment details → new date → "Enrollment details saved."; still one commission (Playwright `agn-013`). |
| 3 | Invalid inputs | PASS — Confirm disabled until a date is entered; server 422 keeps the form and input (component tests). |
| 4 | Date warning | PASS — 2027-10-05 against intake "Sep 2027": "The enrollment date is in the future and after the intake month. Check the date." shown; save not blocked; warning gone after correcting to 2027-09-25. |
| 5 | Server error | PASS — injected plain-text 500 → alert "Something went wrong."; form and date kept. |
| 6 | Offline | PASS — aborted request → "The request did not complete. Check your connection and try again; your entry is kept."; form kept. |
| 7 | Loading / duplicate submission | PASS — 1.5 s latency: "Saving…" disabled; exactly 1 PUT. |
| 8 | Stale screen | PASS — re-confirm with `expected_status: offer` on an enrolled application → 409 "This application changed since you opened it -- reload to see its current status". |
| 9 | Refresh | PASS — after reload the application is under Enrolled (no longer under Visa) and the details persist. |
| 10 | Incorrect role (Staff) | PASS — Staff (assigned student) see the Enrollment section read-only with no buttons; API PUT → 403 "Only an agency Master can confirm enrollment". |
| 11 | Unauthorized | PASS — signed-out PUT → 401. |
| 12 | Keyboard / focus | PASS — Enter in the student-ID field opens the confirmation; focus lands on "Yes, confirm enrollment"; Escape returns focus to "Confirm enrollment"; after save focus moves to the "Enrollment confirmed." notice. The date field takes three Tab stops (Chromium's native day / month / year segments). |
| 13 | Desktop 1280 | PASS with QA13-01 — no overflow. |
| 14 | Mobile 320 | PASS with QA13-01 — no horizontal overflow (scrollWidth − innerWidth = 0) with the edit form open; Playwright `agn-013` 320 px test passed. |
| 15 | Console | PASS — no console errors or uncaught exceptions in the Master flow. |
| 16 | Neighbours | PASS — Playwright `agn-008` ×4, `agt-003` ×2, `agn-014` ×1 passed on the same stack. |

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| QA13-01 | Low (UX) | Repetition on an enrolled application: the "Enrolled" badge appears three times (list card, detail header, Enrollment section) and Course / Intake are listed both in the detail fields and in the Enrollment section (University is also in the heading). The repetition follows the spec (§5: final-status badge; E5: university, course, intake shown in the Enrollment step). Option: show only Enrollment date, University student ID and Confirmed by the agency in the enrolled view, and keep the University / Course / Intake summary and the badge only where they add information (the confirmation form). | **Fixed** (owner: "continue task" after the recommendation) — the enrolled view lists only Enrollment date, University student ID and Confirmed by the agency; the header badge is the final status; University / Course / Intake stay in the confirmation form. Test first (component test red: 2 badges → green). Re-verified on a rebuilt web container: one Enrollment region, one commission, 0 px overflow at 320, no console errors; Playwright `agn-013` 2/2, `agt-003` 2/2, `agn-014` 1/1; `agn-008` 4/4 with `--timeout=30000` (at the configured 15 s, tests 1–2 time out at their last steps on the QA-grown shared demo agency — timing, not behaviour; AGN-006 precedent). |
| QA13-02 | Test defect (not product) | The committed Playwright spec looked up the "Enrolled" badge in the whole detail and matched the header badge too (strict-mode violation). | **Fixed** — scoped to the Enrollment region; spec re-run 2/2 passed. |

## Not covered in this pass

- Tablet width, screen-reader announcement order (only roles/labels checked), and a real (not injected) server failure.
- The full web and backend suites and the production build (owner cadence).
