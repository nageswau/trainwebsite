# pob-022 Interview automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, chosen by the owner's "do not stop" instruction). Steps use `- [ ]`.

**Goal:** Confirm interviews with an approved template, send T-24h/T-2h reminders once (re-armed on reschedule), and chase and then escalate overdue client feedback.

**Architecture:**
- A new service, `app/services/interview_automation.py`, holds the settings, the template checks, and the reminder and chase sweeps.
- `interviews.notify` gains an optional template.
- Two Celery beat tasks run the sweeps.
- The web side adds a template select to the schedule and reschedule forms, and a manager settings panel on `/recruiter/interviews`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Celery beat, Next.js/React, vitest and Playwright.

**Spec:** `docs/superpowers/specs/2026-11-07-pob-022-interview-automation-design.md`

## Global Constraints
- Decision `DEC-SCOPE-421`, migration `0301_interview_automation` (down_revision `0300_vendor_master`), API §12LN, RBAC §2.313.
- Defaults: first reminder 24, second 2 (each 1–168 or null, second < first); chase 24 and escalate 24 (each 1–720 or null); `SWEEP_LIMIT = 200`.
- Templates must be an approved shared email template (`owner_user_id IS NULL`, `status = 'approved'`, `channel = 'email'`). A confirmation template also needs `kind = 'interview_confirmation'`.
- Logs and audit rows carry ids and counts only. No internal notes or feedback go in a reminder.
- The migration is guarded: it checks for existing columns and tables, because 0001 runs `create_all`.

## Review Focus
- A rescheduled interview that is already inside the 2 h window: no reminder minutes after the confirmation (`test_reschedule_inside_window_stamps`).
- A template archived after it was chosen in settings: the sweep falls back to the fixed text (`test_archived_reminder_template_falls_back`).
- A Do Not Contact client contact: no reminder email to them (`test_reminder_skips_do_not_contact`).
- Feedback recorded after the chase: no escalation (`test_feedback_recorded_stops_escalation`).
- A sweep run twice: one reminder, one follow-up, one escalation (`test_reruns_add_nothing`).

---

### Task 1: Model, migration, settings service and routes
**Files:**
- Modify: `app/models.py` (Interview columns `first_reminder_at`, `second_reminder_at`, `chase_follow_up_id` (FK `recruiter_follow_ups.id` RESTRICT), `chase_escalated_at`; new `InterviewAutomationSetting`)
- Create: `alembic/versions/0301_interview_automation.py`, `app/services/interview_automation.py`
- Modify: `app/schemas.py` (`InterviewAutomationSettingsIn`), `app/api/recruiter_interviews.py` (`automation_router` with GET/PUT `/recruiter/interview-automation/settings`, included at the bottom)
- Test: `tests/test_pob_022_interview_automation.py`, `tests/test_pob_022_migration.py`

**Produces:**
- `settings(db) -> InterviewAutomationSetting`
- `settings_out(db, user) -> dict`
- `save_settings(db, user, payload) -> None`
- `require_manager(user)`, which raises 403 for anyone but `placement_manager` and `super_admin`
- `approved_template(db, template_id, *, field, kind=None) -> RecruiterMessageTemplate`, which raises 422 on `field`

- [ ] Tests:
  - `test_settings_defaults` (24/2/24/24, null templates)
  - `test_settings_forbidden_for_recruiter` (403)
  - `test_settings_validation` (second ≥ first → 422; 0 or 169 → 422; a draft or personal template → 422)
  - `test_settings_saved_and_audited`
  - the migration test (single head, columns exist)
- [ ] Run them: FAIL. Implement. Run them: PASS. Commit.

### Task 2: Confirmation template on schedule and reschedule
**Files:** `app/schemas.py` (`template_id: UUID | None = None` on `RecInterviewCreate` and `RecInterviewReschedule`), `app/services/interviews.py` (`notify(..., template=None)`), and `app/api/recruiter_interviews.py`.

**Consumes:** `approved_template(db, id, field="template_id", kind="interview_confirmation")`, plus `recruiter_messages.party_values`, `context_values` and `rendered`.

- [ ] Tests:
  - `test_confirmation_uses_template` (the candidate's and the contact's bodies start with the rendered text, the details follow, `template_id` is stored and `last_used_at` is set)
  - `test_confirmation_template_must_be_approved` (422)
  - `test_no_template_keeps_standard_text`
  - `test_reschedule_with_template`
- [ ] RED, GREEN, commit.

### Task 3: Reminders sweep, re-arm and worker
**Files:** `interview_automation.py` (`arm(interview, now)`, `run_reminders(now=None) -> dict`), `interviews.py` (`insert` and `reschedule` call `arm`), `worker.py` (task plus beat `crontab(minute="*/15")`).

- [ ] Tests:
  - `test_reminder_sent_once`
  - `test_both_slots_due_sends_one`
  - `test_reschedule_rearms`
  - `test_reschedule_inside_window_stamps`
  - `test_reminder_skips_do_not_contact`
  - `test_archived_reminder_template_falls_back`
  - `test_reminder_off_when_null`
- [ ] RED, GREEN, commit.

### Task 4: Feedback chase and escalation
**Files:**
- `interview_automation.py`: `run_feedback_chase(now=None) -> dict`
- `notifications/events.py`: `it.interview.feedback_escalated` in `EVENTS` and `RECRUITMENT_EVENTS`
- `worker.py`: beat `crontab(minute=20)`

- [ ] Tests:
  - `test_chase_creates_follow_up`
  - `test_escalates_to_team_lead`
  - `test_escalation_falls_back_to_managers`
  - `test_feedback_recorded_stops_escalation`
  - `test_closed_follow_up_no_escalation`
  - `test_reruns_add_nothing`
- [ ] RED, GREEN, commit.

### Task 5: Web UI
**Files:**
- `lib/recruiterInterviews.ts`: `AUTOMATION_URL`, `confirmationTemplates()` fetch helper
- `components/RecruiterInterviewForm.tsx` and the `RescheduleForm` in `RecruiterInterviewItem.tsx`: the select
- Create `components/InterviewAutomationSettings.tsx`
- `app/recruiter/interviews/page.tsx`: render it for managers
- Tests: `tests/components/InterviewAutomationSettings.test.tsx`, and an extension of the form test

- [ ] Vitest: the select is hidden when Notify is off and sends `template_id`; the panel saves and shows the 422 on its field. RED, GREEN, commit.

### Task 6: Docs, route matrix, e2e
- [ ] Update the docs: the backlog status, `DEC-SCOPE-421`, API §12LN, RBAC §2.313 and the rec-038 matrix rows.
- [ ] Write the Playwright spec `pob-022-interview-automation.spec.ts`.
