# pob-005 — Contact status, decision-maker, source/verification and per-contact timeline (plan)

Design: `docs/superpowers/specs/2026-11-05-pob-005-contact-status-design.md` (`DEC-SCOPE-411`).

## Tasks (TDD: each test is written and seen failing first)
1. **Model + migration 0289** — `company_contacts` columns (`is_decision_maker`, `source`, `verified_on`, `status`, `status_changed_at`),
   widened channel CHECK, status/source CHECKs, `ix_company_contacts_email`; `recruiter_messages.replied_at`. Guarded (inspect before add),
   backfilled status; downgrade drops them. Tests: `test_pob_005_migration.py`; narrow rec-004's frozen-check test to 0289's copy.
2. **Contact fields + manual status + duplicate check** — schemas (`RecContactIn/Update`: new fields, `confirm_duplicate`), service
   `recruiter_contacts.add/update/list_out` (+ `follow_up_due`), `check_duplicates`, `set_status`/`advance`. Tests:
   `test_pob_005_contacts.py`.
3. **Automatic moves + Do Not Contact** — hooks in `recruiter_messages.create`, `recruiter_calls.create`, `profile_sharing`,
   `interviews` invite, `recruiter_meetings.create/update`. Tests: `test_pob_005_status.py`.
4. **Reply** — `POST /recruiter/messages/{id}/reply`; message `out` gains `replied_at`. Tests in `test_pob_005_status.py`; rec-038 matrix row.
5. **Per-contact timeline + follow-ups filter** — `contact_id` query on both; `contact_status` + `message_reply` branches. Tests:
   `test_pob_005_timeline.py`.
6. **Web** — `lib/recruiterContacts.ts` (types, fields, statuses, sources), `RecruiterContactFields` (checkbox/date/select),
   `RecruiterCompanyContacts` (badges, duplicate confirm, Activity disclosure), `RecruiterTimeline` (`contactId`), `lib/recruiterTimeline.ts`
   (new kinds), `MessagesSection` (`itemAction`, `replied_at`), `RecruiterMessages` (Log reply). Vitest:
   `RecruiterContactStatus.test.tsx`; e2e `pob-005-contact-status.spec.ts`.
7. **Docs** — DEC-SCOPE-411, API §12LE, RBAC §2.304, DATA_MODEL, backlog status, RTM rows.

## Review notes (Phase 3)
- **API:** additive fields only; status/source are closed enums (422); the new route is POST (state change) and idempotent on repeat;
  409 for state conflicts (DNC, duplicate), 422 for validation, 404 for out-of-scope (never 403, so existence is not leaked).
- **Security:** every new path goes through rec-003 `load_scoped` + `can_edit`; duplicate matches filtered by `caller_scope` (no name,
  company or id for out-of-scope rows); DNC enforced in the services, not the UI; audit rows carry ids and statuses only (no PII); no new
  logging of addresses. Status move uses the company lock already held by each write path (no race between two writers).
- **Frontend:** reuse `DetailList`, `BdmConfirm`-style inline confirm, `LeadTimeline`; keyboard-reachable disclosure (`aria-expanded`);
  status shown as text badges (not colour only); loading/empty/error from the shared list components.
