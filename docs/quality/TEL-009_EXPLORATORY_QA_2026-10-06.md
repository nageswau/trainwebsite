# tel-009 — Exploratory browser QA (2026-10-06)

Stack `tel009` (web :3089, API :8089, `EMAIL_ENABLED=false`), branch `feature/tel-009`. Browser: isolated Edge 154 over CDP :9389 driven
by browser-use (real coordinate clicks and key presses), plus Playwright `tel-009-qualification.spec.ts`. Data: one overseas telecaller
manager, two overseas telecallers, and leads with products UK, Java, General Enquiry and Canada (handed over: `owner_id` set directly, since
tel-018 isn't built), plus another telecaller's UK lead.

## Scenarios

| # | Area | Role | Result |
|---|---|---|---|
| 1 | Happy path: overseas lead (UK) → Masters, MSc Data Science, Sep 2027, 72.5 %, city Chennai | telecaller | Pass. Saved, "Qualification saved.", Lead details shows Chennai and B.Tech CSE at once (QD1), stage stays Assigned (QD3), "Last updated by …" |
| 2 | Invalid input: 120 % / 150 % | telecaller, manager | Pass. In-place message, `aria-invalid`, nothing sent. **QA-01** found (focus); fixed and re-verified |
| 3 | Empty state: a lead with no answers | telecaller | Pass. "Not recorded" for every blank |
| 4 | Server error: qualification read answers 500 | telecaller | Pass. "Unable to load the qualification." + Retry; the retry loads the values |
| 5 | Loading | telecaller | Pass. "Loading the qualification…" status line |
| 6 | Cancel | telecaller | Pass. Edits discarded |
| 7 | Refresh | telecaller | Pass. Values persist after reload; the transient success line is gone |
| 8 | Duplicate submission: triple click on Save | telecaller | Pass. One PUT (the button disables while saving) |
| 9 | Leave guard: unsaved edit, then a nav link | telecaller | Pass. "Discard the qualification changes?" confirm; declining stays on the page |
| 10 | Handed-over lead | telecaller | Pass. Values shown, no edit button; PUT `403` |
| 11 | Another telecaller's lead | telecaller | Pass. "Lead not found"; qualification GET `404` |
| 12 | Wrong role (counselor, it_admin, student) | — | Covered by the API tests (`403`); the page-level guard is tel-008's |
| 13 | Manager on a handed-over lead | manager | Pass. Edits and saves (D1); "Last updated by QA Qual Manager" |
| 14 | IT lead (Java) | telecaller | Pass. "IT training requirement" with "Course interested in: Java"; the Offline radio saves |
| 15 | Other product (General Enquiry) | telecaller | Pass. Basic fields only, "General Enquiry has no IT or overseas questions." |
| 16 | Product change UK → Canada → Java → UK (AC3) | telecaller (and e2e) | Pass. The section follows the saved product; the overseas values return when the product is overseas again |
| 17 | Layout 375 / 768 / 1280 | telecaller | Pass. No horizontal scroll; fieldsets stack on mobile |
| 18 | Console / page errors, failed network calls | telecaller | None besides the intended 403/404/500 probes |
| 19 | Broken images, unexpected redirects | — | None |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low (a11y) | telecaller | `/telecaller/leads/{id}` Qualification | Edit qualification → Academic percentage 120 → Save | Focus moves to the first refused field (the BdmLeadForm pattern) | Focus stayed on Save; the error was announced (`role=alert`) but the keyboard user had to find the field | **Fixed** in `f379f30a` (TDD: two vitest assertions red → green); re-verified in the browser: focus lands on `academic_percentage` |

No open issues.
