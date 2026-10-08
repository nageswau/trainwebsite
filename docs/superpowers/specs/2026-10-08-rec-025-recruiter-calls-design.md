# rec-025 — Recruiter call logging (design)

- **Feature:** rec-025 (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-025), EVID-018 §19 "📞 Calls: Call history and notes" (R13).
- **Decision:** `DEC-SCOPE-132` (CA1–CA9 are recommended defaults, **UNVERIFIED**; the owner said "proceed with recommended answers").
- **Numbering (checked on `origin/main` @ `804853c1`):** migration `0117_recruiter_calls` (after `0116_recruiter_follow_ups`), API §12AZ,
  RBAC §2.58.
- **Dependency:** rec-024 is MERGED (PR #168 @ `e92e2094`).

## Understanding

Recruiters phone company contacts (HR, TA, hiring managers) and candidates. They need to see the call history and notes on the company
and the candidate. A call to a contact can schedule the next follow-up (rec-024), and it updates the contact's "Last contacted" (rec-004
C6). Calls are manual, beside a `tel:` link (R13, the telecaller pattern). The source names no outcome list, so the list below is a
default.

## 1. Decisions (UNVERIFIED defaults)

| ID | Decision |
|---|---|
| CA1 | **Outcomes** are a fixed list in code, not an admin catalogue. They are `connected`, `call_back_requested`, `busy`, `no_answer`, `switched_off` and `wrong_number`. The first two count as "connected". |
| CA2 | **Party.** A call is on exactly one of a company contact or a candidate (`CHECK`). A contact call also stores the contact's `company_id`, so the company's scope and its call list need no join through contacts. |
| CA3 | **Who.** A contact call follows the company: it is read by whoever has the company in scope (rec-003), and logged by whoever has the company's `can_edit` (the assigned recruiter or `super_admin`). An archived company → 409. An inactive contact → 409. A candidate call follows R11: `candidates.WRITERS` log it and `READERS` (plus `hr_team`) read it. An archived candidate → 409. |
| CA4 | **Same-day edit and delete** (the tel-010 CL4 idiom). Only the person who logged the call can change it, and only on the call's IST day, while they still have write rights on the party. Editing yesterday's call → 409. The outcome is locked: delete and log again. Editable fields are the time (moved only within today), duration, direction and notes. |
| CA5 | **Time.** `occurred_at` defaults to now. It may not be in the future (60 s tolerance) and may go up to 7 days back. These are `lead_calls.check_time`'s rules, reused. |
| CA6 | **Next follow-up.** Optional and for contact calls only. It is rec-024's create body (`due_at`, `reason`, `notes`), written through `recruiter_follow_ups.create` with `contact_id` set, in the same transaction, so a refusal there (past due, the cap) rolls the whole call back. On a candidate call → 422, because rec-024 follow-ups belong to a company. Deleting a call keeps its follow-up. |
| CA7 | **Last contacted.** A contact's `last_contacted_at` is the latest `occurred_at` of its calls, computed on read in one grouped query. rec-026 and rec-028 add their sources later. |
| CA8 | **Fields.** Direction is `outgoing` or `incoming` (default outgoing). `duration_seconds` is optional, 0–14400. Notes are optional, up to 2000 characters, multi-line. |
| CA9 | **Cap.** 300 calls per caller per IST day, an abuse bound (tel-010 D9). |

## 2. Data — `recruiter_calls` (migration 0117)

The columns are:
- `id`
- `company_id` and `contact_id`, FKs, nullable together.
- `candidate_id`, FK, nullable.
- `caller_user_id`, FK.
- `occurred_at`
- `duration_seconds` (nullable)
- `direction`
- `outcome`
- `notes` (Text, nullable)
- `created_at` and `updated_at`

All FKs are `ON DELETE RESTRICT`.

