# ccrm-016 — Status history with author and reason (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` ccrm-016 (spec §14 status history, AC 6 "who changed the status and when", §5 History
tab). Evidence class of the spec: UNVERIFIED; owner answers H1–H3 (2026-10-23) recorded as `DEC-SCOPE-247`. Depends on ccrm-014
(merged PR #303); also reads ccrm-015 outcomes (PR #306) and ccrm-023 offer closes (PR #307).

## Intent

`application_status_history` already stores author and notes, but the counselor / admin / student read
(`GET /workflows/overseas/applications/{id}/status`) omits both, and no row says which outcome it set or why. This item returns author,
notes, reason, sub-status and outcome per row, and shows them on the counselor's application cards and the student's applications.

## Owner answers

- **H1** Add nullable `outcome` and `reason` columns to `application_status_history`. The outcome record / reopen writers, the agency
  withdraw and the offer withdraw/expire fill them. Existing rows are backfilled where certain. `notes` is unchanged.
- **H2** The student sees stage, sub-status, outcome label and time only — no author, notes or reason (ccrm-015 already hides the
  internal reason from the student).
- **H3** UI: a "Status history" toggle on each counselor *Evaluate Applications* card and the student's applications; the agency
  detail gains the outcome label. The student 360 History tab waits for ccrm-009; an admin-table History link is a follow-up.

## Data (migration `0172_status_history_reason`, after ccrm-023's 0171)

- `application_status_history.outcome` String(20) NULL, CHECK in the six outcomes + `cleared`; `reason` Text NULL.
- Backfill (once, only `outcome IS NULL` rows):
  1. a history row written in the same transaction as an `application_outcomes` event (same application, identical `created_at` —
     both default to the transaction's `now()`) takes that event's `outcome` and `reason`;
  2. a remaining row that moved into `withdrawn` (AGN-008 agency withdraw before ccrm-015) takes `outcome = 'withdrawn'` and
     `reason = notes` (O1: the withdraw note is the reason).
  Offer withdraw/expire rows written before this item keep their reason inside `notes` only.
- Downgrade drops both columns.

## API (§12EZ) — additive only

`GET /api/v1/workflows/overseas/applications/{id}/status` (scope unchanged: the student's own, the assigned counselor, the Overseas
Admin): each `history` row gains `outcome`, `outcome_label` and `created_at` (alias of the existing `changed_at`); for staff also
`notes`, `reason`, `changed_by` (author full name, `null` when the user is gone). Rows are ordered `created_at, id`. The student's rows
never carry the staff fields — filtered on the server, not in the UI.

`GET /api/v1/agent/applications/{id}` `history` rows gain `outcome`, `outcome_label`, `reason` (it already returns `notes` and
`changed_by`). One helper builds both reads (`services/agent_applications.status_history`).

No new endpoints, no new write fields, no change to who may read.

## UI

- `ApplicationStatusHistory` component: loads the status route, shows loading / error with "Try again" / empty states, and an ordered
  list `From → To (sub-status)`, outcome badge, `· author · local time`, then notes (or "Reason: …" when a row has a reason but no
  notes). Text only (React escapes it).
- Counselor *Evaluate Applications* card: "Status history" / "Hide status history" toggle (`aria-expanded`), any application state.
- Student *Apply to a University* panel: its inline history list is replaced by the same component (server-filtered fields).
- Agency application detail: the outcome label beside a history row.

## Review notes (Phase 3)

- **API**: response fields are only added; `changed_at` stays. Reads only; no transactions. One query with an outer join to `users`.
- **Security**: authz unchanged (`_assigned_application`, AGN-004 `application_scope`); H2 enforced server-side; author is a name
  only (no email/phone, AGN-023 H7); no HTML rendering; no new logging of free text.
- **Frontend**: reuses `LocalTime`, `stageLabel`, `subStatusLabel`, `outcomeLabel`; keyboard-operable buttons; wraps on mobile.

## Non-goals

Student 360 History tab (ccrm-009); admin-table History link; notifications (unchanged); reassignment reason capture (ccrm-033).
