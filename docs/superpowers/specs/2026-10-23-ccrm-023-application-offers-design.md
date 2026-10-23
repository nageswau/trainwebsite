# ccrm-023 — Offer records with history (counselor on all applications) — design

Date 2026-10-23. Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § `ccrm-023` (source §9, §15; CC4, CC5). Folds in `nehn-001`
(`docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md`). Decision `DEC-SCOPE-245` (amends `DEC-SCOPE-056`). Migration
`0170_application_offers` (merges main's two `0169` heads). API §12EX. RBAC §2.160. Numbers are rechecked before the PR.

## 1. Owner answers (2026-10-23, clarifying prompt)

| ID | Answer |
| --- | --- |
| OF1 | `nehn-001` is not on main → fold its predicate fix into ccrm-023. |
| OF2 | Every backlog field. The offer letter is **required on the counselor route only**; the agency `PUT …/offer` keeps it optional (no contract break). Backfilled offers may have no letter. |
| OF3 | Types `conditional`, `unconditional`, `pathway`, `other`. Unconditional → sub-status `unconditional_offer`; the other three → `conditional_offer` (agency PUT too). The mirrored `offer_type` CHECK widens to the four types. |
| OF4 | One `POST …/offers/{id}/withdraw` (`withdrawn_by_university` or `expired`, reason required). Closing the current offer clears the mirror columns; the stage stays; an offer sub-status is cleared. No expiry job (ccrm-025 owns deadline expiry). |

## 2. Existing behaviour (verified on `a97dd75f`)

- One offer per application in columns `offer_type` (conditional/unconditional), `offer_date`, `offer_deadline`, `offer_conditions`,
  `offer_document_id`. Only the agency writes them: `PUT /workflows/overseas/agent/crm/applications/{id}/offer` (AGN-010). The PUT
  replaces the offer in place; the earlier values survive only in the status-history note.
- The agency PUT moves a pre-offer stage to `offer`, but the model's `@validates("status")` (ccrm-014 SS3) then leaves `sub_status`
  NULL, so no offer sub-status is set.
- The counselor has no offer route, no document upload route, and no application detail page. The counselor works from the
  "Evaluate Applications" cards (`CounselorEvaluationPanel.tsx`).
- `nehn-001`: the student dashboard Offers tile and the student and university-rep "Offer letters" lists still use
  `status in {"offer_received","accepted"}` (`services/portal.py:592, 663, 1085`). So an offer recorded through the normal path never
  shows there.

## 3. Design

### 3.1 Data — `application_offers` (new)

| Column | Type | Rule |
| --- | --- | --- |
| id | uuid PK | |
| application_id | FK overseas_applications, not null | indexed with created_at |
| offer_type | varchar(20) | CHECK in the four types |
| issue_date | date, not null | not in the future (schema) |
| offer_deadline | date null | ≥ issue_date (schema) |
| conditions | text null | ≤ 2000, cleaned free text |
| currency | char(3) null | required iff any amount is set (CHECK) |
| tuition_amount, scholarship_amount, deposit_amount | numeric(12,2) null | ≥ 0 (CHECK). Scholarship is recorded only when confirmed (form hint) |
| deposit_deadline | date null | ≥ issue_date (schema) |
| offer_document_id | FK student_documents ON DELETE SET NULL, null | |
| status | varchar(30) default `active` | CHECK active / superseded / withdrawn_by_university / expired |
| status_reason | text null | required for withdrawn_by_university / expired (CHECK) |
| recorded_by_id, closed_by_id | FK users null | recorded_by is NULL on backfilled rows |
| closed_at | timestamptz null | |
| created_at, updated_at | TimestampMixin | |

A partial unique index `uq_application_offers_active (application_id) WHERE status = 'active'` makes "one current offer" a database
rule. Writers also hold the application row lock, so concurrent saves queue up and the last one wins (CC5).

Migration `0170`: create the table, widen `ck_overseas_applications_offer_type` to the four types, and backfill one `active` row per
application whose `offer_type` is set, from the columns. The steps are guarded (0001 builds from models). The downgrade drops the table
and restores the 2-type CHECK; it fails loudly if a pathway/other value is present, which is the honest behaviour.

### 3.2 Mirror

The current (`active`) offer is copied to `offer_type`, `offer_date` (= issue_date), `offer_deadline`, `offer_conditions` and
`offer_document_id`. Agency routes, `counts_as_offer`, the dashboards, management and the deadline reminders keep reading those columns
unchanged. Closing the current offer sets all five to NULL. Only `services/application_offers.py` writes the mirror.

### 3.3 Service `services/application_offers.py` (no commits)

- `record(db, user, app, values) -> (offer, superseded)`: marks the active row `superseded`, inserts the new row and mirrors it.
- `apply_stage(app)`: a pre-offer stage → `offer` (forward rule via `check_transition`). If the stage is then `offer`, sets the
  type's sub-status (OF3). A later stage is untouched.
- `close(user, app, offer, status, reason)`: closes the active offer, clears the mirror, and clears an offer-stage sub-status.
- `views(db, app)`: newest first, with the recorder's name and the letter's `{id, name}` (never `file_url`).

### 3.4 API

| Route | Roles | Behaviour |
| --- | --- | --- |
| `GET /workflows/overseas/applications/{id}/offers` | counselor (own), overseas_admin, overseas_student (own), agent (scope) — `_assigned_application` | `{"offers": [...], "offer_letters": [...]}`. Letters (this application's "Offer letter" documents, max 20) go to counselor/admin only. |
| `POST /workflows/overseas/applications/{id}/offer-letters` (multipart `file`) | counselor (own), overseas_admin | AGN-009 `read_upload`/`store` (PDF or image, sniffed). Creates an application-attached "Offer letter" document owned like the application (student account and/or agency record). An application with no student or agency owner (school-bridged) → 422. Withdrawn/archived → 409. `201 {"document": {id, name}}`. |
| `POST /workflows/overseas/applications/{id}/offers` | counselor (own), overseas_admin | Body `ApplicationOfferCreate` (`offer_document_id` required; extra keys 422). The letter must be this application's "Offer letter" (422). Withdrawn/archived → 409. Identical to the active offer → `200 {"changed": false}`, nothing written (retry safe). Otherwise: record, apply stage, one history row (from/to status and sub-status, note "Offer recorded: …"), audit `overseas.application.offer`, student notified, the agency told (CC5). `201`. |
| `POST /workflows/overseas/applications/{id}/offers/{offer_id}/withdraw` | counselor (own), overseas_admin | Body `{status: withdrawn_by_university\|expired, reason}`. An offer of another application → 404. Not active → 409. Writes the history row and audit `overseas.application.offer_close`, and notifies the student and the agency. `200`. |
| Agency `PUT …/agent/crm/applications/{id}/offer` | unchanged | Same contract. A real change now writes an `application_offers` row through `record` (superseding the previous one) and sets the OF3 sub-status. The history row carries from/to sub-status. The counselor is told (CC5) instead of the stage-only notice. |
| Agency `PATCH …/agent/crm/applications/{id}` | unchanged | An `offer_deadline` change while an offer is active records a superseding row with the new deadline (nothing overwritten). |

The other side is notified through a new `agent_notifications.offer_changed(db, app, actor, title)`. It shares its recipient rule with
`sub_status_changed`: the counselor when the agency acted, otherwise the AGN-017 recipients.

### 3.5 nehn-001 (folded in)

`portal.py`: the student dashboard Offers tile, the student Offer letters list and the university-rep Offer letters list use
`counts_as_offer(a)` (the AGN-010 O5 predicate). The `offer_letter_url` rule stays on both lists. The student list gains "Offer type"
and "Offer deadline" columns from the mirror.

### 3.6 Web

- `lib/applicationOffers.ts`: types, labels and URLs.
- `components/ApplicationOffersPanel.tsx`: opened from an "Offers" toggle on each counselor card. It shows:
  - the current offer and the history (status badge, type, dates, amounts, letter download, recorded by, reason);
  - "Record offer": type radios, issue date, deadline, conditions (not for unconditional), currency and amounts, deposit deadline, and
    an offer letter (pick an uploaded one or upload a file — the upload happens first, then the offer is posted);
  - "Close offer" on the current one: status and reason.

  It handles loading, empty and error states, uses a same-tick double-submit guard, and puts labels on every input.
- `lib/agentApplications.ts`: a display label map for all four types, so the agency detail shows a counselor's pathway/other offer.
  The agency form's radios stay at two.

### 3.7 Non-goals

Offer conditions table (ccrm-024), student decision and deposit records (ccrm-025), automatic expiry, a student-facing offer page
(nehn-033), a counselor application detail page (ccrm-009), and agency-side offer history UI.

## 4. Acceptance criteria

1. A counselor records an offer on their own direct or agency application. A row is created, the mirror is set, the stage moves to
   `offer` if earlier, and the sub-status is conditional/unconditional per OF3.
2. A second offer supersedes the first; both rows remain.
3. The counselor route without an offer letter → 422. A letter from another application → 422.
4. An agent's PUT writes a row and the sub-status, and the counselor is notified. A counselor's write notifies the agency (CC5).
5. Withdraw/expire needs a reason, clears the mirror, keeps the stage, and clears the offer sub-status. Closing a non-active offer → 409.
6. Another counselor → 403. university_rep POST → 403. The student can GET their own offers; another student → 403.
7. Backfill: an existing column offer becomes one active row.
8. nehn-001 ACs 1–4 (offer stage counts; later stages count; legacy values count; withdrawn before offer does not).
9. Appendix B: "University B issues a conditional offer" — offer, conditions and deadline recorded, and the counselor alerted (agency
   path) / the student notified.

## 5. Risks

Shared state machine (stage/sub-status); the AGN-010 tests (history notes, notices); management funnel counts (unchanged columns); the
agent dashboard parity test.
