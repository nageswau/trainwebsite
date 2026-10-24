# ccrm-029 — Counselor tasks — design

**Backlog:** `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § `ccrm-029`. **Source:** Counselor CRM spec §11, §15 "Task / Activity", §18 AC 7
(UNVERIFIED); owner answers CC2 (no new roles), CC3 (Overseas Admin is the escalation point and team-wide view). **Decision:**
DEC-SCOPE-250 (planned; recheck main before PR). **Blocks:** ccrm-030 (rules create tasks), ccrm-031 (escalation), ccrm-032, ccrm-036.

## 1. Intent

A task list for the overseas counselor: things to do by a day, optionally about one lead, student or application. The counselor adds
tasks for themself; the Overseas Admin adds tasks for any overseas counselor and sees everyone's. "My tasks" groups them as Overdue /
Today / Upcoming and, for AC 7 ("counselors can see their own tasks and overdue follow-ups"), also lists the counselor's overdue lead
follow-ups (ccrm-003).

Non-goals: rules that create tasks (ccrm-030 — the `source` column is ready for it), escalation (ccrm-031), dashboard tiles (ccrm-032),
reports (ccrm-036), reminders/e-mails about due tasks (ccrm-030).

## 2. Builder's calls (owner pre-authorised recommended defaults; `NEEDS_CONFIRMATION` until the owner confirms)

| ID | Question | Call |
| --- | --- | --- |
| T1 | Due as date or date-time? | **IST date** (`due_on`), like mgmt-028. Bands are IST days. From today to two years ahead when set or changed. |
| T2 | Statuses and moves | `open`, `done`, `cancelled`. open→done (stamps `completed_at`), done→open (undo, clears it), open/done→cancelled. **Cancelled is final** (409). |
| T3 | Who edits what | Counselor: creates for self only; changes status of any own task; edits title/due/priority/link only on tasks they created. Overseas Admin (and Super Admin): creates for any active overseas counselor, edits any field of any task incl. reassigning it. |
| T4 | Link | At most one of lead / student / application (DB CHECK). Must be in the **assignee's** scope when set or changed: lead = handed to them (owner + division); student = csc-001 visible students; application = assigned to them. Out of scope = 422 on `link`. A later reassignment keeps the link. |
| T5 | Notification | When someone other than the assignee creates, reassigns or changes a task, the assignee gets an in-app notification (+ opted-in channels via `queue_deliveries`). The counselor's own changes notify nobody. |
| T6 | "My tasks" bands | Overdue / Today / Upcoming (open tasks), then Done in the last 7 days (so a mistaken "done" can be undone). Cancelled hidden. |
| T7 | Overdue follow-ups (AC 7) | New `GET /counselor/follow-ups?view=day|overdue` — the counselor's own lead follow-ups (counselor_scope), reusing tel-011's list. Shown under "My tasks". |
| T8 | Audit / logs | `AuditLog` rows `counselor_task.create` / `update` / `complete` / `reopen` / `cancel`, field names only. Logs carry ids and field names, never titles. |

## 3. Data model (migration `0174_counselor_tasks`, after `0173_checklist_templates`)

`counselor_tasks`: `id` uuid pk; `title` varchar(200); `counselor_user_id` fk users RESTRICT; `due_on` date; `priority` varchar(8)
CHECK high/medium/low default medium; `status` varchar(10) CHECK open/done/cancelled default open; `source` varchar(10) CHECK
manual/rule default manual; `rule_key` varchar(60) null (ccrm-030); `lead_id` fk enquiries null, `student_user_id` fk users null,
`application_id` fk overseas_applications null — CHECK `num_nonnulls(lead_id, student_user_id, application_id) <= 1`;
`completed_at`, `cancelled_at` timestamptz null; `created_by_user_id`, `updated_by_user_id` fk users; timestamps. Index
(`counselor_user_id`, `status`, `due_on`). FKs on the links are `ON DELETE SET NULL`.

## 4. API (`/api/v1`, API_CONTRACT §12FC)

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| GET | `/counselor/tasks?band=&counselor_id=&limit=&offset=` | counselor (own only; `counselor_id` ignored), overseas_admin, super_admin | Without `band`: overdue+today+upcoming+done(7d). `band=cancelled` lists cancelled. `counts` per band. |
| GET | `/counselor/tasks/options?counselor_id=` | same | `counselors` (admin only: active overseas counselors) and `links` (leads, students, applications in the assignee's scope; 200 each, newest first). |
| POST | `/counselor/tasks` | same | 201. Counselor: `counselor_user_id` must be self or omitted. |
| GET | `/counselor/tasks/{id}` | same | Counselor: another counselor's task = 404. |
| PATCH | `/counselor/tasks/{id}` | same | Partial; nothing changed = nothing recorded. Row lock. |
| GET | `/counselor/follow-ups?view=day|overdue&day=` | overseas counselor | T7. |

Other roles: 403. An IT counselor: 403 (overseas only).

## 5. UI

- `/overseas/counselor/tasks` ("Tasks" in the counselor sidebar): add-task form (title, due, priority, optional link), the bands with a
  status control per task (Done / Reopen / Cancel) and an edit form for own-created tasks, then "Overdue follow-ups" linking to the lead.
- `/overseas/admin/counselor-tasks` ("Counselor tasks" in the admin sidebar): counselor filter + band filter (All / Overdue / Today /
  Upcoming / Done / Cancelled), the same list with the counselor's name, and the add/edit form with a counselor picker.
- Loading = server-rendered; empty, error (role="alert") and success (role="status") messages; keyboard-only operable; mobile single column.

## 6. Tests

Backend `tests/test_ccrm_029_counselor_tasks.py` (create/self-only, admin-for-counselor, link scope, bands, status moves, cancelled final,
edit rights, notification, 403/404 matrix, follow-ups route) and `tests/test_ccrm_029_migration.py`. Frontend unit tests for the lib
helpers and the task list component; Playwright `ccrm-029-counselor-tasks.spec.ts`.

## 7. Regression risks

tel-011 follow-up lists (`list_page` gains an optional "whose follow-ups" filter; the telecaller default is unchanged); sidebar
navigation (two new links); migration chain (parallel ccrm-007/ccrm-021 also claim 0174 — re-chain at merge time).
