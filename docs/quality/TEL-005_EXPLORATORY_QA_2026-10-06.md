# tel-005 exploratory QA — 2026-10-06

Stack `tel005` (web :3085, API :8085, migration head `0086_lead_enquiries`), isolated Edge (CDP :9385) driven by Browser Use.
Accounts: a telecaller manager, two IT telecallers reporting to that manager, and an IT counselor, all created for the session.

## Scenarios covered

| Area | Result |
|---|---|
| Happy path: a telecaller creates a lead (mobile + email + product + source) | PASS: lands on the detail page, stage **Assigned**, own lead (I2) |
| Invalid inputs: empty form, mobile `12345` | Empty form: QA-02. The bad mobile gets "Enter a valid mobile number" |
| Duplicate: same mobile in another format (`09123450001`) / same email in another case | PASS: the §18 panel shows telecaller, counselor, last contact, status, previous enquiries; "Open lead" only when in scope |
| Another telecaller's lead: Add enquiry | PASS: added; the owner's and the manager's Activity show "New enquiry … · QA Caller 2 · Referral" |
| Add enquiry without a source | PASS: "Choose the lead source first." |
| Duplicate submission (double click) | QA-04 |
| Manager New lead | PASS: "waits in its team's unassigned queue" wording; same form |
| Unauthorised / wrong role | PASS: signed out → telecaller sign-in redirect; a counselor gets "Access unavailable" on both pages |
| Desktop 1366 / tablet 820 / mobile 390 layout | No horizontal scroll; QA-01 (desktop), QA-05 (mobile) |
| Console / network | No unexpected errors; the only failed request is the intended 409 of a duplicate create |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Low | Telecaller, New lead (desktop) | Open the form | A readable priority choice | The option text with its help was cut off ("Warm – Interested but need") | Fixed: the options are Hot/Warm/Cold, and the chosen level's help shows under the select |
| QA-02 | Medium | Telecaller, New lead | Click Create lead on an empty form | Says which fields are missing; sends nothing | "Field required; Field required; …" from a 422 | Fixed: "Enter the student name, mobile number, product interest and lead source." No request is sent |
| QA-03 | Low | Telecaller, New lead | Match a mobile, then change it to `12` and leave the field | The panel clears | The old match stayed | Fixed: an unusable or unmatched value clears the panel |
| QA-04 | Medium | Telecaller, duplicate panel | Double-click "Add enquiry to this lead" | One enquiry | Two identical enquiry rows (seen in Activity); the button stayed live | Fixed: one request per click burst; the button then reads "Enquiry added" (disabled). Create lead is guarded the same way |
| QA-05 | Medium | Telecaller, New lead (390 px) | Type a known mobile and leave the field | The warning is visible | The panel rendered below the form (heading at y≈1755 in an 844 px viewport) | Fixed: the panel renders above the form (y≈304), and a refused create focuses its heading |

All five were fixed test-first (`tests/components/NewLeadForm.test.tsx`, QA-01…05) and re-verified in the browser at 390 px.

## Re-test after merging tel-007 (main @ `6a3e7722`)

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-06 | Medium | Manager, New lead | Create a lead; tel-007's round robin gives it to an IT telecaller outside the manager's reports | A confirmation of the new lead | The form opened the lead, which then read "Lead not found" | Fixed: the create reply carries `in_scope`; when it is false the form says "Lead LD-… created and assigned to …" and clears for the next caller |
