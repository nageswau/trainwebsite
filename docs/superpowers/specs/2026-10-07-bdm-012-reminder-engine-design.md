# bdm-012 — Reminder engine (design)

Decision: `DEC-SCOPE-102` (R1–R12, agent-recommended defaults; the owner asked the session to proceed on recommended answers —
owner confirmation pending). Evidence: `EVID-016` §6 (L198–227), §7 (L229–248), §10 (L339–369), §4 Common (L1254–1334) →
`BDM_CRM_BACKLOG.md` §bdm-012 (AC1–AC6); `DEC-SCOPE-055` D6 (in-app + email, deep links need login, no WhatsApp), D18 (Q-09 timings),
D19 (Q-10 MoU timings), D29 (nothing to organization contacts).

Dependencies (all merged on `main`): bdm-006 appointments, bdm-010 trips, bdm-005 MoUs, bdm-008 follow-ups/tasks, bdm-011 trip
anchors, bdm-025 handover (owners are read at fire time).

## 1. Scope

**In:** one periodic Celery task (every 5 minutes) that creates in-app notifications + an email delivery for six reminder kinds;
an SMTP BDM reminder email with deep-link buttons; `?action=confirm|reschedule|cancel` on the BDM appointment page; an `id` anchor on
the organization MoU section; the BDM notifications page's empty text.

**Out:** manager digests; WhatsApp / SMS (D6); reminders to organization contacts (D29); a reminder settings UI; external calendars;
any new API route; any change to the appointment / trip / MoU / task rules.

## 2. Decisions (DEC-SCOPE-102)

| # | Question | Recommended answer |
|---|---|---|
| R1 | "Exactly once" store | Reuse AGN-017's `notifications.dedupe_key` + partial unique index (`ux_notifications_dedupe_key`), key `bdm012:{kind}:{entity_id}:{fire_key}`, inserted with `ON CONFLICT DO NOTHING`. The backlog's `bdm_reminders_sent` table would duplicate that guarantee; **no migration** |
| R2 | Cadence | Beat entry `bdm012-reminders`, every 300 s, task `app.worker.send_bdm_reminders_task` |
| R3 | Kinds and times (IST, D18/D19) | `appointment_day_before` 09:00 the IST day before; `appointment_hour_before` exactly `starts_at − 1 h`; `trip_day_before` 09:00 the day before `travel_date`; `task_due` 09:00 on `due_on` (follow-ups and tasks); `mou_follow_up` 09:00 on day 5, 10, 15… after the IST date of `status_changed_at` while the current MoU stays Proposal Sent / Draft Shared; `mou_renewal` 09:00 on `valid_until − 30 days` for a current Active MoU |
| R4 | Catch-up (beat down) | A 09:00 reminder can still fire later the **same IST day** (the hour-before one until the start). After that it is not sent; each run logs its counts |
| R5 | Which records fire | Appointments `scheduled / confirmed / rescheduled`; trips `approved` + `planned`; tasks `open`; MoUs current, organization not archived. Cancelled / completed / no-show / done never fire (AC2) |
| R6 | Recipient | The owner **at fire time**: `bdm_appointments.bdm_user_id`, `bdm_trips.bdm_user_id`, `bdm_tasks.assignee_user_id`, the MoU organization's `assigned_bdm_user_id`; only an active user. The dedupe key has no user, so a reminder already sent is not re-sent after a reassignment |
| R7 | Rescheduling | `fire_key` = the event time (`starts_at` UTC ISO, `travel_date`, `due_on`, `status_changed_at`+day count, `valid_until`), so a new time is a new reminder (AC3) |
| R8 | Channels | In-app + email only (`channels=["email"]`), even for users opted in to WhatsApp / SMS (D6) |
| R9 | Email | SMTP through `mailer.send_bdm_reminder_email` (delivery `context = {"kind": "bdm_reminder", "links": [...]}`). Unconfigured SMTP → `not_configured`, no webhook fallback; the in-app row always exists. SMTP errors → ENH-014 retries, then `failed` with the error on the row (AC5) |
| R10 | Deep links | Appointment `/bdm/appointments/{id}?action=confirm|reschedule|cancel` (Reschedule / Cancel open their form; Confirm focuses the Confirm button — **a link never changes data**); trip `/bdm/travel/{id}#trip-appointments|#trip-costs|#trip-remarks`; MoU `/bdm/organizations/{org}#org-mou`; task `/bdm/follow-ups?kind=…`. The in-app `action_url` is the entity page without an action. Email links are `FRONTEND_URL` + path, no token; the pages require a session |
| R11 | Already confirmed | The day-before message for a Confirmed appointment drops "Please confirm your appointment." and the Confirm button |
| R12 | Bounds and failures | Each kind reads in keyset chunks of 200 and commits per chunk; each reminder runs in a savepoint — a failure is counted and logged with ids only and never stops the run. Logs never carry names or text |

