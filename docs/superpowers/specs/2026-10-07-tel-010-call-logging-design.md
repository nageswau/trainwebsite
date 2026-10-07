# tel-010 — Call logging (design)

- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` § tel-010 (EVID-019 §5, L198–L252; T5, T7). Dependencies tel-008 (PR #85) and
  tel-011 (PR #100) are merged.
- **Decision:** `DEC-SCOPE-096` (CL1–CL4 owner answers 2026-10-07; D1–D10 defaults). Migration `0092_lead_calls`, API contract §12R,
  RBAC §2.24. The tel-016 session (in parallel) holds `0091` / `DEC-SCOPE-095` / §12Q / RBAC 2.23. `0092` chains to main's `0090` until
  tel-016 merges; whichever merges second re-chains.

## 1. Decisions

| ID | Topic | Answer |
|---|---|---|
| CL1 (Q-08) | Call type | `outgoing` / `incoming`. A requested call-back is an outcome, not a type |
| CL2 | Closed lead | No call is logged on a closed lead: 409 ("A manager can reopen it"), as tel-011 F4 |
| CL3 | Duplicate Lead | Recorded only. Remarks are required (name the other lead); no stage change. A merge is deferred |
| CL4 | Edit / delete | Same IST day only (bdm-009). The outcome is locked: to change it, delete and log again. Delete removes the row but never reverses a stage move or a follow-up the call created |
| D1 | Outcomes | 13 selectable (EVID-019 L226–L250); "Converted" is never offered (T5) |
| D2 | Connected | Appendix B B7: Busy, No Answer, Switched Off, Wrong Number are *not connected*; every other outcome is *connected* (B6) |
| D3 | Pipeline effects | See §2. Connected → tel-004 event `call_connected` (new/assigned/first_call_pending → contacted); Busy / No Answer / Switched Off → `call_unconnected` (new/assigned → first_call_pending); Connected – Interested additionally moves to `interested` when the lead is before it (never backwards); the four closing outcomes close the lead with the outcome label as reason (closing cancels open follow-ups, tel-011 F4) |
| D4 | Follow-up required | Connected – Follow-up Required and Call Back Requested need a next follow-up (422 on `next_follow_up`). A closing outcome with a next follow-up is 422 |
| D5 | Next follow-up | The tel-011 create body (`due_at`, `reason`, `notes`, `next_action`, `move_to_follow_up`) through `lead_follow_ups.create`, in the same transaction (any refusal rolls the call back) |
| D6 | Time | `occurred_at` defaults to now (IST in the form). More than 5 min in the future → 422; more than 7 IST days back → 422 (bdm-009 V4/V9; AC2). Errors sit on the field |
| D7 | Duration | `duration_seconds` 0–14400 (4 h), required; 0 is valid (not-connected calls) |
| D8 | Who | Write: only the lead's telecaller, before handover (403 otherwise; a manager / super_admin is 403). Edit / delete: only the caller (`caller_user_id`), lead still theirs and not handed over. Read: the lead's scope (tel-004 `scope`: telecaller own, manager reports, super_admin all; others 403; out of scope 404) |
| D9 | Daily cap | 300 calls per caller per IST day (409) — an abuse bound, soft under concurrency (bdm-009 V10 precedent) |
| D10 | Last call | tel-011 F8: the follow-up list item's lead gains `last_call` `{occurred_at, outcome}` (newest call on the lead), shown on the §7 card |

## 2. Outcomes

| Key | Label | Connected | Effect |
|---|---|---|---|
| `interested` | Connected – Interested | yes | contacted; then `interested` if before it |
| `need_information` | Connected – Need Information | yes | contacted |
| `follow_up_required` | Connected – Follow-up Required | yes | contacted; next follow-up required |
| `appointment_fixed` | Connected – Appointment Fixed | yes | contacted (the booking is tel-016's; without it the stage stays `contacted`) |
| `not_interested` | Not Interested | yes | close → `not_interested` |
| `wrong_number` | Wrong Number | no | close → `wrong_number` |
| `busy` | Busy | no | first_call_pending |
| `no_answer` | No Answer | no | first_call_pending |
| `switched_off` | Switched Off | no | first_call_pending |
| `call_back_requested` | Call Back Requested | yes | contacted; next follow-up required |
| `already_joined` | Already Joined Elsewhere | yes | close → `lost` |
| `duplicate_lead` | Duplicate Lead | yes | none; remarks required (CL3) |
| `not_eligible` | Not Eligible | yes | close → `not_eligible` |

Closing outcomes close directly (one history row, reason = the label); they don't first pass the first-call events.

## 3. Data

`lead_calls`: `id`, `lead_id` → enquiries (RESTRICT), `caller_user_id` → users (RESTRICT), `occurred_at` timestamptz, `duration_seconds` int,
`call_type` varchar(16), `outcome` varchar(32), `remarks` text null, `created_at`, `updated_at`. Checks: type, outcome, duration 0–14400.
Indexes `(caller_user_id, occurred_at)` (daily counts) and `(lead_id, occurred_at)` (per-lead list, last call). Migration guarded like 0090.

## 4. API (§12R)

| Route | Notes |
|---|---|
| `GET /telecaller/leads/{id}/calls` | Lead in scope (404). Newest first, `{items, total, limit, offset}`; each item has `caller`, `outcome_label`, `connected`, `can_change` |
| `POST /telecaller/leads/{id}/calls` | Body `{occurred_at?, duration_seconds, call_type, outcome, remarks?, next_follow_up?}`. Order: scope 404 → lead lock → telecaller 403 → handover 403 → closed 409 → time 422 → outcome rules 422 → cap 409 → effects → follow-up → audit → commit. 201 `{call, lead: {id, status, status_label, stage_changed_at}, follow_up_id}` |
| `PATCH /telecaller/calls/{id}` | `{occurred_at?, duration_seconds?, call_type?, remarks?}` (outcome not accepted: unknown field 422). Scope 404 → lock → caller 403 → handover 403 → same day 409 → a moved time must stay in today 422 → duplicate keeps remarks 422 |
| `DELETE /telecaller/calls/{id}` | Same gates; 204. No reversal (CL4) |
| `GET /telecaller/calls/day-counts?day=` | AC4. Calls *made by* the caller scope on that IST day (default today): telecaller own; manager their reports; super_admin all. `{day, total, connected, not_connected, by_outcome: {key: n}}` — every key present |

Audit `lead_call.create|update|delete` with ids, outcome and field names. Logs carry ids and the outcome — never remarks.

## 5. Web

- `lib/telecallerCalls.ts`: outcomes, types, URLs, guards.
- `CallLogForm` (create / edit): date-time (IST, default now), duration (min + s), type, outcome, remarks, and a "Next follow-up" block
  (due, reason, next action) that is required for D4 outcomes and hidden for closing ones. Field errors inline; never clears typed text.
- `LeadCalls` on the lead page: "Log call" + the list with Edit / Delete when `can_change`. The header's "Call" (`tel:`) also opens the form.
  A stage change updates the page header; a created follow-up reloads the follow-ups list.
- The §7 follow-up card shows "Last call" (D10).

## 6. Tests

API (pytest): each outcome's effect (incl. repeated events never re-fire: No Answer ×2 then Connected – Interested), D4/CL3 422s, AC2
time bounds, next follow-up created, closed 409, handover 403, manager 403, other telecaller 404, cap, edit/delete same-day/caller rules,
day counts exact per outcome and scoped, last_call on follow-ups, migration round trip. Web: vitest for the lib helpers; Playwright
`tel-010` logs a call from the lead page and sees the stage and the list update.
