# pob-007 — BD activity completeness: LinkedIn, call/meeting/follow-up fields, BD visits (design)

**Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` `pob-007` (§4 activity table; §18 AC "The CRM records outreach, calls,
emails, LinkedIn messages, meetings and next follow-up tasks"). Classification `UNVERIFIED` (a requirements draft). Decision:
`DEC-SCOPE-422`. Every call below (A1–A12) is the builder's, `NEEDS_CONFIRMATION`. Dependencies pob-005 (`DEC-SCOPE-411`) and pob-023
(`DEC-SCOPE-408`) are built.

## Goal
A Placement Officer can record every §4 BD activity with its fields: LinkedIn outreach (manual), message outcomes with the next follow-up,
call details, meeting details with action items that become follow-ups, follow-up priority and reminder time, and BD visits to a company.
**Anti-goals:** a LinkedIn API or scraping (§17 platform terms); reminder delivery (pob-008); a BD-visit expense workflow; new grants.

## Calls (builder's answers)
- **A1 LinkedIn is a logged message.** `recruiter_messages.channel` gains `linkedin`, with `linkedin_action` (`connection_request`,
  `message`; required for LinkedIn, null otherwise). `POST /recruiter/messages/linkedin` records one: a contact or a candidate (the send's
  party rules: scope 404, `can_edit` 403, inactive / archived 409, Do Not Contact 409), `sent_at` (default now; the call form's rule: not in
  the future, at most 7 days back), an optional usable LinkedIn template (422 otherwise; its name is kept and `last_used_at` moves), the
  text sent (optional for a connection request, required for a message; ≤ 2000), and an optional `next_follow_up` (contact only, rec-024's
  rules, same transaction). It is outreach: the company's Last contacted (pob-003) and the contact's status (pob-005 → Contacted) move; the
  per-sender daily cap is 300 (as WhatsApp). There is no delivery status. Audit `recruiter_message.create` with `channel: linkedin`.
- **A2 LinkedIn in the timeline.** The existing message branch already carries every channel; LinkedIn rows read "LinkedIn connection
  request sent" / "LinkedIn message sent" (the action travels in `status`). Company, per-contact and candidate timelines (AC3).
- **A3 Message outcome.** `POST /recruiter/messages/{id}/outcome` `{outcome, next_follow_up?}` on a contact message (any channel): the
  reply's scope and right (404 / 403 / 409 archived); a candidate message is 422 (follow-ups belong to a company). Recorded once: a second
  is 409. The follow-up uses rec-024's rules (and links the contact when still active). Message output gains `outcome`,
  `follow_up {id, due_at}` and `linkedin_action`. Reply status is pob-005's `replied_at` (unchanged).
- **A4 Call fields.** `job_id` (the requirement discussed: one of the contact's company, 422 otherwise; contact calls only),
  `objections` (catalogue keys, ≤ 8, no repeats) and `objection_notes` (≤ 1000), `next_action` (≤ 500). On create and on the same-day edit.
  Output gains them plus `requirement {id, code, title}`. Objection catalogue (UNVERIFIED, the source names none): no current requirement,
  already works with vendors, fees too high, no hiring budget, not the right time, not the decision-maker, hires in-house only, other.
- **A5 Meeting fields.** Recorded with the outcome: `hiring_forecast` (≤ 10 rows of role ≤ 120, count 1–10000, timeframe: this month,
  next 3 / 6 / 12 months), `commercial_notes` (≤ 2000), `action_items` (≤ 10 rows of action ≤ 500, due time, follow-up reason).
- **A6 Action items create follow-ups (AC2).** Each item becomes a rec-024 follow-up (notes = the action, the meeting's contact when still
  active) in the outcome's transaction, kept in order in `recruiter_meeting_action_items` (meeting, follow-up, position). The legacy single
  `next_action` stays accepted and shown. A refusal of any follow-up (past time, the open cap) refuses the whole outcome.
- **A7 Commercial-discussion notes are grant-gated (Q-07 second half).** Writing needs pob-001's `commercials.client.view` (403 otherwise);
  reading returns them only with it (`commercial_notes: null`, `commercial_notes_visible: false` without). Never in the timeline or logs.
- **A8 Follow-up priority and reminder.** `priority` (`high`, `medium`, `low`; default `medium`) and `remind_at` (optional; in the future
  when set or changed, and not after `due_at` → 422 on `remind_at`) on create and edit. Moving `due_at` before a stored reminder is 422
  unless the reminder moves too. Stored only: delivery is pob-008.
- **A9 BD visits (Q-07 first half): a recruiter meeting of type `company_visit`** ("Company visit (BD visit)"), mode "In person" suggested
  in the form. It reuses scheduling, participants, outcome, action items, history and the timeline. `BdmTrip` is not extended: it is the
  BDM role's travel plan with expenses, which `placement_team` cannot open; a company target there would couple the two CRMs.
- **A10 RBAC unchanged.** Every new write uses the party's existing right (the company's `can_edit`, the candidate pool's writers).
- **A11 Privacy.** Audit and logs carry ids, keys and counts — never message text, objections notes, forecasts or commercial notes.
- **A12 Data.** Additive, nullable columns (priority has a default); existing rows are unchanged and read as before.

## Data (migration 0302, guarded like 0299)
- `recruiter_messages`: `linkedin_action` String(24), `outcome` String(500), `follow_up_id` FK → follow-ups; the channel check gains
  `linkedin`; new check `(channel = 'linkedin') = (linkedin_action IS NOT NULL)` and the action list.
- `recruiter_calls`: `job_id` FK → jobs, `objections` JSON, `objection_notes` String(1000), `next_action` String(500); check
  `job_id IS NULL OR contact_id IS NOT NULL`.
- `recruiter_meetings`: `hiring_forecast` JSON, `commercial_notes` Text; the type check gains `company_visit`.
- `recruiter_follow_ups`: `priority` String(8) NOT NULL default `medium` (check), `remind_at` timestamptz; check `remind_at <= due_at`.
- new `recruiter_meeting_action_items` (id, meeting_id FK, follow_up_id FK unique, position; unique (meeting, position)).
- Downgrade: LinkedIn messages are deleted first (the old check cannot hold them), `company_visit` meetings become `company_meeting`.

## API (additive)
`POST /recruiter/messages/linkedin` (201), `POST /recruiter/messages/{id}/outcome` (200); extended bodies and outputs of calls, meetings'
outcome and follow-ups. Error order as in each module's spec. rec-038 matrix rows for the two routes.

## Web
- Messages: "Log LinkedIn" replaces nothing — the LinkedIn composer (pob-023) gains the action, the time and "Copy and log" / "Log"
  (a log without a template is allowed); a message line shows the LinkedIn action, its outcome and follow-up; "Record outcome" on a
  contact message (outcome + optional follow-up).
- Call form: requirement discussed (the company's requirements), objections (checkboxes), objection notes, next action; the call list shows them.
- Meeting outcome form: hiring forecast rows, commercial notes (only when visible), action items (add/remove rows); the item shows them.
  Meeting type "Company visit (BD visit)".
- Follow-up form: priority and reminder; the item shows a High-priority badge and the reminder.
- Timeline: LinkedIn rows.

## Acceptance (testable)
1. Each §4 activity type is logged with all its fields: LinkedIn (action, time, template, text, next follow-up), message outcome +
   follow-up, call (requirement, objections, notes, next action), meeting (forecast, commercial notes, action items), follow-up (priority,
   reminder), BD visit (a `company_visit` meeting).
2. Meeting action items create follow-ups (one per item, in order, linked to the meeting; refusal rolls back).
3. LinkedIn activity appears in the company, per-contact and candidate timelines.
4. Commercial notes are hidden and unwritable without `commercials.client.view`.
5. Scope: another recruiter's contact / message is 404; a read-only role is 403; Do Not Contact refuses LinkedIn logging.

## Regression risks
rec-025/026/028/024 schemas (`extra="forbid"` bodies grow), rec-026 migration check copies (`test_rec_026_migration`), rec-028's type
check, rec-027 timeline, company merge (moves messages/calls), candidate privacy (blanks message bodies), pob-023 copy mode, web fixtures.
