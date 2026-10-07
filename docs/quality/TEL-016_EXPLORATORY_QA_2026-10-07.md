# tel-016 — Exploratory browser QA (2026-10-07)

**Stack:** `tel016` (web :3096, API :8096), branch `feature/tel-016`, with the images rebuilt from the branch (the web image's `next build`
passed).

**Browser:** an isolated Edge 154 over CDP :9396, driven by browser-use for the first checks (sign-in, the lead page, the booking form, the
select state and the leave guard). The browser-use daemon then kept timing out on navigation and evaluation in this Edge session, so the rest
of the walk ran as throwaway Playwright scripts (Chromium) against the same stack. Those scripts were not committed. They logged each
check, every 4xx/5xx response and every console error, and took screenshots at 1280, 768 and 375 px. The committed spec
`tel-016-lead-appointments.spec.ts` covers the main flow.

**Data:**
- one telecaller manager and one IT telecaller (reporting to that manager)
- two IT counselors and one overseas counselor
- IT leads with a Digital Marketing product

## Scenarios

| # | Area | Role | Result |
|---|---|---|---|
| 1 | Happy path: IT course counselling, IT counselor, tomorrow, Online + link, location, purpose | telecaller | Pass. "Appointment CAP-… booked with …", the card shows Scheduled, the stage line shows Counselling Scheduled at once (AC2), the activity lists "→ Counselling Scheduled", and "Book counselling" is hidden while the appointment is open (AP5) |
| 2 | Required fields: empty submit | telecaller | Pass. Three in-place messages and "Check the highlighted fields."; the first field is focused; nothing sent. **QA-01** found (the error stayed after the field was fixed); fixed and re-verified |
| 3 | Invalid: past time | telecaller | Pass. API `422` "Choose a time in the future" on the date field, which is focused |
| 4 | Invalid: `javascript:alert(1)` link | telecaller | Pass. "Meeting link must start with http:// or https://" on the link field, focused; never linked (component test) |
| 5 | Duplicate submission: double-click Book | telecaller | Pass. One appointment (the button disables while booking; one-open-per-lead is the backstop) |
| 6 | Clash: a second lead with the same counselor at the same time | telecaller | Pass. "The counselor already has an appointment at this time. Busy: <time> IST." and the date field marked busy (AP1); the same time with the other counselor books |
| 7 | Refresh | telecaller | Pass. The card and status persist; the transient notice is gone |
| 8 | Reschedule | telecaller | Pass. The new-time field is focused; the status becomes Rescheduled; the history keeps both times |
| 9 | Cancel with no reason | telecaller | Pass. "Add a reason for cancelling.", focused, nothing sent |
| 10 | Manager view of the same lead | telecaller_manager | Pass. No "Book counselling" button and no action buttons (AP2 read only) |
| 11 | Counselor Appointments page | IT counselor | Pass. Nav shows Dashboard / Leads / Appointments (AP14); the lead name, Lead ID, mobile and email appear (AP13); no overseas student forms (WorkflowPanel guard) |
| 12 | Confirm; status filter | IT counselor | Pass. Confirmed; "Completed" filter shows "No completed lead appointments." |
| 13 | Complete after the start (start moved 2 h back in the DB) | IT counselor | Pass. Completed; the lead's stage is `counselling_completed`; history Booked → Confirmed → Completed |
| 14 | Wrong role: counselor opens a telecaller lead page | IT counselor | Pass. "Access unavailable — Telecaller role required" |
| 15 | Wrong role: telecaller opens `/it/counselor/appointments` | telecaller | Pass. "Access unavailable — Role/division mismatch" |
| 16 | Overseas counselor Appointments | overseas counselor | Pass. "Lead appointments" panel above the unchanged "Student appointments" table and its Schedule / Update forms |
| 17 | Layout at 1280 / 768 / 375 px (lead page and counselor page) | both | Pass. No sideways scroll; the card's fields stack at 375 px |
| 18 | Leave guard: unsaved booking, then navigation | telecaller | Pass. The browser's leave prompt appears (browser-use) |
| 19 | Server error on the options read | telecaller | Pass (component test, `500` mocked): "Unable to load the booking form." with Try again. The loading lines ("Loading the booking form…", "Loading appointments…") are in the code but not asserted by a test |
| 20 | Console / network | all | Only the deliberate `4xx` responses (422, 409) and the browser's matching "Failed to load resource" lines. No page errors, broken images or unexpected redirects |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Low | telecaller, lead detail → Book counselling | Submit the empty form, then choose a type | "Choose the appointment type." clears | The message and `aria-invalid` stayed until the next submit | **Fixed** (`BookCounsellingForm` clears a field's error on change; the card clears its error as the reason or the time is typed); covered by `BookCounsellingForm.test.tsx` and `LeadAppointmentCard.test.tsx` |

## Known, not tel-016

- `tests/lib/dateZoneSweep.test.ts` already fails on `main`. It lists 24 `formatDate` calls without a zone in existing telecaller, BDM and agent components. None is in a file this item added; the two in `LeadDetailPanel.tsx` are existing lines that moved down.
- `apps/api/app/services/portal.py` has an import-order lint finding (`I001`) that predates this item.
