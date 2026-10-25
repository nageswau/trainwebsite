# ccrm-030 — Counselor reminder and trigger engine (design)

- **Feature:** `ccrm-030` (docs/delivery/COUNSELOR_CRM_BACKLOG.md). **Decision:** `DEC-SCOPE-268`. **Migration:** `0189_counselor_reminders`.
  **API:** §12FU. **RBAC:** §2.182.
- **Source:** Counselor CRM Specification (UNVERIFIED) §11 trigger table, §14 "Deadline alerts — trigger configurable reminders before
  application, offer, deposit and visa dates", AC 12 "Notifications and deadlines are tested with sample records before go-live".
- **Dependencies (all merged):** ccrm-003 (lead next action), 013 (decision_due_on), 015 (on hold review date), 020 (student document
  requests with due date), 024 (offer conditions), 025 (deposit records), 026 (visa appointment), 029 (counselor tasks `source='rule'`).
- **Owner instruction:** proceed with recommended answers. Every choice below marked RM-n is the builder's call, `NEEDS_CONFIRMATION`.

## Intent

Counselors miss dates because nothing reminds them: the only daily reminder job (AGN-017) covers agency applications and tells agents.
ccrm-030 adds one rule catalogue, configured by the Overseas Admin, that turns lead and application dates into counselor tasks (ccrm-029)
or notifications, and (where the rule says so) reminds the student.

## Rules (RM1 — catalogue and defaults)

| key | trigger | action | offset (default, range) | student |
|---|---|---|---|---|
| `first_contact` | a lead is handed to a counselor (tel-018 handover, or the admin sets `owner_id`) | task "First contact" due today + offset | 1 day (0–30) | — |
| `no_response` | a counselor's lead in Contacted / Qualified / Interested / Follow-up / Counselling Completed has had no stage change and no call for *offset* days, and no next action due today or later | task "Follow up — no response" | 3 days (1–60) | — |
| `document_overdue` | an open document request to a direct student (ccrm-020) is *offset* days past its due date | task "Chase overdue document" + student reminder | 0 days after (0–30) | default on |
| `application_deadline` | an application not yet submitted (pre-offer stage, no `submitted_on`) has its application deadline within *offset* days | notify counselor | 7 days before (0–60) | — |
| `decision_overdue` | a submitted application (pre-offer stage, `submitted_on` set) is *offset* days past `decision_due_on` | task "Chase university decision" | 0 days after (0–30) | — |
| `offer_deadline` | the active offer is undecided (`considering`) and its deadline is within *offset* days | notify counselor + student | 3 days before (0–60) | default on |
| `deposit_due` | the deposit record (ccrm-025) is required and pending, due within *offset* days | notify counselor + student | 3 days before (0–60) | default on |
| `condition_due` | an open condition of the active offer is due within *offset* days | notify counselor; student when the condition's owner is the student | 3 days before (0–60) | default on |
| `visa_appointment` | the visa case has an appointment within *offset* days and no decision | notify counselor (+ student when on) | 2 days before (0–30) | default off |
| `hold_review` | the application is On Hold and its review date is within *offset* days | task "Review on-hold application" for the hold owner (else the counselor) | 0 days before (0–30) | — |

- **RM2 — catch-up, not exact-day:** a "before" rule fires on any day from (date − offset) up to the date, so a missed run still
  reminds. An "after" rule fires once (date + offset) has passed, but only for dates in the last 30 days (no flood of years-old items the
  first time a rule is switched on).
- **RM3 — de-duplication:** every firing claims a row in `counselor_reminder_log` with a unique `dedupe_key = rule:subject:anchor`, where
  the anchor is the date the reminder is about (deadline, due date, review date, last activity day; for `first_contact` the new owner).
  Insert … ON CONFLICT DO NOTHING — a re-run, a second beat process or the admin's "Run now" never creates a second task or notice. A
  changed date is a new anchor and so a new reminder.
- **RM4 — recipients:** the counselor is the application's `counselor_id`, else (direct students) the student's csc-001 counselor, and
  must be an active overseas counselor; otherwise the firing is skipped (counted, nothing logged). The student is told only on direct
  applications (no `agent_student_id`) and only when their login is active. Agents are never told by ccrm-030: AGN-017 keeps agency
  deadline reminders unchanged, so nothing is sent twice.
