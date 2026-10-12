# mgmt-028 — Management to-do + staff "Management tasks" — design

- **Feature:** `mgmt-028` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-028). Depends on mgmt-001 (PR #243) and mgmt-027 (PR #248),
  both merged on `main@6c01db5a`.
- **Evidence:** `EVID-017` §28 (My Tasks; bands Overdue / Due Today / This Week / Completed; 7 examples; "Owner + Priority + Deadline +
  Status"), Management M13/M14 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`), the mgmt-002 audit helper (kind `mgmt.task` already registered
  as operational), mgmt-027 `STAFF_ROLES` and the decision line (`DEC-SCOPE-191`).
- **Decision:** one new DEC-SCOPE (number taken at merge). MT1–MT14 below answer Q-27 and the item's open points with **recommended
  defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

Partners and the super admin (M13 operational tier) keep a management to-do list: each task has a title, an owner (any active staff
user), a priority, a deadline and a status, and is shown in the §28 bands. Every staff member sees **their own** management tasks in a
shared "Management tasks" page linked from their portal's sidebar, and moves each task's status on. The same page folds in the
mgmt-027 decision lines they are responsible for, so one place lists everything management asked of them.

## 2. Decisions (MT1–MT14)

| # | Point | Answer |
|---|---|---|
| MT1 | Fields | title (2–200, required), owner (required, MT6), priority `high` / `medium` / `low` (default medium), deadline (required IST date), status, source, created_by, updated_by, completed_at, timestamps |
| MT2 | Status | `open` → `in_progress` → `completed`, plus `cancelled` (management only). Labels Open / In Progress / Completed / Cancelled. New tasks start `open`. Reopening a completed task clears `completed_at` |
| MT3 | Bands (Q-27) | IST calendar. **Overdue**: open/in progress, deadline < today. **Due Today**: deadline = today. **This Week**: today < deadline ≤ the Sunday of the current Monday–Sunday week. **Later**: after this week (added so no open task is hidden). **Completed**: completed in the last 7 IST days (today and the six before). Cancelled tasks are in no band; `band=cancelled` lists them for management |
| MT4 | Ordering | Within an open band: deadline, priority (high first), created_at, id. Completed: completed_at newest first |
| MT5 | Source | `manual` for every task mgmt-028 creates. The column's CHECK also allows `decision`, `meeting`, `plan` (+ nullable `source_id`) so mgmt-029 / mgmt-026 can link tasks without a migration; the API never accepts a source from the client |
| MT6 | Owner | Any **active staff user** (`STAFF_ROLES`, MD6). An inactive or non-staff owner → `422` on `owner_user_id`. An owner who has since been deactivated is not re-checked on other edits; the task is flagged `owner_active: false` and the management list shows "Owner inactive — reassign" |
| MT7 | Who writes | Operational tier (partner, super_admin) lists every task, reads, creates, edits (all fields, incl. cancel). The accountant and every other role → `403` on `/management/tasks*`. No delete (cancel instead) |
| MT8 | Deadline rule | A deadline set or changed by management can't be before today (IST) (`422`), and is at most 2 years ahead. An unchanged past deadline is never re-checked, so an overdue task stays editable |
| MT9 | Staff slice | `GET /me/management-tasks` lists the caller's own tasks (not cancelled; completed only for the last 7 days) with band and counts. `PATCH /me/management-tasks/{id} {status}` sets open / in_progress / completed. Another user's task, or an unknown id → `404` (AC3, no existence leak); a cancelled one → `409`. The staff serializer carries no creator or other people |
| MT10 | Decisions folded in | The staff page `/account/management-tasks` shows the tasks in bands, then a "Decisions" section reusing mgmt-027's `GET /me/management-decisions` and `MyManagementDecisions`. No task row is copied from a decision (one source of truth for each status) |
| MT11 | Notification | In-app + email (`queue_deliveries`) to the owner on assignment / reassignment, and when management changes the title, deadline, priority or status. Not when the owner is the actor. Body: "title — deadline — priority". Link `/account/management-tasks` |
| MT12 | Audit | Kind `mgmt.task` (operational → field names only). Verbs `create`; `complete` when the status becomes completed; `update` otherwise. The owner's status change is recorded with the owner as actor |
| MT13 | Concurrency | Every write locks the task row (`FOR UPDATE`) and commits once; an owner's status change racing a reassignment re-checks ownership after the lock (`404`) |
| MT14 | Navigation | Every staff portal's sidebar gets "Management tasks" → `/account/management-tasks` (IT trainer / placement / HR / counselor / admin, Overseas counselor / admin, BDM, BDM manager, telecaller, telecaller manager, recruiter, placement manager, partnership manager / head, the three school service teams, super admin). The Command Center's "To-do" entry goes live at `/management/tasks`; the accountant's management sidebar gets "Management tasks" |

## 3. Data (migration `0153_management_tasks`)

- `management_tasks`: id, title, owner_user_id → users, priority (CHECK), deadline (date), status (CHECK), source (CHECK, default
  `manual`), source_id (uuid, nullable), completed_at, created_by_user_id, updated_by_user_id, timestamps.
  Index `(owner_user_id, deadline, status)` (backlog), `(status, deadline)`.
- New table only; downgrade refuses while any task exists.

## 4. Components

- `services/management_tasks.py`: rules, bands (`band_of`, `band_filter`, `week_end`), serializers (management, owner),
  notification, list/page.
- `api/management_tasks.py`: `GET/POST /management/tasks`, `GET /management/tasks/options`, `GET/PATCH /management/tasks/{id}`;
  `me_router`: `GET /me/management-tasks`, `PATCH /me/management-tasks/{id}`.
- Web: `lib/managementTasks.ts` (types, band labels, grouping, links); components `ManagementTaskBands` (band sections, shared),
  `ManagementTaskForm`, `ManagementTasks` (management list), `MyManagementTasks` (owner rows); pages `/management/tasks`,
  `/management/tasks/new`, `/management/tasks/[id]/edit`, `/account/management-tasks`. `lib/navigation.ts` (MT14), `lib/management.ts`.

## 5. Error handling

`401` signed out; `403` outside the operational tier; `404` unknown task, or another user's task on `/me`; `409` a cancelled task on
`/me`; `422` field rules (field-located). Pages show the access card on 401/403 and "Tasks are unavailable right now" otherwise.

## 6. Testing

- Backend `tests/test_mgmt_028_tasks.py`: band_of / week_end with fixed IST days (AC1, incl. Sunday and Monday edges); API bands
  relative to `india_today()`; completing an overdue task moves it to Completed (AC2); staff A can't list or PATCH B's task (404, AC3);
  cancelled 409; inactive / non-staff owner 422; past deadline 422; accountant / BDM 403 on management routes; notifications on assign,
  change, reassign, none on the owner's own update; audit verbs; migration up/down.
- Web vitest: `managementTasks.test.ts` (grouping, labels), `ManagementTasks.test.tsx` (bands render, empty state, owner status update,
  form errors), `navigation` test for the staff entries.
- Playwright `mgmt-028-tasks.spec.ts`: the partner adds "Approve marketing budget" for a staff user; that user sees it in Management
  tasks under Due Today / This Week and completes it; it moves to Completed.
