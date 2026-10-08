# rec-025 Recruiter Call Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native; chosen by the owner's "proceed" instruction).

**Goal:** Log calls on company contacts and candidates. A contact call can schedule a rec-024 follow-up and updates the contact's Last
contacted. Calls can be edited or deleted on the same IST day.

**Architecture:**
- One new table, `recruiter_calls`, whose party is exactly one of a contact (with `company_id`) or a candidate.
- A functions-only service, `services/recruiter_calls.py`, reuses rec-003 `load_scoped` / `require`, rec-009 `candidates.load` /
  `require_writer`, rec-024 `recruiter_follow_ups.create`, and tel-010 `lead_calls.check_time`.
- A router, `api/recruiter_calls.py`.
- Web: `lib/recruiterCalls.ts`, `RecruiterCallForm`, and `RecruiterCalls` on the company and candidate pages.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2; Next.js/React, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-08-rec-025-recruiter-calls-design.md`

## Global Constraints
- Numbering: migration `0118_recruiter_calls` (down `0117_job_descriptions`), `DEC-SCOPE-133`, API §12BA, RBAC §2.59.
- Outcomes are `connected`, `call_back_requested`, `busy`, `no_answer`, `switched_off` and `wrong_number`. Directions are `outgoing` and `incoming`.
- Duration is 0–14400 s and optional. Notes are up to 2000 characters. The cap is 300 calls per caller per IST day.
- Audit and logs carry ids, the outcome and field names. They never carry notes.
- Nothing in the service commits. The route owns the transaction.

## Review Focus
1. Both or neither of `contact_id` / `candidate_id` → 422 naming the field. Test this in Task 2.
2. A call on a contact of an archived company → 409, not 403. Test this in Task 2.
3. A recruiter logs on a candidate, then the candidate is archived, then the recruiter edits the call → 409 "Restore this candidate first". Test this in Task 3.
4. A next follow-up with a past due → 422, and no call row is left behind (rollback). Test this in Task 2.
5. A moved time on PATCH lands on yesterday → 422. Test this in Task 3.

---

### Task 1: Model + migration
**Files:** `apps/api/app/models.py` (RECRUITER_CALL_* + `RecruiterCall`), `apps/api/alembic/versions/0118_recruiter_calls.py`,
`apps/api/tests/test_rec_025_migration.py`
- [ ] Write the migration test: the migration's CHECKS equal `models.RECRUITER_CALL_CHECKS`; revision and down_revision. Run it (fails).
- [ ] Add the model and migration. Run it (passes).

### Task 2: Create + lists (AC1, AC2)
**Files:** `schemas.py` (`RecCallCreate`, `RecCallUpdate`), `services/recruiter_calls.py`, `api/recruiter_calls.py`, `main.py`,
`services/recruiter_contacts.py` (`last_contacted_at`), `tests/test_rec_025_calls.py`
**Interfaces (produces):** `svc.create(db, user, payload, now) -> (RecruiterCall, follow_up_id | None)`,
`svc.company_page`, `svc.candidate_page`, `svc.one(db, user, call_id, now) -> dict`, `svc.contact_last(db, company_id) -> dict[UUID, datetime]`.
- [ ] Tests:
  - a connected call with notes → 201, `can_change` true, and the audit has no notes;
  - the contact's `last_contacted_at` is the call time;
  - a next follow-up is created with `contact_id` and is the contact's `next_follow_up_at`;
  - the candidate follow-up 422;
  - xor 422;
  - future 422;
  - a past follow-up 422 with no call row;
  - archived company 409; inactive contact 409; archived candidate 409;
  - another recruiter's company 404; manager log 403; BDM log 403; `hr_team` POST 403 but GET candidate calls 200;
  - the lists are newest first.
- [ ] Implement. Run the tests and make sure they pass.

### Task 3: PATCH / DELETE (AC3)
- [ ] Tests:
  - edit today's call (notes, duration) → 200 with an audit of field names;
  - yesterday's call (stored directly) PATCH and DELETE → 409;
  - another writer → 403;
  - the outcome in PATCH → 422 (extra forbid);
  - the time moved to yesterday → 422;
  - DELETE → 204 and the follow-up stays;
  - a candidate archived after the call → 409.
- [ ] Implement `load_for_write` and `apply_update`. Make the tests pass.

### Task 4: Web lib + components
**Files:** `apps/web/lib/recruiterCalls.ts`, `components/RecruiterCallForm.tsx`, `components/RecruiterCalls.tsx`,
`RecruiterCompanyDetail.tsx`, `RecruiterCompanyContacts.tsx` (`tel:`), `RecruiterCandidateDetail.tsx`, and the tests
`tests/lib/recruiterCalls.test.ts` and `tests/components/RecruiterCalls.test.tsx`.
- [ ] vitest:
  - `telHref` strips spaces and keeps `+`;
  - the guards;
  - the list renders the loading, empty, error/Retry and item states;
  - Edit/Delete appear only when `can_change`;
  - the form posts the body with `contact_id` and a `next_follow_up`;
  - the server's field errors land on their fields.
- [ ] Implement. Run vitest, tsc and eslint.

### Task 5: E2E + docs
- [ ] `apps/web/tests/e2e/rec-025-calls.spec.ts`: log a contact call with a follow-up, then check Last contacted and the follow-up listed; a candidate call; edit.
- [ ] Docs: API_CONTRACT §12BA, RBAC_MATRIX §2.59, DATA_MODEL, PRODUCT_DECISION_REGISTER DEC-SCOPE-133, the backlog status, SCREEN_CATALOG.
