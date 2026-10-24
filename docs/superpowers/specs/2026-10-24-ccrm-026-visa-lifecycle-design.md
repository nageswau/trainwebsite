# ccrm-026 — Visa case: the counselor records the full visa lifecycle (all applications) — Design

Status: built 2026-10-24 on `feature/ccrm-026`. Decision `DEC-SCOPE-254`. Migration `0177_visa_lifecycle`. API `12FG`. RBAC `2.169`.
Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` ccrm-026 (§10 visa tracking, Appendix A statuses, CC2, CC4, CC5). The source spec is
UNVERIFIED; VC1-VC4 are owner answers (2026-10-24), the rest are recommended defaults (NEEDS_CONFIRMATION).

## 1. Owner answers

- **VC1 (CC5 vs V2):** V2 stays. A recorded decision (Approved / Refused / Withdrawn) locks the case for the counselor and the agency.
  Only the Overseas Admin corrects it, with a correction reason (kept in the audit trail). A correction does not reopen the application;
  a refused application is reopened by the ccrm-015 admin reopen.
- **VC2:** the agency keeps its AGN-012 form and fields unchanged and sees the new fields read-only, never the refusal reason.
- **VC3:** the counselor (or admin) may record the decision on an agency case too (supersedes DEC-SCOPE-090 H4 for the decision only).
  Whoever records first locks it (VC1); the other side is notified (CC5).
- **VC4:** Appendix A statuses map onto the existing stages and the ccrm-014 sub-statuses (§3).
- **VC5:** every writer — the AGN-012 agency route too — moves the application forward and closes it as `visa_refused` on a refusal.
  Supersedes `DEC-SCOPE-057` V5 ("the application stage never moves").

## 2. Recommended defaults (NEEDS_CONFIRMATION)

- D1 New route `PATCH /workflows/overseas/visa/{id}/lifecycle`. The legacy `PATCH /workflows/overseas/visa/{id}` keeps its contract
  (stage `status`, checklist, appointment date, reference) and now also keeps `visa_status` in step with the stage it sets.
- D2 Required per status: Appointment Booked needs an appointment date; Submitted needs a submission date; Refused needs a refusal
  reason. A decision without a date is dated today. Dates: interview and expected decision not before submission; decision date not in
  the future and not before submission.
- D3 Outcome evidence is a document already attached to the application (422 otherwise).
- D4 Visa category is free text (no catalogue exists).
- D5 Starting a case with no checklist uses the resolved ccrm-018 `visa` template's item document types; the start form is pre-filled
  from it. No template → free text, as today.
- D6 Notifications: the student on every status change (status label only); the agency on a counselor/admin change of an agency case and
  the assigned counselor on an agency change (CC5, the AGN-017 `_other_side` recipients). Never the refusal reason.
- D7 On hold refuses a status change (it may move the application) but not a field edit. A terminal outcome refuses everything except
  an admin correction on a `visa_refused` application. Enrolled refuses everything (409, as AGN-012 V5).
- D8 The student's visa-status read gains the status label, appointment date/place, submission date, expected decision date and next
  steps. It never carries the refusal reason or the category-free internal fields.

## 3. Status model

`visa_cases.visa_status` (CHECK), in order: `not_started, preparing, appointment_booked, submitted, additional_info_requested,
decision_pending, approved, refused, withdrawn`. `status` (the stage) and `decision` are derived on every write:

| visa_status | stage | decision | application sub-status (forward only) |
|---|---|---|---|
| not_started | checklist | — | — |
| preparing | documentation | — | visa_preparation |
| appointment_booked | interview_prep | — | visa_preparation |
| submitted | tracking | — | visa_applied |
| additional_info_requested | tracking | — | visa_applied |
| decision_pending | tracking | — | visa_decision_pending |
| approved | decision | approved | visa_approved |
| refused | decision | refused | outcome `visa_refused` (ccrm-015) |
| withdrawn | decision | withdrawn | — |

Moves: forward only, except `additional_info_requested` ↔ `decision_pending`; `withdrawn` from any open status. Leaving `not_started`
passes the VISA-001-AC02 checklist gate. A sub-status earlier than the application's stage is skipped (no backward move).
The AGN-012 agency route keeps its stages; a forward stage move there sets that stage's first status and a decision sets the decision
status, so both views agree. A legacy stage write does the same.

## 4. Data (migration 0177)

New nullable columns on `visa_cases`: `readiness_review_date`, `visa_category` (80), `appointment_place` (200),
`expected_decision_date`, `decision_date`, `outcome_document_id` (FK `student_documents`, SET NULL), `refusal_reason` (Text,
restricted), `next_steps` (Text); `visa_status` String(40) NOT NULL server default `not_started` + CHECK. The submission date is the
existing `visa_application_date`; the reference is `tracking_reference`. Backfill: `decision` if set, else from the stage
(checklist→not_started, documentation→preparing, interview_prep→appointment_booked, tracking→submitted, decision→decision_pending,
anything else→not_started). `decision_date` backfilled from `decided_at`. Downgrade drops the columns.

## 5. API

`PATCH /workflows/overseas/visa/{id}/lifecycle` — counselor (own application, direct or agency) and Overseas Admin. Body
`VisaLifecycleUpdate` (extra keys 422): `expected_visa_status` (required; stale → 409), optional `visa_status`, the fields of §4,
`submission_date`, `tracking_reference`, `appointment_date`, `interview_date`, `checklist` (only at `not_started`),
`correction_reason` (required for an admin change of a decided case). Entry: role, `_assigned_application`, bridged entitlement,
application row lock, scope re-check, archived agency record 409, the case row lock. Identical values → 200, nothing written.
Response: the case view.

`GET …/applications/{id}/visa-checklist` gains the lifecycle fields; `refusal_reason` and the application's `documents` (for the
evidence picker) only for counselor/admin; when no case exists, `template` = the resolved visa template (name + items).
`POST /workflows/overseas/visa` uses the template's items when the checklist is empty. The agency detail's `visa` block gains the
non-restricted lifecycle fields read-only.

## 6. Security

Refusal reason: never in audit metadata (field names only), logs, notifications, history notes, the student read or the agency read.
IDOR: every write goes through `_assigned_application` + the locked re-check. Audit `visa.lifecycle` with changed field names,
from/to status and `correction` flag.

## 7. Acceptance (ccrm-026-AC01…AC10)

AC01 counselor records category, readiness date, appointment date+place, submission date, reference, interview, expected decision date,
next steps on a direct application. AC02 same on an agency application; the agency is notified and sees them read-only. AC03 status
moves follow §3 and update the application sub-status. AC04 leaving Not Started needs every checklist item verified. AC05 Refused needs
a reason, writes outcome visa_refused, and the reason reaches no log, audit, student or agency. AC06 a decided case is locked for the
counselor and agency (409); the admin corrects with a reason. AC07 stale `expected_visa_status` → 409. AC08 a visa template pre-fills
the checklist. AC09 the student sees the status label and next steps. AC10 the AGN-012 agency routes and the legacy PATCH keep their
contracts (existing tests pass).
