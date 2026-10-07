# tel-014 — Email to a lead: exploratory QA (2026-10-07)

## Setup

- **Stack:** an isolated `tel014` stack (web `:3114`, API `:8114`, with worker and beat) built from `feature/tel-014`.
- **Mail:** SMTP is a local Mailpit sink (`:8214`, chaos mode on), so nothing leaves the machine.
- **Browser:** an isolated Edge profile driven over CDP (Browser Use) at 1280, 768 and 375 px. Playwright `tel-014-email.spec.ts` (both
  tests, including `@external`) and `tel-013-whatsapp.spec.ts` ran against the same stack.
- **Accounts:** a telecaller ("Asha Rao") and their manager, both created through the admin API.
- **Leads:** a normal lead, a long-name and long-address lead, a closed lead, a handed-over lead and a lead entered with no email (tel-005 I1).

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Evidence | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | High | telecaller / lead page | Create a public enquiry (this queues the PUB-002 CRM sync on the worker), then send an email to a lead | The email is delivered within seconds | The email task crashed with `RuntimeError … attached to a different loop` and the row stayed "Email sending" until the 30-minute sweeper | Worker log `celery.app.trace … deliver_lead_email_task … raised unexpected: RuntimeError`; Playwright `@external` failed on its second email | **Fixed**: `sync_enquiry_to_crm_task` ran a bare `asyncio.run` and left pooled connections on its closed loop; it now uses `_run_with_fresh_pool` like every other task. Regression test `test_a_crm_sync_run_leaves_no_connection_that_breaks_the_next_email_task` (RED → GREEN); e2e rerun green, 0 loop errors in the worker log |

No other defect was found.

## Scenarios checked

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: the header "Email" opens the composer with focus on Template. The template renders subject and body with the lead's name; both are edited; Send | Pass. The row is shown as "Email sending – …", then "Email sent – …" within about 5 s (polling). Mailpit has From `Asha Rao via EduSphere <noreply@…>`, Reply-To the telecaller and the edited subject. The HTML escapes `<b>` / `&`, and the brochure URL is a link with `&amp;` |
| 2 | Invalid input: whitespace-only subject or body; over-long fields | Pass. Send stays disabled; `maxLength` is 200 / 5000; the API's 422s are covered by pytest |
| 3 | Duplicate submission: Send activated three times quickly | Pass. One row and one email |
| 4 | Keyboard: Enter in Subject submits; Cancel returns focus to "Send email" | Pass |
| 5 | Refresh after sending | Pass. Rows and statuses persist |
| 6 | Lead with no email (AC3) | Pass. "Send email" is disabled with "No email address on this lead."; no header "Email" button |
| 7 | Closed lead / handed-over lead | Pass. No send controls |
| 8 | Recipient rejected by the server (Mailpit 550) (AC2) | Pass. "Email failed – …" with "This email was not delivered. Check the lead's email address and send it again."; the worker log carries only ids and `SMTPRecipientsRefused` |
| 9 | Mail server down (transient) | Pass. "Email delayed – …" with "It will be retried automatically"; the worker retried after 60 s, and after a refresh the row reads "Email sent" |
| 10 | Daily cap: 100 emails today | Pass. 429 "You've sent 100 emails today" shown in the composer; the text is kept |
| 11 | SMTP not configured (`SMTP_FROM_EMAIL` unset) | Pass. 503 "Email is not set up. Ask an administrator to configure SMTP." in the composer; nothing stored |
| 12 | Manager (incorrect role for sending) | Pass. Sees the email rows and statuses with no buttons; API POST answers 403 |
| 13 | Signed out | Pass. The page redirects to `/telecaller/sign-in?next=…`; API 401 |
| 14 | Layout at 375 / 768 / 1280 px with a 180-character subject and an unbroken 230-character word | Pass. No side scroll; the text wraps; the header buttons wrap |
| 15 | Console errors and failed requests during the run | None (only the expected 4xx/5xx of the refusal scenarios) |
| 16 | tel-013 WhatsApp regression (Playwright) | Pass |

## Notes (by design, not defects)

- A template placeholder with no value renders empty. For example, a lead with no product gives "about .". This is tel-013 D5,
  unchanged here.
- A "delayed" (retrying) row doesn't refresh on its own, because its retries come minutes apart (spec §5). A reload shows the outcome.
- Pre-existing and out of scope: `test_tel_012_migration::test_seed_round_trip_and_idempotence` fails identically on untouched `origin/main`.
  In its throwaway database, 0001 builds tel-013's `lead_messages`, whose FK blocks the downgrade of `tel_message_templates`.