The checks are:
- the direction is in its list;
- the outcome is in its list;
- the party: `(contact_id IS NULL) = (company_id IS NULL) AND (contact_id IS NULL) <> (candidate_id IS NULL)`;
- the duration is null or between 0 and 14400.

The indexes are:
- `(company_id, occurred_at)`
- `(contact_id, occurred_at)`
- `(candidate_id, occurred_at)`
- `(caller_user_id, occurred_at)`

It is a new table only. The upgrade is guarded (0110's idiom). The downgrade refuses while any call exists.

## 3. API (§12AZ)

| Method | Path | Notes |
|---|---|---|
| POST | `/recruiter/calls` | Body: `contact_id` xor `candidate_id`, `occurred_at?`, `duration_seconds?`, `direction`, `outcome`, `notes?`, `next_follow_up?`. Returns 201 `{call, follow_up_id}`. Not idempotent. |
| GET | `/recruiter/companies/{id}/calls` | The company's contact calls, newest first, paginated. The scope is the company's (404). |
| GET | `/recruiter/candidates/{id}/calls` | The candidate's calls, newest first, paginated. Readers only (403), pool (404). |
| PATCH | `/recruiter/calls/{id}` | CA4. Returns the call. |
| DELETE | `/recruiter/calls/{id}` | CA4. Returns 204. |

Result of QA: QA-01 (cosmetic) -- the form grid aligns items to the start so a select is not stretched.

The error order on a write is:
1. role (403);
2. party in scope (404);
3. lock the party (the company row or the candidate row);
4. write right (403), then archived or inactive (409);
5. caller and same day (403 / 409);
6. validation (422);
7. write, audit, commit, log.

Each call in a response carries:
- `id`, `kind` (`contact` or `candidate`), `company_id`, `contact` (`{id, name}` or null) and `candidate` (`{id, name, code}` or null)
- `occurred_at`, `duration_seconds`, `direction`, `outcome`, `outcome_label`, `connected` and `notes`
- `caller {id, full_name}`, `created_at` and `can_change`

Audit rows are `recruiter_call.create`, `recruiter_call.update` and `recruiter_call.delete`. They carry ids, the outcome and field names, and never notes.

## 4. Web

- `lib/recruiterCalls.ts` holds the types, outcomes, URLs, type guards and `telHref`.
- `RecruiterCallForm.tsx` logs or edits a call. It is modelled on `CallLogForm` but smaller (no lead stage rules), and it reuses the rec-024 reasons. For a contact call it shows a contact picker (active contacts) and an optional "Add a next follow-up".
- `RecruiterCalls.tsx` is the list section ("Calls"), with Log call, and Edit / Delete when `can_change`. It handles the loading, empty and error (Retry) states, and it is used on the company page and the candidate page.
- On the company page, a logged call re-keys the contacts (Last contacted) and the follow-ups (when one was created).
- Each contact's mobile becomes a `tel:` link.
- On the candidate detail page, the mobile becomes a `tel:` link and a Calls section is added. Writers log while the candidate is not archived.

## 5. Tests

- **pytest** `test_rec_025_calls.py`:
  - AC1: last contacted;
  - AC2: the follow-up is created and is the contact's next one;
  - AC3: same day 409;
  - the party xor 422;
  - the candidate follow-up 422;
  - an archived company 409, an inactive contact 409 and an archived candidate 409;
  - out of scope 404, a manager or BDM log 403 and `hr_team` reads candidate calls;
  - another recruiter's PATCH 403;
  - a future time 422;
  - the delete keeps the follow-up;
  - the audit carries no notes.
- **pytest** `test_rec_025_migration.py`: the checks equal the models'.
- **vitest:** the lib and the form/list behaviour.
- **Playwright** `rec-025-calls.spec.ts`: log a call on a contact with a follow-up, then Last contacted; a candidate call.

## 6. Risks

- The shared `models.py` and `schemas.py` are append-only.
- The contacts list output changes only `last_contacted_at`, from null to a value.
- The route-inventory and RBAC tests may need rows for the new routes.