- **RM5 — applications in scope:** outcome not terminal, not `withdrawn` / `enrolled`; On Hold applications only for `hold_review`.
  "Before the offer" means a status not in the offer stages, so a status outside the pipeline (seeded `university_review`) counts
  (browser QA-01). School-bridged applications with an overseas counselor are included; they have no student login to remind (QA-02).
- **RM6 — tasks:** `source='rule'`, `rule_key=<key>`, priority medium, link to the lead / application (student for document requests),
  created and updated by the counselor themself (the column is NOT NULL and there is no system user), so the counselor can edit or cancel
  it as their own (ccrm-029 T3). An AuditLog row `counselor_task.create` with `{"fields": [...], "rule": key}`.
- **RM7 — notices:** in-app + email + opted-in channels (`queue_deliveries`), titles from the catalogue, bodies with codes, university
  names and dates only — never names of people, notes or labels a user typed (AGN-017 §8). Task rules also send the counselor a notice.
- **RM8 — schedule:** beat daily 08:15 IST (`crontab(hour=2, minute=45)` UTC), after AGN-017's 08:00. `first_contact` is event-driven
  (runs inside the handover / admin write transaction); the job does not create first-contact tasks.
- **RM9 — configuration:** `counselor_reminder_rules` (one row per key, seeded by the migration; the service falls back to the code
  defaults for a missing row). The Overseas Admin (and Super Admin) edits `enabled`, `offset_days`, `notify_student` (only on rules with a
  student column). Each save is audited (field names only).
- **RM10 — AC 12 tooling:** the admin page has "Run reminders now" (same job, idempotent) and a "Recent reminders" list (last 50 log rows:
  rule, summary, task created, recipients, time) so sample records can be tested before go-live.

## Out of scope

Escalation of overdue tasks (ccrm-031), the counselor dashboard (ccrm-032), templates (ccrm-037), consent/opt-out (ccrm-040 — reminders
already respect channel opt-ins), WhatsApp/SMS providers (deliveries go through the existing dispatcher). Checklist items that are missing
without a request are not reminded (a request is how a counselor asks for a document — ccrm-020 R2). Cancelling a first-contact task when
the counselor logs a call is not automatic.

## Data

- `counselor_reminder_rules(rule_key PK varchar(40), enabled bool, offset_days int CHECK 0..60, notify_student bool,
  updated_by_user_id FK users NULL, created_at, updated_at)`; CHECK rule_key IN catalogue.
- `counselor_reminder_log(id uuid PK, rule_key varchar(40), dedupe_key varchar(200) UNIQUE, subject_id uuid, summary varchar(200),
  task_id FK counselor_tasks SET NULL, recipients int, created_at)`; index (created_at).

## API (§12FU)

- `GET /overseas-admin/reminder-rules` → `{rules: [...]}` (catalogue order, with label, description, action, timing, min/max, current
  values, `notify_student` null where not supported).
- `PUT /overseas-admin/reminder-rules/{key}` `{enabled, offset_days, notify_student?}` → the rule. 404 unknown key; 422 out of range or
  `notify_student` on a rule without a student column.
- `POST /overseas-admin/reminder-rules/run` → `{created, duplicate, skipped, failed, rules: {key: created}}`.
- `GET /overseas-admin/reminder-rules/log?limit=50&offset=0` → `{items, total, limit, offset}`.
- All: `overseas_admin` (division overseas) or `super_admin`; anyone else 403.

## UI

`/overseas/admin/reminder-rules` (nav "Reminder rules"): a table of rules (enabled toggle, offset input with unit, student toggle where
supported, Save per row with inline success/error), a "Run reminders now" button with a result line, and the recent reminders table with
an empty state. Existing `portal-content` / `form-grid` / `table` styles; responsive (table scrolls inside its wrapper on mobile).

## Tests

Backend `tests/test_ccrm_030_reminders.py`: each rule fires once with sample records (AC 12) and not on a re-run; window edges; terminal /
agency / inactive-counselor exclusions; student notified only where the rule and application allow; first-contact on handover and on admin
owner change (not on unchanged owner, not when disabled); admin routes (403 for counselor, 404/422, audit). Migration test. AGN-017
regression file runs unchanged. Web: vitest for the lib and component; Playwright spec for the admin page.
