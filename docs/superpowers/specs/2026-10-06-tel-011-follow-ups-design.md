# tel-011 — Lead follow-ups: design

NO-ASSUMPTION MODE. Source: `docs/delivery/TELECALLER_CRM_BACKLOG.md` §4 tel-011, Appendix A L266–L312, Appendix B B3/B9; `EVID-019` §7.
The branch is `feature/tel-011`, cut from `main` @ `515e6c13` (tel-006 merged). Decision `DEC-SCOPE-094`, migration `0090_lead_follow_ups`
(re-chained after tel-009's `0089_lead_qualifications` / `DEC-SCOPE-093` / §12O, which merged first), API contract §12P. Earlier drafts of this spec said
093 / 0089.

## 1. Decisions

| # | Topic | Decision |
|---|---|---|
| F1 (owner, Q-10) | Overdue / call | A follow-up is **overdue** when it is `open` and `due_at < now` (to the minute). Logging a call (tel-010) never auto-completes one; the telecaller marks it done |
| F2 (owner) | Who writes | **Only the lead's telecaller** creates, reschedules, completes and cancels. A `telecaller_manager` / `super_admin` reads its reports' follow-ups (lists + lead detail); its writes are 403 |
| F3 (owner) | Reassignment | A follow-up **belongs to its lead**: scope is the lead's (`lead_pipeline.scope`), so on reassignment the new telecaller sees and acts on it and the old one gets 404. There is no `telecaller_user_id` column to rewrite (deviation from the backlog's DB note, which this decision supersedes); `created_by_user_id` / `completed_by_user_id` keep who did what |
| F4 (owner) | Closed / handed over | No new follow-up on a **closed** lead (409) or, for a telecaller, a **handed-over** lead (403, tel-008 D1). A move to a closed stage (`lead_pipeline.person_move`, the only path into a closed stage) cancels the lead's open follow-ups in the same transaction (`cancel_reason = "Lead closed"`). Cancel on handover stays with tel-018 |
| F5 (default) | Stage | Creating a follow-up moves the lead to `follow_up` only when the telecaller ticks "Also move the lead to Follow-up" (T13). The move is `person_move(..., "follow_up")`, so every tel-004 rule applies (422 past the counselor). Already at `follow_up` → no move |
| F6 (default) | Times | `due_at` is a timezone-aware instant; it must be in the future at create and on a changed reschedule (422), and within 366 days (422). Day windows are IST (`day_range`) |
| F10 (review) | Abuse bound | At most 20 open follow-ups per lead (409), counted under the lead lock |
| F7 (default) | Endpoints | The backlog's single `PATCH` is split along the bdm-008 idiom: `PATCH` (reschedule/edit), `POST …/complete`, `POST …/cancel` (reason required). A done/cancelled follow-up is 409 for every write |
| F8 (default) | "Last call" | The §7 card's "Last Call" needs `lead_calls` (tel-010). It is not shown until tel-010 adds it to the list item; no placeholder (tel-008 D4) |
| F9 (default) | My Leads filter | tel-008 D3's deferred "Due follow-up" filter: `GET /telecaller/leads?follow_up=today|overdue` — an open follow-up due in today's IST window / overdue |

## 2. Data — `lead_follow_ups` (migration 0089)

`id` uuid PK · `lead_id` → `enquiries` (RESTRICT) · `due_at` timestamptz · `reason` varchar(40) CHECK in the 10 keys · `notes` text NULL ·
`next_action` varchar(200) NULL · `status` varchar(16) default `open` CHECK `open|done|cancelled` · `created_by_user_id` → users ·
`completed_at`, `completed_by_user_id`, `cancelled_at`, `cancel_reason` varchar(500) NULL · `created_at`, `updated_at`.
CHECK `ck_lead_follow_ups_state`: done ⇔ completed_at and completed_by set; cancelled ⇔ cancelled_at and cancel_reason set; open ⇔ neither.
Indexes: `ix_lead_follow_ups_lead (lead_id, status, due_at)`; partial `ix_lead_follow_ups_open_due (due_at) WHERE status = 'open'`.

