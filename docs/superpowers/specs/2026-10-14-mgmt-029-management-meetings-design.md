# mgmt-029 — Management meetings + minutes chain — design

- **Feature:** `mgmt-029` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-029). Depends on mgmt-027 (PR #248) and mgmt-028 (PR #250),
  both merged on `main@8f66a2b6`. Re-chained after mgmt-015 (`0159`) and mgmt-026 (`0160`): `DEC-SCOPE-214`, API §12EB, RBAC §2.139.
- **Evidence:** `EVID-017` §29 (source lines 1133–1155: "Meeting Calendar"; Partner / Department / School / University / Agent /
  Recruiter meetings and Marketing reviews; "Every meeting should connect to: Meeting → Minutes → Decision → Task → Deadline →
  Completion"), §31's "📅 Today's Meetings" home panel (line 1227, built by mgmt-031 from this item), Management M13/M14
  (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`), mgmt-027 (`DEC-SCOPE-191`) and mgmt-028 (`DEC-SCOPE-193`, MT5 reserved `source = meeting`).
- **Decision:** one new DEC-SCOPE (number taken at merge). MM1–MM14 below answer Q-28 and the item's open points with **recommended
  defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

Partners and the super admin (M13 operational tier) schedule management meetings of the seven §29 kinds on a meeting calendar, with
participants, agenda and an online link. After the meeting they record the minutes and, from the minutes, create the mgmt-027
decisions and mgmt-028 tasks that came out of it. The meeting page shows the whole chain — each decision with its responsible person,
deadline and status, the tasks under it, the meeting's own tasks — and rolls the completion up ("3 of 5 completed"). Participants see
the meetings they are invited to (time, place, link, agenda; never the minutes) in their Management tasks page.

## 2. Decisions (MM1–MM14)

| # | Point | Answer |
|---|---|---|
| MM1 | Kinds | The 7 §29 values in source order and wording: `partner` Partner meeting, `department` Department meeting, `school` School meeting, `university` University meeting, `agent` Agent meeting, `recruiter` Recruiter meeting, `marketing_review` Marketing review |
| MM2 | Fields | title (2–200, required), kind (required), starts_at (required, minutes only, IST in the web), mode `Online` / `Phone` / `In person` (the shared `APPOINTMENT_MODES`, default Online), location (≤ 200, optional), meeting link (MM3), agenda (≤ 5 000, line breaks kept, optional), participants (MM5), minutes (MM6), status (MM4), created_by, updated_by, minutes_recorded_at, timestamps. No duration (rec-028 MT3) |
| MM3 | Link (Q-28) | **Typed, as elsewhere:** an optional `http(s)` URL ≤ 500 (`LeadApptLink`, tel-016 AP7 / rec-028 MT4); any other scheme → `422` on `meeting_url`. Rendered as a link with `rel="noopener noreferrer"` |
| MM4 | Status | `scheduled` → `completed` (recording minutes, MM6) or `cancelled` (management, by `PATCH status`; final). Labels Scheduled / Completed / Cancelled. A completed meeting can't be cancelled (`409`); a cancelled one can't be changed (`409`) |
| MM5 | Participants | **Staff users only** (mgmt-027 MD2/MD6: active `STAFF_ROLES`), 0–30, replaced as a whole on edit. An inactive or non-staff user → `422` on `participant_ids`. A stored participant since deactivated stays |
| MM6 | Minutes (Q-28) | **Free text + the decisions and tasks list.** `POST /management/meetings/{id}/minutes {minutes}` (2–20 000 characters, line breaks kept) records them, sets `completed` and stamps `minutes_recorded_at` the first time; later posts replace the text (an edit). Allowed only once the meeting has started (`starts_at ≤ now`, else `409`), never on a cancelled meeting (`409`) |
| MM7 | Time window | `starts_at` set or changed must be within 366 days before or after now (`422` on `starts_at`), so a meeting held earlier can be recorded afterwards. A changed time on a completed meeting → `409` (the minutes belong to the time it was held) |
| MM8 | Decisions from the minutes | `POST /management/meetings/{id}/decisions {decision, responsible_user_id?, deadline?, topic?}` creates a mgmt-027 discussion with `meeting_id` = the meeting: topic = the given topic or the meeting title, discussion date = the meeting's IST day, participants = the meeting's current participants who are still active staff, status open, `points` = none (the minutes stay on the meeting). mgmt-027's rules, notification (MD9) and audit (`mgmt.decision create`, as on mgmt-027's own create) apply unchanged. Needs recorded minutes (`409` otherwise) |
| MM9 | Tasks from the minutes | `POST /management/meetings/{id}/tasks {title, owner_user_id, priority, deadline, decision_id?}` creates a mgmt-028 task: `source = meeting`, `source_id` = the meeting; with `decision_id` (a decision of this meeting, else `422` on `decision_id`) `source = decision`, `source_id` = that decision. mgmt-028's rules (MT6/MT8), notification (MT11) and audit (`mgmt.task create`) apply unchanged. Needs recorded minutes (`409`). The client never sends `source` on `/management/tasks` (MT5 unchanged) |
| MM10 | Chain and roll-up (AC) | The meeting detail carries `decisions` (each: id, decision, responsible, deadline, status, its tasks) and `tasks` (linked to the meeting directly), each task with owner, deadline, priority, status. `progress` = {done, total}: every non-cancelled decision and task, done = completed. The page shows "Meeting → Minutes → Decisions → Tasks" with each item's deadline and status and "N of M completed" |
| MM11 | Calendar + Today | `GET /management/meetings?date_from&date_to` lists meetings whose IST day is in the range (≤ 62 days, `422` otherwise), by start time; `kind` and `status` filter. Without dates: today's IST meetings ("Today's meetings"). The page has a Today's meetings panel and a Week (Mon–Sun, every day) / Month (days with meetings only) calendar (upc-011 CL13 layout: a list of days, plain links, reflows on a phone). Cancelled meetings are listed with their status |
| MM12 | Who | Operational tier (partner, super_admin) lists, reads, creates, edits, records minutes, creates decisions/tasks. The accountant and every other role → `403` on `/management/meetings*`. No delete (cancel instead). A participant's slice: `GET /me/management-meetings` lists the caller's meetings starting from the last 7 IST days on (any status, by start time, at most 100) — id, title, kind, starts_at, mode, location, meeting_url, agenda, status; never minutes, other participants or the creator |
| MM13 | Notification | In-app + email (`queue_deliveries`) to each participant added (new meeting or added later), and to every current participant when the time changes or the meeting is cancelled. Never the actor. Body: "title — date time IST — kind". Link `/account/management-tasks#meetings` |
| MM14 | Audit, concurrency, recurrence | Kind `mgmt.meeting` (operational → field names only): `create`; `complete` when minutes are first recorded; `update` otherwise (incl. minutes edits, cancel). Every write locks the meeting row (`FOR UPDATE`) and commits once; creating a decision/task locks the meeting first so a racing cancel can't slip in. **No recurrence** (backlog edge case: "no recurrence, or simple weekly" — the simpler answer); a weekly partner meeting is scheduled each time |

## 3. Data (migration `0161_management_meetings`)

- `management_meetings`: id, title, kind (CHECK), starts_at (timestamptz), mode (CHECK), location, meeting_url, agenda, minutes,
  minutes_recorded_at, status (CHECK, default `scheduled`), created_by_user_id, updated_by_user_id, timestamps. Index `(starts_at)`,
  `(status, starts_at)`.
- `management_meeting_participants`: (meeting_id → cascade, user_id → users RESTRICT) primary key; index `(user_id)`.
- `management_discussions.meeting_id` (uuid, nullable, → management_meetings RESTRICT) + index. Existing rows stay null.
- Downgrade refuses while any meeting exists; then drops the column and the tables.

## 4. Components

- `services/management_meetings.py`: rules (MM2–MM7), participants, serializers (management, participant), chain + progress (MM10),
  notification (MM13), audit.
- `api/management_meetings.py`: `GET/POST /management/meetings`, `GET /management/meetings/options` (reuses discussions' staff list),
  `GET/PATCH /management/meetings/{id}`, `POST …/{id}/minutes`, `POST …/{id}/decisions`, `POST …/{id}/tasks`; `me_router`:
  `GET /me/management-meetings`.
- Reuse: `management_discussions.check/set_participants/notify_after_write/audit/staff_ids/person/options/require_operational`,
  `management_tasks.check/set_status/notify_after_write`, `management_audit.record` (+ kind `mgmt.meeting`).
- `DiscussionOut` gains `meeting_id` (nullable; additive). The discussion page links "From meeting" when set.
- Web: `lib/managementMeetings.ts` (types, labels, ranges via `bdmCalendar`/`partnershipCalendar` helpers, links); components
  `ManagementMeetingCalendar` (week/month list of days), `MeetingForm`, `MeetingChain` (minutes + decisions + tasks, client),
  `MyManagementMeetings`; pages `/management/meetings`, `/management/meetings/new`, `/management/meetings/[id]`,
  `/management/meetings/[id]/edit`; `/account/management-tasks` gains a Meetings section; `lib/management.ts` gives the Command Center
  "Meetings" entry its href.

## 5. Error handling

`401` signed out; `403` outside the operational tier; `404` unknown meeting; `409` cancelled / completed-time-change / minutes before
the start / chain before minutes; `422` field rules (field-located). Pages show the access card on 401/403 and "Meetings are
unavailable right now" otherwise; the calendar shows "Unable to load the calendar" with a Try again link.

## 6. Testing

- Backend `tests/test_mgmt_029_meetings.py`: create with the 7 kinds; link scheme 422; participants non-staff 422; window 422;
  calendar range + IST day boundaries + default today; minutes before start 409; minutes complete + audit `complete`; edit minutes
  `update`; decision from minutes (meeting_id, participants, notification) and task from minutes (source meeting / decision);
  decision_id of another meeting 422; chain before minutes 409; **AC: detail shows decisions and tasks with progress rolled up**
  (completing a task via `/me` moves the count); cancel 409 paths; accountant / BDM 403; participant `/me` slice keys (no minutes);
  notifications. Migration test: chain after 0158, model ↔ migration CHECKs, up/down + refusal.
- Web vitest: `managementMeetings.test.ts` (ranges, labels, progress text), `ManagementMeetings.test.tsx` (calendar render/empty/error,
  form validation, chain rendering + forms).
- Playwright `mgmt-029-meetings.spec.ts`: the partner schedules a partner meeting, records minutes, adds a decision and a task; the
  meeting page shows the chain with "0 of 2 completed"; the task owner completes the task in Management tasks; the meeting shows
  "1 of 2 completed".
