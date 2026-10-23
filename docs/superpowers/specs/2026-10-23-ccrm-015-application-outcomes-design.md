# ccrm-015 — Application exception outcomes (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` ccrm-015 (spec §7, Appendix B "University C rejects", AC 9). Evidence class of the spec:
UNVERIFIED; owner answers O1–O4 (2026-10-23) recorded as `DEC-SCOPE-244`.

## Intent

An overseas application can end or pause for reasons that are not a forward stage: the university rejects it, the student withdraws,
the intake is deferred, the case is put on hold, the student declines the offer (ccrm-025) or the visa is refused (ccrm-026). Today
those are refused (`api/workflows.py` 422 "open item") and only an agent can withdraw. This feature adds an **outcome** to each
application, independent of its stage, recorded per application (rejecting University C never touches A or B — AC 9).

## Owner answers

- **O1** Withdrawn keeps `status = 'withdrawn'` (AGN-008 readers) **and** sets `outcome = 'withdrawn'` with who requested, date and
  reason. Existing withdrawn rows are backfilled. An Admin reopen restores the stage (and sub-status) it was withdrawn from.
- **O2** Terminal: rejected, withdrawn, offer_declined, visa_refused — every stage, sub-status and edit write is refused (409) until the
  Overseas Admin reopens with a reason. On hold blocks stage / sub-status moves until resumed. Deferred is informational: it sets the new
  intake and revised deadlines and the application continues.
- **O3** Rejected / offer-declined / visa-refused free the duplicate slot like withdrawn (re-apply as a new application).
- **O4** No waitlist. The route sets rejected, withdrawn, deferred, on_hold, offer_declined. `visa_refused` is in the enum only
  (ccrm-026 writes it).

## Data (migration `0170_application_outcomes`, merges main's two 0169 heads)

- `overseas_applications.outcome` String(20) NULL, CHECK in the six values. NULL = no outcome.
- `application_outcomes` — one row per outcome event (append-only): `application_id` (CASCADE), `outcome` (the six values or
  `cleared`), `outcome_date`, `reason`, `requested_by` (student / counselor / agent / university), `next_steps`, `document_id`
  (student_documents, SET NULL), `previous_intake`, `new_intake`, `review_date`, `hold_owner_id`, `another_offer_preferred`,
  `created_by_id`, timestamps. The current outcome's detail is the latest row.
- Backfill: `outcome = 'withdrawn'` where `status = 'withdrawn'`. Downgrade drops both.
- Each event also writes an `application_status_history` row (from = to = stage, note "Outcome: Rejected — reason") so existing
  timelines show it; withdraw / reopen of a withdrawn application change the stage there.

## API (§12EW)

`POST /api/v1/workflows/overseas/applications/{id}/outcome` — counselor (own applications, agency too — CC4) or Overseas Admin.
Body `{outcome, outcome_date?, reason?, requested_by?, next_steps?, document_id?, new_intake?, application_deadline?, offer_deadline?,
review_date?, hold_owner_id?, another_offer_preferred?}`; per-outcome required fields are a 422:

| outcome | required | effect |
|---|---|---|
| rejected | reason | terminal; stage kept; letter must be a document of this application |
| withdrawn | reason, requested_by | terminal; `status = 'withdrawn'` |
| deferred | new_intake | intake and given deadlines updated; continues |
| on_hold | reason, review_date (≥ today) | blocks moves; owner = hold_owner_id or the actor (active overseas counselor/admin) |
| offer_declined | reason | terminal; needs the offer stage or later |

Refusals: current outcome terminal → 409; enrolled → 409; archived agency record → 409; outcome_date in the future → 422.
`POST …/outcome/reopen {reason}` — clears the outcome: on_hold / deferred by the counselor or Admin ("resume"); a terminal outcome by
the Overseas Admin only (403 otherwise). Restores the pre-withdraw stage from history.

Agency withdraw (`POST /agent/applications/{id}/status` to `withdrawn`) also sets the outcome; optional `requested_by` (default
`agent`), reason = notes. Reads: `GET …/status`, the agent detail and the portal rows carry `outcome`, `outcome_label` and (staff) an
`outcome_detail` / one-line `outcome_summary`. The student read omits reason, owner and letter.

Guards: everywhere `status == 'withdrawn'` is refused today now refuses any terminal outcome; `/advance`, `/sub-status`, PATCH status,
agency status / sub-status also refuse on hold (agency withdraw still allowed). Duplicate checks ignore terminal applications (O3).

## Notifications (CC5)

Student: "Application update — {university}: {label}". Agency application: the other side — the counselor when the agency withdrew, the
AGN-017 recipients when EduSphere set it. Reopen tells the same people.

## UI

Counselor "Evaluate Applications" card: outcome badge + summary; "Record outcome" opens `ApplicationOutcomeForm` (outcome select and its
fields); terminal/on-hold cards hide Advance and sub-status; on hold / deferred show "Resume". Admin applications table: Outcome column
and a "Reopen" control on terminal rows (reason prompt). Agent detail: outcome block, read-only for terminal outcomes; the withdraw
confirmation asks who requested. Student applications table: Outcome column.

## Calls made by the builder (not owner decisions)

- Rejection letter is an optional `document_id` in the API; the counselor UI has no document picker yet (ccrm-019 / 021 own
  application documents) — follow-up.
- Student is notified on every outcome, including on hold.
- Agency withdraw keeps reason optional (backward compatible with AGN-008).
- Management / school analytics counts are unchanged (they key on `status`); follow-up.

## Non-goals

Waitlist; on-hold review reminders (ccrm-030); visa refused writer (ccrm-026); offer decision UI (ccrm-025); status-history author
display (ccrm-016).