Reasons (§7 L284–L302): `discuss_with_parents` Need to discuss with parents · `course_details` Need course details · `fee_details` Need fee
details · `waiting_salary` Waiting for salary · `waiting_documents` Waiting for documents · `comparing_courses` Comparing courses ·
`next_month` Interested next month · `next_intake` Interested next intake · `university_information` Waiting for university information ·
`counselor_call` Requested counselor call.

## 3. API (§12P)

All under `/telecaller`, scope = `lead_pipeline.scope(user)` joined through the lead (other roles 403, signed out 401, out of scope 404).

- `GET /follow-ups?view=day|overdue&day=YYYY-MM-DD&limit&offset` — `day` (default): open follow-ups with `due_at` in that IST day (default
  today), oldest due first (AC1). `overdue`: every open follow-up with `due_at < now`, oldest first. Response `{items,total,limit,offset,
  day, counts: {day, overdue}}`.
- `GET /leads/{id}/follow-ups` — the lead's follow-ups: open by due time, then done/cancelled newest first.
- `POST /leads/{id}/follow-ups` `{due_at, reason, notes?, next_action?, move_to_follow_up?}` → 201. Order: lead locked in scope (404) →
  telecaller only (403) → handed over (403) → closed (409) → time rules (422) → optional stage move → insert → audit.
- `PATCH /follow-ups/{id}` `{due_at?, reason?, notes?, next_action?}` — open only (409); only changed values are written and audited.
- `POST /follow-ups/{id}/complete` · `POST /follow-ups/{id}/cancel {reason}`.

Item: `{id, lead: {id, lead_code, name, priority, status, status_label, product: {id,name}|null, telecaller}, due_at, reason, notes,
next_action, status, overdue, created_by, created_at, completed_at, completed_by, cancelled_at, cancel_reason, can_change}`.
`can_change` = caller is the lead's telecaller, the lead is not handed over, and the follow-up is open.

Writes lock the **lead, then the follow-up** (the same order as a closing stage move), so a complete racing a close serialises. Audit
`lead_follow_up.{create,update,complete,cancel}` with ids, reason key and field names; notes, next action and cancel reasons are never logged.

## 4. Web

- `lib/telecallerFollowUps.ts` — types, reason labels, URLs, guards.
- `FollowUpForm` — date-time (IST), reason, next action, notes; the stage tick on create; server errors placed on fields; leave guard.
- `LeadFollowUps` — the lead-detail section: list, Add, Reschedule/Edit, Done, Cancel (reason); read-only for managers and handed-over leads.
- `TodayFollowUps` — the §7 card list (student, interest, action + time, priority, Overdue badge) with Today / Overdue tabs and a day
  picker; pages `/telecaller/follow-ups` and `/telecaller/manager/follow-ups` (telecaller name shown); nav "Follow-ups"; a "Today's
  follow-ups" card on the telecaller dashboard; My Leads gets the "Due follow-up" filter.

## 5. Acceptance criteria (backlog + decisions)

1. Today's list shows exactly the open follow-ups due in today's IST window, ordered by time (AC1).
2. Overdue ones are marked (AC2), and the Overdue view lists every open past-due follow-up (F1).
3. A due time in the past at creation → 422 (AC3).
4. Completing someone else's follow-up → 404 (negative scenario).
5. Managers read their reports' follow-ups; their writes are 403 (F2).
6. A reassigned lead's follow-ups move with it (F3).
7. Closed lead → 409, handed-over lead → 403 for a telecaller; closing cancels open follow-ups (F4).
8. The stage moves to Follow-up only when asked (F5).
9. My Leads `follow_up=today|overdue` narrows the list (F9).

## 6. Risks

`lead_pipeline.person_move` gains the close cancel — a shared hot spot (tel-004's frozen API keeps its signature). `api/telecaller.py`
`my_leads` gains one filter. Both have focused regression tests (tel-004 routes, tel-008 workspace).
