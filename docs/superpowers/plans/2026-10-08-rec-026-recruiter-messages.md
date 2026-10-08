# rec-026 — implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-026-recruiter-messages-design.md`. TDD per task: write the failing test (RED), make it pass
(GREEN), then tidy (REFACTOR). The lite tests run in the `api-test` / `web-test` containers.

## Tasks

1. **Model and migration.**
   - Add `REC_WHATSAPP_KINDS`, `REC_EMAIL_KINDS`, `RECRUITER_MESSAGE_CHECKS`, `RecruiterMessageTemplate` and `RecruiterMessage` to
     `models.py` (an append-only block).
   - Add `0119_recruiter_messages`: guarded create, idempotent seed of 12 templates (inserting only a missing channel+name), and a
     downgrade that refuses while any message exists or any template differs from its seed.
   - Test: `test_rec_026_migration.py` (the chain, the checks equal the models', the round trip, the downgrade refusal).
2. **Templates API.**
   - Add the schemas `RecTemplateCreate/Update/Out/Page/Preview`.
   - Add placeholders, `check_template`, `render` and `template_out` in `services/recruiter_messages.py`.
   - Add the routes in `api/recruiter_messages.py`.
   - Tests:
     - AC1, the 12 seeds render;
     - the role matrix (manager and `super_admin` write; a recruiter reads only active rows; `hr_team`, BDM and telecaller → 403);
     - an unknown placeholder → 422;
     - a duplicate name → 409;
     - the channel is fixed;
     - the preview.
3. **Send and list.**
   - Add the schemas `RecMessageCreate` (WhatsApp / email, party xor validator).
   - In the service, add:
     - `load_party` (the scope and lock);
     - `render_for`;
     - `create` (the error order in spec §3);
     - `page`, `one` and `contact_last`.
   - Add the routes for render, POST, and the company and candidate lists.
   - Tests:
     - AC3 (WhatsApp is logged);
     - AC2 queue and publish after the commit;
     - no number or address → 409 (the candidate with no email);
     - SMTP unset → 503;
     - inactive, archived → 409;
     - scope → 404;
     - a manager sending to a contact → 403;
     - a manager sending to a candidate is allowed;
     - `hr_team` reads candidate messages;
     - the caps;
     - the audit and logs carry no body.
4. **Delivery.**
   - Add `notifications/recruiter_email.py` (claim, send with `lead_email._send`, record, sweep).
   - Add `dispatch.enqueue_recruiter_email` and `_publish_recruiter_email`.
   - Add the worker tasks and a beat entry.
   - Add the conftest fixture `recruiter_emails_enqueued`.
   - Test `test_rec_026_delivery.py`: sent once to the party's address with the recruiter's reply-to; retry; permanent failure; address
     removed; sweep.
5. **Contact and candidate outputs.**
   - Add `whatsapp_to` to the contacts list and to `CandidateDetail`.
   - Compute `last_contacted_at` from messages (MS10).
   - Tests are in task 3's file.
6. **Web composers.**
   - Add the `target` prop.
   - Add `leadTarget` in `lib/telecallerMessages.ts`.
   - Update `LeadMessages`.
   - Rerun the composer and `LeadMessages` vitest files.
7. **Web recruiter.**
   - Add `lib/recruiterMessages.ts` and `RecruiterMessages.tsx`, used on the company page and the candidate page.
   - Add `RecruiterTemplatesPanel.tsx`, `RecruiterTemplateRow.tsx` and the `/recruiter/manager/templates` page.
   - Add the nav entry.
   - Vitest for the lib and the components.
8. **e2e** `rec-026-messages.spec.ts` and browser QA.
9. **Docs:** DEC-SCOPE-134 in the register, API §12BB, RBAC §2.60, DATA_MODEL, SCREEN_CATALOG and the backlog status.

## Phase 3 review notes (applied to the tasks above)

- **API.**
  - A template body is a typed pydantic model with `extra="forbid"`.
  - POST `/recruiter/messages` returns 201 and is not idempotent, as tel-013.
  - The list endpoints are paged (`limit` / `offset`).
  - A render for an inactive template → 404.
  - The PATCH re-checks the merged row.
  - The transaction is: lock the party, count the cap under the lock, insert, audit, commit, then publish. The worker's claim is an atomic
    UPDATE…RETURNING, so a duplicate publish never double-sends.
- **Security.**
  - IDOR: every read and write resolves the party's scope first; a contact is checked against its company (`company_id` comes from the
    contact row, never from the client).
  - Role escalation: template writes are limited to the manager and `super_admin`.
  - Header injection: the subject's CR/LF become spaces (`_one_line`).
  - XSS: the email HTML escapes everything (the existing mailer), and the web renders text only.
  - Email injection: the recipient is always the party's stored address, never a request field.
  - Logs and audit carry no body, subject or address.
  - The caps are the rate limit.
  - Secrets: none.
- **Frontend.**
  - Reuse the composers and the library list.
  - Buttons are disabled with a visible reason (`aria-describedby`).
  - There are loading, empty and error (Retry) states, and a `role=status` notice.
  - Focus returns to the opener.
  - Cards (not tables) for messages, so the layout works on a phone.
