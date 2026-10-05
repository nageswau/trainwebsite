# bdm-007 — Appointment outcome + meeting report (design)

- **Item:** `bdm-007` (`docs/delivery/BDM_CRM_BACKLOG.md` §4). Depends on bdm-006 (merged, `0070_bdm_appointments`).
- **Decision:** `DEC-SCOPE-070`. **Migration:** `0072_bdm_meeting_reports` (down_revision `0071_bdm_activities`).
- **Branch:** `feature/bdm-007-meeting-outcomes` from `origin/main` @ `2e057b3a`.
- **Evidence:** `EVID-016` `BDM Functionalities.md` (`DERIVED_BLUEPRINT`) §8 Appointment Outcome (250–283), Agent §C outcomes
  (637–653), §4 Common "Meeting Report" (1302–1318); backlog D18, Q-13/D22, AL-6 (Appendix B).
- **Skills applied:** superpowers:brainstorming, api-and-interface-design, frontend-ui-engineering, security-and-hardening.

## 1. Goal

After every meeting the BDM files a meeting report. Filing it is the only way an appointment becomes Completed. A follow-up
date creates exactly one follow-up. The author may correct the report on the IST day it was filed; after that it is read-only.
Past appointments still waiting for a report are visible as "Outcome pending" (the query bdm-023's alert AL-6 will reuse).

## 2. Scope

| In | Out (owner item) |
|---|---|
| `bdm_meeting_reports` (1:1 with a completed appointment), report on complete, same-day edit | Follow-up pages, manual tasks, completing tasks (bdm-008) |
| Minimal `bdm_tasks` table + one follow-up per report | Reminders (bdm-012) |
| Backfill: a legacy report (+ follow-up) for every appointment completed under bdm-006 | Manager dashboard alert tile (bdm-023) |
| `outcome_pending` row flag + list filter; detail-page report section; "Book the next meeting" link on Reschedule | "Not Interested → pipeline lost" (bdm-004, not on `main`) |

## 3. Owner decisions (2026-10-05, in-session, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| R1 | Where do follow-ups live (bdm-008 not built)? | **A minimal `bdm_tasks` table now** (bdm-008's shape); a unique source index guarantees one follow-up per appointment |
| R2 | Edit window (AC4) | **The IST day the report was filed** (bdm-009's activity rule) |
| R3 | Appointments already completed without a report | **Migrate them:** one legacy report each (+ a follow-up for a stored follow-up date); legacy reports are read-only |
| R4 | Outcome "Reschedule" | **No server action:** the detail page offers "Book the next meeting" (the existing booking form, organization prefilled) |
| R5 | Responsible person | **Free text** (≤ 200) |
| R6 | Required fields | **Outcome + Discussion**; the rest optional |
| R7 | Approach | **A:** report table holds the narrative; `outcome` / `next_follow_up_on` stay on `bdm_appointments` (one place each) |

**Defaults taken (not asked; consistent with bdm-006/009):** only the appointment's BDM files or edits (managers and
super_admin read); no idempotency key (the appointment row lock + state check makes a duplicate a 409); no ETag (not contracted;
the same author is the only writer); no general rate limiter (bounded by one report per appointment; bdm-006/009/010 precedent).

## 4. Data model (migration `0072_bdm_meeting_reports`)

### 4.1 `bdm_meeting_reports`

| Column | Type | Rule |
|---|---|---|
| `id` | uuid PK | |
| `appointment_id` | uuid FK → `bdm_appointments.id` RESTRICT, NOT NULL | `uq_bdm_meeting_reports_appointment` (1:1; race backstop) |
| `author_user_id` | uuid FK → `users.id` RESTRICT, NOT NULL | the appointment's BDM |
| `discussion` | varchar(4000) NULL | `ck_bdm_meeting_reports_discussion`: `legacy OR discussion IS NOT NULL` |
| `requirements` | varchar(2000) NULL | |
| `opportunity` | varchar(2000) NULL | |
| `next_action` | varchar(1000) NULL | |
| `responsible_person` | varchar(200) NULL | |
| `legacy` | boolean NOT NULL default false | true only for migration-created rows |
| `submitted_at` | timestamptz NOT NULL default now() | anchors the edit window |
| `created_at`, `updated_at` | timestamptz NOT NULL default now() | `TimestampMixin` |

`outcome` and `next_follow_up_on` stay on `bdm_appointments` with their bdm-006 CHECKs (completed ⇔ outcome; follow-up only
when completed; outcome in the catalogue). The report never copies them.

### 4.2 `bdm_tasks` (minimal; bdm-008 extends)

| Column | Type | Rule |
|---|---|---|
| `id` | uuid PK | |
| `kind` | varchar(20) NOT NULL | CHECK in (`follow_up`, `task`) |
| `title` | varchar(200) NOT NULL | bdm-007 writes `Follow up on APT-000123` (no organization name copied) |
| `due_on` | date NOT NULL | follow-ups are date-based (D18: reminded 09:00 IST on the day) |
| `organization_id` | uuid FK → `bdm_organizations.id` RESTRICT, NULL | |
| `source` | varchar(30) NOT NULL | CHECK in (`appointment_outcome`, `mou`, `manual`) |
| `source_appointment_id` | uuid FK → `bdm_appointments.id` RESTRICT, NULL | `uq_bdm_tasks_source_appointment`; CHECK `(source = 'appointment_outcome') = (source_appointment_id IS NOT NULL)` |
| `assignee_user_id` | uuid FK → `users.id` RESTRICT, NOT NULL | |
| `status` | varchar(20) NOT NULL default `open` | CHECK in (`open`, `done`, `cancelled`) |
| `completed_at` | timestamptz NULL | CHECK `(status = 'done') = (completed_at IS NOT NULL)` |
| `created_at`, `updated_at` | timestamptz | |

Index `ix_bdm_tasks_assignee_status_due (assignee_user_id, status, due_on)`.

### 4.3 Follow-up sync (one follow-up per appointment, ever)

| Event | Follow-up row |
|---|---|
| Report filed with a date | insert `open`, `due_on` = date |
| Report filed without a date | none |
| Edit: date changed | `due_on` = new date (the row stays `open`) |
| Edit: date cleared | `status = cancelled` |
| Edit: date set again (row exists, cancelled) | `status = open`, `due_on` = date |
| Edit: date set (no row yet) | insert |
| Any date change while the row is `done` (bdm-008) | 409 "This follow-up is already done" |

### 4.4 Migration

- Guard as 0070/0071: when `0001`'s `create_all` already built the tables (fresh database), skip the DDL but **still backfill**.
- Backfill (one `INSERT … SELECT` each, set-based, idempotent through `NOT EXISTS`):
  - every `completed` appointment without a report → report `legacy = true`, `author_user_id = bdm_user_id`,
    `submitted_at` = latest `bdm_appointment_events.created_at` with `to_status = 'completed'` (fallback `updated_at`);
  - every completed appointment with `next_follow_up_on` and no follow-up → `open` follow-up (past dates kept; bdm-008 shows
    them overdue).
- Columns of `bdm_appointments` are not touched. After upgrade: every completed appointment has exactly one report.
- Downgrade refuses while a non-legacy report exists ("Cannot downgrade 0072_bdm_meeting_reports: meeting reports exist …");
  legacy rows and their follow-ups are rebuilt from the appointment columns, so dropping them loses nothing.

## 5. API (`app/api/bdm_appointments.py`, `app/services/bdm_appointments.py`)

### 5.1 `POST /api/v1/bdm/appointments/{id}/complete` (changed — the AC1 contract change)

Body `BdmMeetingReportCreate` (`extra="forbid"`):

| Field | Rule |
|---|---|
| `outcome` | required, in the owner's type list (bdm-006 A8) |
| `discussion` | required, trimmed, 1–4000, multi-line (`\n` allowed, other control characters 422) |
| `requirements`, `opportunity` | optional, ≤ 2000, multi-line; blank → null |
| `next_action` | optional, ≤ 1000, multi-line; blank → null |
| `responsible_person` | optional, ≤ 200, single line; blank → null |
| `next_follow_up_on` | optional date (YYYY-MM-DD), on or after IST today |

Order (each refusal is one rule): scope → 404; `FOR UPDATE` on the appointment; owner (`bdm` and owns it) → 403; transition
→ 409 "Appointment is already …"; started → 422; outcome in list → 422; follow-up date → 422. Then, in **one transaction**: set
`outcome` / `next_follow_up_on` / status, insert the report (`submitted_at = db now`), apply §4.3, event, audit
`bdm_appointment.complete` (metadata adds `follow_up: bool`), commit, log. Response: the appointment envelope (200).

**Compatibility:** URL, method, status codes and response shape are unchanged; the body gains fields and `discussion` becomes
required, so an old client that sends only `{outcome}` gets 422 "Discussion is required". This is the change AC1 requires; the
only client is this web app (updated in the same change).

### 5.2 `PATCH /api/v1/bdm/appointments/{id}/report` (new)

Body `BdmMeetingReportUpdate` (`extra="forbid"`): any subset of §5.1's fields; omitted = unchanged; `outcome` and
`discussion` cannot be null (non-nullable types); `next_follow_up_on: null` clears it.

Order: scope → 404; `FOR UPDATE` appointment; owner → 403; no report (not completed) → 409 "This appointment has no meeting
report"; `FOR UPDATE` report; not editable (§5.4) → 409 "Meeting reports can only be changed on the day they were filed";
outcome in list → 422; a **changed** follow-up date before IST today → 422 (an unchanged past date is accepted); §4.3 (lock the
follow-up row `FOR UPDATE`). Values equal to the stored ones are not changes (no audit, no `updated_at` bump — bdm-006 R-A6).
Audit `bdm_appointment.report_update` with metadata `{fields: [...], follow_up: "created|moved|cancelled|reopened"|absent}`.
Response: the appointment envelope.

### 5.3 Reads (additive)

- `BdmAppointmentRow` gains `outcome_pending: bool` = status in Open (scheduled/confirmed/rescheduled) **and** `starts_at <=
  now`. (Completed always has a report; cancelled / no-show never need one.)
- `GET /bdm/appointments?outcome_pending=true|false` filters on the same expression (ANDed with scope; manager/super_admin too).
- `BdmAppointmentOut` gains:
  - `report: {discussion, requirements, opportunity, next_action, responsible_person, legacy, author: {id, full_name, active},
    submitted_at, updated_at} | null`
  - `follow_up: {id, due_on, status} | null`
  - `permissions.can_edit_report: bool` = owner and report exists and editable.
- Every reader of the appointment (owner, team manager, super_admin) reads the report; no new scope.

### 5.4 Edit window

`editable(report, now)` = not `legacy` and IST date of `submitted_at` == IST date of `now` (`now` = database clock, read once per
request). Single function, used by the PATCH check and by `permissions`.

### 5.5 Errors (unchanged conventions)

`{"detail": str}` for 403/404/409/service 422; FastAPI's list for schema 422. New messages: "Discussion is required",
"This appointment has no meeting report", "Meeting reports can only be changed on the day they were filed",
"This follow-up is already done", "<Field> contains invalid characters".

## 6. Transactions, concurrency, failure

- One commit per route; services never commit; audit rows in the same transaction (fail closed). Any exception before commit
  leaves nothing written (the session is discarded with the request).
- **Lock order: appointment → report → follow-up.** Every report/follow-up write holds the appointment lock first, so
  complete ∥ complete, complete ∥ cancel/no-show, edit ∥ edit serialize; the loser of a complete race re-reads `completed`
  → 409. `uq_bdm_meeting_reports_appointment` / `uq_bdm_tasks_source_appointment` are backstops (never reached by design).
- Midnight IST: the window and the follow-up rule use the one `db_now()` per request.
- Archived organization: completing / editing stays allowed (bdm-006: existing appointments stay manageable); the follow-up is
  still created (bdm-008 decides archive handling).

## 7. Security (security-and-hardening review)

| Concern | Control |
|---|---|
| Authentication | `get_current_user` (httpOnly, `SameSite=Lax` cookie); unchanged |
| Authorization / IDOR | every route resolves through `load_scoped` (out of scope = 404); writes need `require_owner` (403, logged as `bdm_appt_write_refused`); author == owner always |
| Role escalation / mass assignment | `extra="forbid"`; `author_user_id`, `legacy`, `submitted_at`, status, follow-up ids are server-owned |
| Input validation | lengths, enums, IST date rule, control characters at the schema boundary |
| XSS | React text rendering only (`white-space: pre-wrap`), no `dangerouslySetInnerHTML` |
| CSRF | JSON `POST`/`PATCH` under `SameSite=Lax`; no form-encoded endpoint |
| SQL injection | ORM / bound parameters; migration SQL has no input |
| Sensitive logs | logs and audit carry ids, outcome key, field names, follow-up action — **never** report text or responsible person |
| Secrets / tokens | none added |
| Rate limiting | none added (one report per appointment; same-day edits by one author) |
| Audit | `bdm_appointment.complete`, `bdm_appointment.report_update` |

## 8. Frontend (frontend-ui-engineering)

- **`BdmMeetingReportForm`** (renamed from `BdmAppointmentCompleteForm`, extended): Outcome (select, required), Discussion
  (textarea, required), Requirements, Opportunity, Next action (textareas), Responsible person (input), Next follow-up (date,
  min = IST today). Visible "(required)" labels, `maxLength` matching the API, a character hint on Discussion, `autoFocus` on
  Outcome, Escape cancels, submit disabled while busy ("Saving…"). Mode `complete` ("Save report and complete") and `edit`
  ("Save changes", prefilled). Field-level 422 messages via `fieldErrors`. **On failure the typed text stays** (the form is not
  closed); on a 409 the form stays open with "This appointment changed elsewhere — copy your notes, then reload" and a Reload
  button (refetch).
- **`BdmAppointmentDetail`:** the "Outcome" section becomes "Meeting report": Outcome, Discussion, Requirements, Opportunity,
  Next action, Responsible person, Next follow-up (+ "cancelled" when so), Filed by / at. Multi-line text keeps line breaks.
  Legacy reports say "Recorded before meeting reports — outcome only." An **Edit report** button (when `can_edit_report`) with
  the hint "You can change this report until midnight IST today." Outcome **Reschedule** on the BDM's page shows "Book the next
  meeting" → `/bdm/appointments/new?organization=<id>` (the existing prefill). An open, past appointment shows
  "Outcome pending — file the meeting report" (owner) / "Outcome pending" (manager) as text, not colour only.
- **`BdmAppointmentActions`:** the Complete button opens the report form; body = the report.
- **`BdmAppointmentsPanel`:** the Status filter gains "Outcome pending" (`status=outcome_pending` in the URL →
  `outcome_pending=true`; choosing it clears the From date, since pending rows are in the past); rows with `outcome_pending`
  show a text badge "Outcome pending" beside the status.
- Loading / empty / error states of pages and the list are unchanged (already present); the report section has no empty state
  (shown only when a report exists).
- Mobile: the form is single-column `.field` blocks (existing CSS); the `<dl>` grid wraps; no fixed widths.

## 9. Acceptance criteria (testable)

| AC | Criterion | Verified by |
|---|---|---|
| AC1 | Completed only through filing a report; `/complete` without `discussion` → 422; after the migration every completed appointment has exactly one report | API test; migration test |
| AC2 | Outcome lists: Agent §C (8) for agent BDMs, §8 (9) for school/college, on complete and on edit; foreign → 422 | API test; existing catalogue test |
| AC3 | A follow-up date creates exactly one follow-up; edits move / cancel / reopen that same row; never two | API + concurrency tests; DB unique index test |
| AC4 | The author edits on the IST filing day; the next IST day (and legacy) → 409, `can_edit_report=false`; non-author → 403 | API test (submitted_at moved back a day) |
| AC5 | Past open appointments carry `outcome_pending=true` and are returned by `outcome_pending=true` (team scope for managers); the badge shows; bdm-023 reuses the filter | API + component tests |
| AC6 | Outcome Reschedule creates nothing server-side; the BDM sees "Book the next meeting" | API + component tests |
| AC7 | Report text never appears in logs or audit metadata | API test inspecting audit rows / caplog |

Negative: report on a future appointment → 422; another BDM → 404 (out of scope) / same-team non-owner impossible (BDMs see
only their own); manager / super_admin write → 403; duplicate complete → 409.

## 10. Regression risks

1. `/complete` body change: `test_bdm_006_transitions.py`, `test_bdm_006_org_meetings.py`, `BdmAppointmentActions.test.tsx`,
   e2e `bdm-006-appointments.spec.ts` must send a discussion.
2. Migration tests: `test_bdm_009_migration.py` pins `0071` as the single head (relax to "on the chain"); the isolated-db
   fixtures of `test_bdm_002_migration.py` and `test_bdm_006_migration.py` drop dependent tables before downgrading (add
   `bdm_meeting_reports`, `bdm_tasks`).
3. `models.py` / `schemas.py` are shared single files; `BdmAppointmentComplete` is renamed → `test_bdm_006_schemas.py`.
4. Lock order (appointment first) must hold with `test_bdm_006_concurrency.py`.
5. `permissions` gains a key → web type `AppointmentPermissions` and test fixtures.
6. Organization Last/Next meeting (`bdm_organizations.meeting_columns`) — untouched; still reads `status`.

## 11. Testing (lite only; the owner runs the full suites)

- Backend new: `test_bdm_007_migration.py`, `test_bdm_007_schemas.py`, `test_bdm_007_reports.py`, `test_bdm_007_concurrency.py`.
- Backend updated: `test_bdm_006_transitions.py`, `test_bdm_006_org_meetings.py`, `test_bdm_006_schemas.py`,
  `test_bdm_006_migration.py`, `test_bdm_002_migration.py`, `test_bdm_009_migration.py`.
- Backend LITE = `tests/test_bdm_007_*.py tests/test_bdm_006_*.py tests/test_bdm_009_migration.py tests/test_bdm_002_migration.py`.
- Web: `BdmMeetingReportForm.test.tsx` (new), `BdmAppointmentActions.test.tsx`, `BdmAppointmentDetail.test.tsx`,
  `BdmAppointmentsPanel.test.tsx`, `tests/lib/bdmAppointments.test.ts`; `tsc --noEmit`; eslint on changed files.
- E2E: `bdm-006-appointments.spec.ts` updated and `bdm-007-meeting-reports.spec.ts` written; run during browser validation.
- Not claimed complete until browser validation and the independent Codex review.