## 3. Messages (source wording, minimal PII)

User-typed text (purpose, task title, location) is cleaned (control characters → spaces) and capped; contact phone / email are never
included. Times read `10:00 AM`, dates `08 Oct 2026` (IST).

| Kind | Title | Body | Email buttons |
|---|---|---|---|
| appointment_day_before | Appointment reminder | `Tomorrow at 10:00 AM. Organization: ABC College. Contact: Mr. XYZ. Purpose: … Location: Vijayawada. Please confirm your appointment.` | Confirmed / Reschedule / Cancel |
| appointment_hour_before | Appointment in 1 hour | `Your appointment with ABC College is at 10:00 AM. Location: Vijayawada.` | View appointment |
| trip_day_before | Travel reminder | `Tomorrow (08 Oct 2026): travel to Vijayawada. BDM: Name. Purpose: … Appointments: 3.` | View Appointments / View Expenses / Add Remarks |
| mou_follow_up | MoU follow-up | `ABC College: the proposal was sent 5 days ago. Follow up with the contact person.` (Draft Shared: "the draft was shared") | View MoU |
| mou_renewal | MoU renewal due | `ABC College: the MoU is valid until 07 Nov 2026. Plan the renewal with the contact person.` | View MoU |
| task_due | Follow-up due today / Task due today | `{title}. Organization: X. Due 07 Oct 2026.` | View follow-ups |

## 4. Components

- `app/services/bdm_reminders.py` — `send_bdm_reminders(db, now=)` + `run_bdm_reminders()`; one finder per kind returning
  `Reminder(kind, entity_id, fire_key, user, title, body, url, links)`; `_remind` (savepoint + `pg_insert … on_conflict_do_nothing`
  + `queue_deliveries(..., context=..., channels=["email"])`). It imports AGN-017's `clean_text` pattern locally (no cross-domain import).
- `app/worker.py` — the task and the beat entry.
- `app/notifications/delivery.py` — `_send_email` routes `context.kind == "bdm_reminder"` to the mailer.
- `app/services/mailer.py` — `send_bdm_reminder_email` (text + HTML, every value escaped).
- Web: `app/bdm/appointments/[id]/page.tsx` reads `action`; `BdmAppointmentDetail` passes it on, shows a notice when the action is
  no longer available, and drops `?action` from the URL; `BdmAppointmentActions` opens the matching form or focuses Confirm;
  `BdmOrganizationMou` section gets `id="org-mou"`; `/bdm/notifications` empty text mentions reminders.

## 5. Security

No new endpoint, no token in any link, no action from a GET. Recipients are owners only (R6), never managers or contacts. The email
carries the organization and contact name (source requirement) but no phone / email. HTML email escapes every value. Logs carry ids
and counts only.

## 6. Acceptance criteria → tests

| AC | Test (`tests/test_bdm_012_*.py`, web `BdmAppointmentActions.test.tsx`) |
|---|---|
| AC1 each kind fires once at its time | per kind: nothing before the time, one at the time, content and link checked |
| AC2 cancelled / completed do not fire | cancelled, completed, no-show appointments; cancelled / unapproved trips; done tasks; status-changed MoUs |
| AC3 reschedule fires relative to the new time | starts_at moved → new reminder at the new time |
| AC4 re-running sends no duplicates | second run creates nothing; two concurrent runs create one |
| AC5 email failure recorded | SMTP raises → delivery `retrying` → `failed` with error; not configured → `not_configured`; in-app row kept |
| AC6 deep links open the right dialog | web unit tests for `action=reschedule|cancel|confirm` + unavailable notice; Playwright opens the email link |
| R6 reassignment / inactive owner | moved appointment reminds the new BDM only; inactive owner gets nothing |
