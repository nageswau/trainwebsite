# pob-022 — Interview coordination automation (design)

**Decision:** `DEC-SCOPE-421` (builder's calls A1–A10, `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`
pob-022 (§12 bullets 3–8; §16 "Interview scheduled → Send approved confirmation/reminder", "Feedback overdue → Notify the responsible contact
owner and manager based on escalation rules"; the source DOCX is `UNVERIFIED`). The owner assigned pob-022 on 2026-11-07 and said to proceed
with the recommended answers. Dependencies hrc-028 (`DEC-SCOPE-400`), hrc-032 (`DEC-SCOPE-413`) and pob-023 (`DEC-SCOPE-408`) are merged.
Migration `0301_interview_automation`, API §12LN, RBAC §2.313.

## Intent
Today the interview confirmation is hard-coded text, nobody is reminded before an interview, and a client who never sends feedback is only
noticed by hrc-032's single "feedback overdue" notice. pob-022 lets the recruiter confirm with an approved template, sends reminders before
the interview from the worker, and turns missing client feedback into a follow-up for the owner that escalates to the Team Lead.

## Builder's calls
- **A1 Confirmation template.** `POST /recruiter/interviews` and `POST /recruiter/interviews/{id}/reschedule` take an optional `template_id`.
  It must be an **approved shared** email template of kind `interview_confirmation` (pob-023 G4/G5: personal templates are never approved);
  anything else is 422 on `template_id`. The candidate's and the contact's emails (and a portal candidate's in-app notice, which its email
  delivery reads) then carry the template's rendered subject and body, each with that recipient's values (`{name}` is the recipient,
  `{candidate}`, `{company}`, `{designation}`, `{recruiter}`, the interview's `{interview_*}`, `{job_*}`; `{package_range}` keeps pob-001's
  grant), followed by the interview details block, so the time, link and instructions are always exact. The `.ics` is unchanged. The
  queued `recruiter_messages` rows keep the `template_id`, the template's `last_used_at` moves (G7) and the audit row names the template id.
  Without `template_id`, or with `notify: false`, nothing changes. Edit and cancel notices keep the fixed text.
- **A2 Settings.** One global row `interview_automation_settings` (id 1, seeded):
  - `first_reminder_hours` 24, `second_reminder_hours` 2: 1–168 each, null switches that reminder off, and the second must be sooner than the first.
  - `reminder_template_id`: null means the fixed reminder text.
  - `chase_after_hours` (N) 24 and `escalate_after_hours` (M) 24: 1–720 each, null switches that step off.
  - `chase_template_id`: null means the fixed chase text.

  Each template must be an approved shared email template (any kind: no kind exists for a reminder email or a feedback chase).
  `GET/PUT /recruiter/interview-automation/settings` is for `placement_manager` (the Team Lead, pob-001) and `super_admin`, and is 403 for
  everyone else. A save is audited with its before and after.
- **A3 Reminders.** The beat job `pob022-interview-reminders` runs every 15 minutes. An open interview (scheduled, confirmed or
  rescheduled) whose start is in the future and within a slot's hours, with that slot's marker unset, gets the reminder once:
  - the marker is `interviews.first_reminder_at` / `second_reminder_at`, set in the same transaction as the notices
  - `FOR UPDATE SKIP LOCKED`, at most 200 per run, soonest first
  - when both slots are due at once, one reminder goes out and both markers are set

  Recipients and channels are the confirmation's: a portal candidate gets an in-app notice plus deliveries through `notify` (email and
  consented WhatsApp/SMS), anyone else a queued email; the client contact gets an email unless Do Not Contact, inactive or without an email.
  The reminder carries no `.ics` and never internal notes or feedback. Its emails are sent as the interview's owner (application owner,
  else the requirement's primary, else the creator); with none, only the in-app notice goes.
- **A4 Re-arm.** Scheduling (`insert`, every creator) and rescheduling set each marker to "now" when the new start is already inside that
  slot (the confirmation just went out, so no reminder minutes later) and clear it otherwise, so a rescheduled interview is reminded again.
  The chase and escalation markers are cleared on reschedule too.
- **A5 Feedback chase.** The hourly `pob022-feedback-chase` job (at most 200 a run, oldest first, `SKIP LOCKED`) picks an interview that:
  - is awaiting feedback (hrc-032's set: open or completed)
  - ended (`ends_at`, else `scheduled_at`) more than N hours ago
  - has no `interview_feedback` row and no chase yet

  It creates a `recruiter_follow_ups` row on the requirement's company:
  - reason `interview_feedback`
  - the interview's contact when that contact is active, the job and the application
  - due now, created by the owner (as A3)
  - notes = the chase template rendered for the contact (fixed text when there is none)

  It also sets `interviews.chase_follow_up_id`. The follow-up shows in the owner's Today list. No extra notice is sent: hrc-032 already
  notifies the owner, so one trigger keeps one notice. With no owner, the interview is skipped and retried on a later run. The follow-up
  cap (FU8) is a manual-abuse bound and does not apply.
- **A6 Escalation.** The same job escalates, once (`interviews.chase_escalated_at`), when all of these hold:
  - the chase follow-up is still open
  - it is older than M hours
  - feedback is still missing

  The Team Lead is the follow-up owner's `recruiter_profiles.reporting_manager_user_id` when that person is an active
  `placement_manager`, else every active `placement_manager`. They get the fixed-text `it.interview.feedback_escalated` notice ("Interview
  feedback is still overdue after a follow-up. Open EduSphere to review it."). A follow-up that is done or cancelled means the owner
  handled it, so there is no escalation.
- **A7 Migration safety.** On upgrade, interviews that already started, or that start within 24 hours, get their reminder markers stamped, and
  interviews that had already started get `chase_escalated_at` stamped with `chase_follow_up_id` left null (the chase query requires
  `chase_escalated_at IS NULL`), so the first runs create no backlog of reminders, follow-ups or escalations.
- **A8 Catalogue.** `it.interview.feedback_escalated` joins `RECRUITMENT_EVENTS`, so hrc-032's exceptions page covers its failed deliveries.
  No new grant.
- **A9 UI.**
  - The schedule form and the reschedule form show a "Confirmation message" select: "Standard text" (default), then the approved
    interview confirmation templates. It is shown only while Notify is ticked, and loading or failing to load falls back to "Standard text"
    with a note.
  - Managers see an "Interview automation" panel on `/recruiter/interviews` with the reminder, chase and escalation hours and the two
    template selects. It has its own loading and error states and is saved as one form.
- **A10 Metrics.** The time-in-stage (`stage_changed_at`) and no-show (`status = no_show`) data already exist, and pob-028/029 own their
  widgets and reports. pob-022 adds no metric endpoint (`NEEDS_CONFIRMATION`).

## Non-goals
Automated WhatsApp from the recruiter's number (wa.me is manual), a chase email sent to the client without review, metrics widgets, per-company rules.

## Errors, races, security
- Every sweep commits per run. The marker and its notices or follow-up share one transaction: both or neither. A rerun adds nothing. The
  notices are published after commit through `notify` and the email queue.
- A reschedule takes the interview lock (`load_for_write`), so it cannot race a sweep that holds `SKIP LOCKED` rows: either the sweep
  passes over the row, or it waits.
- Settings writes lock row 1 and are audited. Template ids are validated server side, and the template text is rendered by pob-023's
  single-pass allow-list (no field access, plain text; the mailer escapes).
- Logs carry ids and counts only, never names, bodies or notes.

## Acceptance
1. Confirmation uses the template text (candidate and contact), and the standard text when there is no template.
2. Each reminder is sent once (reruns add nothing), and a reschedule re-arms it.
3. Overdue feedback creates one chase follow-up, then escalates once to the Team Lead after M hours. Recorded feedback or a closed
   follow-up stops it.
4. Settings: managers read and write, others get 403, and invalid hours or templates get 422.

## Tests
- `apps/api/tests/test_pob_022_interview_automation.py`
- `test_pob_022_migration.py`
- vitest for the form picker and the settings panel
- Playwright `apps/web/tests/e2e/pob-022-interview-automation.spec.ts`

## Regression risks
- rec-020 and hrc-028 tests pin the notice bodies: the no-template path is unchanged.
- The hrc-032 catalogue lists.
- The rec-038 route matrix (new routes need rows).
- `insert` is shared by the legacy and employer creators: the markers only.
