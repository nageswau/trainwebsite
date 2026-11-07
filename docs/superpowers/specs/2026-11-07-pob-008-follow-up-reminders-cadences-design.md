# pob-008 — Recruiter follow-up reminders and outreach cadences (design)

**Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` `pob-008` (§3.3 "Allow follow-up reminders"; §4 "Set reminders for overdue
follow-ups and unanswered outreach"; §16 "No reply after configured period → Create reminder using the chosen communication cadence",
"New company/contact created → … create a follow-up task"). Classification `UNVERIFIED` (a requirements draft). Decision `DEC-SCOPE-423`.
Every call below (B1–B12) is the builder's, `NEEDS_CONFIRMATION`; the owner said to proceed with the recommended answers. Dependencies
pob-005 (`DEC-SCOPE-411`), pob-007 (`DEC-SCOPE-422`) and itc-002 (`DEC-SCOPE-336`, `notify()`) are merged. Migration
`0303_outreach_cadences`, API §12LP, RBAC §2.314.

## Intent
Follow-ups have Today / Overdue lists and (since pob-007) a stored `remind_at`, but nothing ever tells the recruiter. Outreach that gets no
reply is only chased if the recruiter remembers. pob-008 delivers the reminders, lets the Team Lead define outreach cadences that turn
"no reply yet" into the next step's follow-up, and gives every new company or contact a first-outreach follow-up.

**Anti-goals:** sending outreach automatically (every step is a follow-up the recruiter acts on; no unreviewed email/WhatsApp/LinkedIn);
a per-user reminder setting; new grants; changing the shared `MessagesSection` (upc-012 uses it).

## Builder's calls
- **B1 Reminder delivery.** Beat `pob008-follow-up-reminders` every 5 minutes. An open follow-up with `reminded_at IS NULL` is due a
  reminder when `remind_at <= now`, or, with no `remind_at`, when `due_at <= now + 30 minutes` (this also covers overdue ones). Once per
  follow-up: `recruiter_follow_ups.reminded_at` is set in the transaction of the notice. `FOR UPDATE SKIP LOCKED`, at most 200 a run,
  soonest first; archived companies are skipped (and stay unreminded).
- **B2 Recipient = the owner now.** The company's assigned recruiter when active, else the follow-up's creator when active; nobody →
  left for a later run. A reassigned company's follow-ups therefore remind the new owner (edge case in the backlog).
- **B3 Notice.** itc-002 `notify` with the new fixed-text event `it.recruiter.follow_up_due` ("Follow-up due" / "A follow-up is due soon
  or overdue. Open EduSphere to act on it."), entity `recruiter_follow_up`, action URL `/recruiter/follow-ups`. It joins
  `RECRUITMENT_EVENTS` (hrc-032 delivery exceptions). No reason, note or company name in the text.
- **B4 Re-arm.** Editing `due_at` or `remind_at` of an open follow-up clears `reminded_at`, so a rescheduled follow-up is reminded again.
- **B5 Cadence definitions.** `recruiter_cadences`: `name` (1–120, unique case-insensitive), `description` (≤ 500, optional), `active`,
  `steps` JSON — 2 to 10 steps of `{day, channel, template_id}`:
  - `day` 0–90, the first is 0, strictly increasing;
  - `channel` `email`, `whatsapp`, `linkedin` or `call`;
  - `template_id` optional; when set it must be an **approved shared** template of that channel (422 on `steps`).
  Never deleted; deactivated. CRUD: `GET /recruiter/cadences` (every recruiter-CRM reader: rec-003 `caller_scope` roles, else 403;
  `?include_inactive=true`), `POST /recruiter/cadences` (201), `PATCH /recruiter/cadences/{id}` — writes for `placement_manager` (the Team
  Lead) and `super_admin` only (403). Writes lock the row and are audited (ids, field names, step count).
- **B6 Starting a cadence = on an outreach message.** `POST /recruiter/messages/{id}/cadence {cadence_id}` (201) on a message to a
  contact: the reply's scope and right (404 / 403 / 409 archived), a candidate message 422, an inactive cadence 422, a Do Not Contact /
  Not interested / inactive contact 409, a message already replied 409, a contact that already runs a cadence 409 (one active per contact,
  a partial unique index). The message is step 1 (day 0); the run keeps a **snapshot** of the name and steps, so a later edit by the Team
  Lead does not change a run in progress. This is the "picker on the outreach form": the recruiter sends (or logs) the day-0 outreach,
  then picks the cadence on that message line.
- **B7 Run state.** `recruiter_contact_cadences`: cadence, contact, company, start message, started by / at, `steps` snapshot, `name`,
  `step` (steps done, 1 at start), `next_step_at` (start + next step's day; null once ended), `status` `active` / `replied` / `stopped` /
  `completed`, `ended_at`, `end_reason` (`reply`, `do_not_contact`, `not_interested`, `inactive`, `archived`, `manual`), last follow-up id.
  Indexed: `(next_step_at) WHERE status = 'active'`.
- **B8 Cadence sweep.** Beat `pob008-cadences` every 15 minutes, bounded (200, `SKIP LOCKED`, earliest `next_step_at` first). For each
  active run with `next_step_at <= now`:
  - **stop** first when the contact replied (any reply logged on a message to the contact sent at or after the start, or the contact's
    status is Replied / Meeting scheduled) → `replied`; the contact is Do Not Contact / Not interested / inactive, or the company is
    archived → `stopped` with that reason;
  - otherwise create the next step's rec-024 follow-up: reason `cadence_step`, the contact, due `max(now, start + day)`, created by the
    owner (B2's rule), notes "‹cadence› — step k of n: ‹channel›" plus the template's name and its text rendered for the contact (pob-023's
    allow-list renderer; email keeps its subject line). The follow-up then gets B1's reminder. The last step's follow-up completes the run.
  The FU8 open cap is a manual-abuse bound and does not apply (pob-022 A5's call).
- **B9 Immediate stops.** A reply logged by hand (pob-005 D7) and any move of the contact to Replied / Meeting scheduled, a manual change
  to Do Not Contact / Not interested, and a deactivation end the run in the same transaction (AC3), so the screen never shows a stopped
  cadence as running. The sweep's checks (B8) are the safety net. `POST /recruiter/messages/{id}/cadence/stop` stops by hand (`manual`;
  the company's `can_edit`; 409 when not running).
- **B10 First outreach (§16).** `POST /recruiter/companies` (the recruiter route) and `POST /recruiter/companies/{id}/contacts` create one
  open follow-up, reason `first_outreach`, due 24 hours later, created by the caller, in the same transaction: about the new contact (the
  company's first contact when sent with the company), else about the company. Not for a contact added as Do Not Contact / Not interested,
  not when the company is at the FU8 cap, and **not for imports** (pob-006 bulk import: hundreds of tasks at once; `NEEDS_CONFIRMATION`).
- **B11 Reasons.** `RECRUITER_FOLLOW_UP_REASONS` gains `first_outreach` ("First outreach") and `cadence_step` ("Outreach cadence step");
  both are also offered in the manual follow-up form (harmless; keeps one catalogue).
- **B12 Migration safety.** Additive. On upgrade, open follow-ups already past due get `reminded_at = now()` so the first run sends no
  backlog; upcoming ones are reminded normally. The reason check is re-created (frozen copy). Downgrade drops the cadence tables and the
  column, deletes no follow-up: `first_outreach` / `cadence_step` rows become `new_openings` (the closest old reason) so the old check holds.

## Data (migration 0303)
- `recruiter_follow_ups.reminded_at` timestamptz; index `(due_at) WHERE status = 'open' AND reminded_at IS NULL`; reason check gains 2 keys.
- `recruiter_cadences` (id, name, description, active, steps JSON, created_by, updated_by, timestamps; unique `lower(name)`).
- `recruiter_contact_cadences` (B7; FKs RESTRICT; unique `(contact_id) WHERE status = 'active'`; checks on status / end_reason / the
  `status = 'active'` ⇔ `ended_at IS NULL` ⇔ `next_step_at IS NOT NULL` invariant).

## API (additive)
`GET/POST /recruiter/cadences`, `PATCH /recruiter/cadences/{id}`, `POST /recruiter/messages/{id}/cadence`,
`POST /recruiter/messages/{id}/cadence/stop`. Message output gains `cadence` (`{id, name, status, step, steps, next_step_at, end_reason,
can_stop}` for the run started on that message, else null). Follow-up output gains `reminded_at`. rec-038 matrix rows for the new routes.

## Web
- `/recruiter/manager/cadences` (manager nav "Outreach cadences"): list (name, steps summary, active), add / edit form with step rows
  (day, channel, template select of approved shared templates of that channel), activate / deactivate. Loading / empty / error states;
  others reaching the page get the access-unavailable screen (the API's 403 on writes; reads are open to recruiters but the page is the
  manager's).
- Company Messages: on a contact message line, a writer sees "Start cadence" (select of active cadences + Start) when the message has no
  reply and no run; a message that started a run shows "Cadence ‹name› · step k of n · next ‹date›" or its end ("Stopped: reply"), with
  "Stop cadence" while active. Uses `MessagesSection`'s existing `itemAction` slot.
- Follow-up reasons gain the two labels.

## Acceptance (testable)
1. A reminder is sent once per follow-up (reruns add nothing); a moved due/remind time re-arms it; the recipient is the current owner.
2. Without a reply, the next cadence step's follow-up appears once the step's day is reached (with the template text); the last step
   completes the run.
3. A reply (logged, or the status moving to Replied) stops the cadence; Do Not Contact stops it and refuses a start.
4. Cadence CRUD: Team Lead / super_admin write; a recruiter reads but gets 403 on writes; invalid steps / templates are 422.
5. A new company / contact gets one first-outreach follow-up; an import does not.

## Tests
`tests/test_pob_008_reminders_cadences.py`, `tests/test_pob_008_migration.py`, vitest for the cadence library and the message cadence
control, Playwright `apps/web/tests/e2e/pob-008-cadences.spec.ts`.

## Regression risks
The beat schedule; rec-024 follow-up counts in tests that create companies (B10 adds an upcoming follow-up); migration frozen copies
(`test_pob_016_migration` pins the reason check); rec-038 route matrix; recruiter nav pin tests; message output fixtures.
