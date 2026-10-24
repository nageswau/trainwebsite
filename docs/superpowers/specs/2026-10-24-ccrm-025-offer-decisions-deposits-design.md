# ccrm-025 — Student decision, acceptance and deposits (design)

Status: design, 2026-10-24. Backlog item `ccrm-025` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`). Source class: owner request on an
`UNVERIFIED` spec (see the backlog header). Decision `DEC-SCOPE-255`, migration `0178_offer_decisions_deposits`, API §12FH, RBAC §2.170.
Depends on ccrm-023 (`application_offers`, DEC-SCOPE-245) and ccrm-015 (`application_outcomes`, DEC-SCOPE-244), both merged.

## 1. Owner answers (2026-10-24)

| ID | Question | Answer |
| --- | --- | --- |
| D1 | Several accepted offers for one student at once? | **Allowed, with a warning.** Accepting is never blocked; the response lists the student's other applications whose current offer is accepted, and the panel names them. |
| D2 | Where does the counselor's manual deposit live? | **New table `application_deposit_records`**, one per application, any 3-letter currency (prefilled from the current offer, no conversion). AGN-011 `application_deposits` + Razorpay unchanged. An application that already has an AGN-011 deposit shows it read-only; the counselor cannot add a manual one (409). |
| D3 | "Expired (auto at deadline)" | **Daily beat job (00:10 IST)**: the current offer of an application at stage `offer`, still `considering`, whose `offer_deadline` is before today (India) → decision `expired` and the offer closed `expired` (ccrm-023 OF4: mirror cleared, offer sub-status cleared, stage kept); history row with no actor; counselor, student and (agency) the agency notified. No deadline → never expires. On-hold and closed applications are skipped. |

Defaults taken without a question (recorded as `NEEDS_CONFIRMATION` in the DEC): the receipt document is optional; `paid_on` is required
for a paid status; the agency reads the decision and deposit record through the existing read routes but has no new UI.

## 2. Existing behaviour (verified on main @ e7e2f62c)

- `application_offers` (ccrm-023): one `active` row per application, mirrored onto the application; `services/application_offers.py`
  is its only writer; routes in `api/application_offers.py` (counselor own apps incl. agency, Overseas Admin any; student + agency read).
- Sub-status `offer_accepted` exists under stage `offer` (ccrm-014) but nothing sets it from an offer.
- Outcome `offer_declined` (ccrm-015) is set through `POST …/outcome` (reason required, `another_offer_preferred`), terminal.
- `application_deposits` (AGN-011): agency-only, INR-only, Razorpay; untouched here.
- Bug on main: `schemas.py` defines `_not_future` twice (ccrm-007 at ~1567 shadows the 3-argument one at ~884), so offer, agency
  application, and deposit remit/refund date validators raise `TypeError` → 500. Fixed here (rename the profile helper) because every
  ccrm-025 route depends on it.

## 3. Design

### 3.1 Offer decision (columns on `application_offers`)

- `decision` VARCHAR(20) NOT NULL DEFAULT `'considering'`, CHECK in (`considering`, `accepted`, `declined`, `expired`).
- `decision_date` DATE NULL; `decided_by_id` FK users NULL (NULL for the job). CHECK `(decision = 'considering') = (decision_date IS NULL)`.
- Backfill: existing rows get `considering` (server default).

`POST /workflows/overseas/applications/{id}/offers/{offer_id}/decision`, body `{decision: accepted|declined, decision_date?,
reason?, another_offer_preferred?}` (`extra=forbid`; date defaults to today, not in the future (UTC+1 day rule), not before the issue
date → 422; `reason` required for declined; `another_offer_preferred` only with declined).

- Entry = the offer routes' `_writable` (role, scope, row lock, counselor re-check, closed 409, on hold 409, archived agency 409).
- Offer not this application's → 404; not `active` → 409 "Only the current offer can be decided".
- Same decision again → 200 `changed: false`, nothing written.
- **accepted**: decision + date + decider; at stage `offer` the sub-status becomes `offer_accepted`; a history row "Offer accepted
  (date)"; student + agency (CC5, `offer_changed`) notified; audit `overseas.application.offer_decision`. Response adds
  `other_accepted: [{id, application_code, university}]` (D1) — the same student (`student_id` or `agent_student_id`), other
  applications not closed, whose active offer is accepted.
- **declined**: delegated to `application_outcomes.record` with an `offer_declined` `ApplicationOutcomeSet` (one path for the terminal
  outcome, its event, its history row); the outcome writer sets the active offer's decision to `declined`. The ccrm-015 `/outcome`
  route therefore also records the decision. The CC5 notice is the outcome's.

### 3.2 Expiry job (D3)

`services/application_offers.expire_offers(db, today) -> int` locks matching applications `FOR UPDATE SKIP LOCKED`, sets decision
`expired` (date = today), calls `close(None, app, offer, "expired", "Offer deadline <d> passed without a decision")`, writes a history
row (`changed_by_id` NULL), notifies the counselor and the student, and the agency through `offer_changed(…, actor=None)`. Rerun-safe.
Beat entry `ccrm025-offer-expiry` at 18:40 UTC (00:10 IST).

### 3.3 Manual deposit record (D2)

Table `application_deposit_records`: `id`, `application_id` (FK, unique, CASCADE), `required` bool, `amount` NUMERIC(12,2),
`currency` CHAR(3), `due_date`, `payment_status` (`not_required`, `pending`, `paid_to_university`, `paid_via_edusphere`), `paid_on`,
`receipt_document_id` (FK student_documents SET NULL), `recorded_by_id`, `updated_by_id`, timestamps. CHECKs: status set;
`(payment_status = 'not_required') = NOT required`; required ⇒ amount > 0 and currency; not required ⇒ amount, currency, due date,
paid_on, receipt all NULL; `(paid_on IS NOT NULL) = (payment_status LIKE 'paid%')`.

- `GET …/applications/{id}/deposit` (readers of the offers list): `{record, agency_deposit, prefill, receipts}` — `agency_deposit` is
  the AGN-011 row's `{status, amount, currency, due_date}` or null; `prefill` the active offer's deposit amount/currency/deadline;
  `receipts` (writers only) the application's "Deposit receipt" documents. No `file_url` anywhere.
- `PUT …/applications/{id}/deposit` (writers; `_writable(moves_stage=False)` — on hold allowed): AGN-011 deposit present → 409
  "The agency pays this deposit through EduSphere -- it is shown read-only"; receipt must be a "Deposit receipt" of this application →
  422; identical → 200 `changed: false`; else upsert, history row "Deposit: …", student + agency notified, audit
  `overseas.application.deposit_record` (no amounts in metadata).
- `POST …/applications/{id}/deposit-receipts` upload: the offer-letter upload refactored into one helper taking the document type.

### 3.4 Web

`ApplicationOffersPanel`: the current offer shows its decision ("Considering" / "Accepted on d" / "Declined on d" / "Expired on d");
"Record acceptance" (date) and "Record decline" (date, reason, another offer preferred) forms; after accept the D1 warning is part of
the success message. A new `ApplicationDepositPanel` below the offers: agency deposit read-only, otherwise the record and an
edit form (required yes/no, amount, currency, due date, status, paid on, receipt pick/upload), prefilled from the offer.
Loading / error / empty states and the double-submit guard follow ccrm-023's panel.

## 4. Acceptance (Appendix B "Student accepts University B")

AC1 accept sets decision/date, sub-status `offer_accepted`, history, notices. AC2 decline writes outcome `offer_declined` (terminal),
decision declined. AC3 accepting a second application warns, never blocks. AC4 the job expires a past-deadline undecided offer exactly
once. AC5 counselor records a deposit on a direct application in GBP with a receipt; AC6 agency application with an AGN-011 deposit →
409 and read-only view. AC7 scope: other counselor 403, student/agent cannot write 403, closed 409, on hold refuses decisions but not
deposits. AC8 migration round-trips and stays single-head.
