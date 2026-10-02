# AGN-016 — Agent Tasks & Follow-ups — Design

- **Feature:** `AGN-016` (backlog item `ang-016`, `docs/delivery/AGENT_CRM_BACKLOG.md`).
- **Decision:** `DEC-SCOPE-051` (provisional number — see §9), answers T1–T8 below (`EXPLICIT_APPROVAL`, owner in-session 2026-10-02).
- **Evidence:** `EVID-015` (`functionalities/edusphere_markdown/Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) names only
  "Tasks & Follow-ups" (Staff sidebar, §4, line 229) and "Pending Actions" (Master dashboard KPI, §2, line 43). Every rule below
  comes from the owner's answers, not from the source.
- **Requirement:** "Tasks & Follow-ups" (§4); "Pending Actions" KPI (§2).
- **Owner acceptance:** CRUD per scope; overdue = due before now and open; a reassigned student's open tasks follow the new owner.
- **Dependencies (merged):** AGN-001 (tenant), AGN-002/003 (staff, matrix), AGN-004 (students, G4 assigned-only scope), AGN-008
  (applications with `agent_student_id`).

## 1. Decisions (T1–T8)

| # | Question | Answer |
|---|---|---|
| T1 | Task owner / reassignment | **The task follows the student.** No assignee column: Staff see tasks of students assigned to them (G4); Masters see the agency's. Reassigning a student moves its tasks with no write to the task. |
| T2 | Delete | **Cancel only.** Status `open`, `done`, `cancelled`; no hard delete. |
| T3 | Due time | **`due_at` timestamptz, required.** Overdue ⇔ `status = open` and `due_at < now` (one `now` per request). |
| T4 | Linkage | **A student is required** (with or without a login). An application link is optional and must be the same student's, not withdrawn. An archived student's tasks are read-only (409) and leave the open counts. |
| T5 | KPI and navigation | **One "Pending actions" metric** (open tasks of active students in the caller's scope, SQL `COUNT`) on the existing agent dashboard for Master and Staff; the other metrics are unchanged. **"Tasks" in the nav for both roles.** Full dashboards stay with ang-018. |
| T6 | Edit rules | **Anyone in scope** (Master; the student's assigned Staff) creates, edits, completes and cancels. Done/cancelled are final (409). A past `due_at` is allowed on create (the UI warns). |
| T7 | Abuse cap | At most **100 open tasks per student** (409), checked under the agency lock. |
| T8 | Retry safety | `POST` is documented as not safe to retry (no `Idempotency-Key`); a duplicate is harmless and can be cancelled. The form guards double submits. |

Out of scope: notifications and reminders (ang-017), journey page (ang-015), dashboard redesign (ang-018), assignee other than the
student's owner, reopening, hard delete, bulk actions, any change to `OverseasApplication.next_action`.

## 2. Data model — table `agent_tasks` (migration `0058_agent_tasks`, provisional number)

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `agent_student_id` | UUID NOT NULL, FK `agent_students.id` RESTRICT | the only ownership link; fixed after create |
| `application_id` | UUID NULL, FK `overseas_applications.id` RESTRICT | |
| `title` | String(200) NOT NULL | |
| `notes` | Text NULL | ≤ 2000 (API) |
| `due_at` | timestamptz NOT NULL | |
| `status` | String(20) NOT NULL default `open` | CHECK `status IN ('open','done','cancelled')` |
| `closed_at` | timestamptz NULL | CHECK `(status = 'open') = (closed_at IS NULL)` and `(closed_at IS NULL) = (closed_by_user_id IS NULL)` |
| `closed_by_user_id` | UUID NULL FK `users.id` | |
| `created_by_user_id`, `updated_by_user_id` | UUID NOT NULL FK `users.id` | |
| `created_at`, `updated_at` | `TimestampMixin` | |

Index `ix_agent_tasks_student_status_due (agent_student_id, status, due_at)`; index on `application_id`. The migration only creates
the table (guarded, since `0001` builds a fresh database from the models); `downgrade()` refuses while rows exist (0057's idiom),
otherwise drops it. No existing row is read or written.

## 3. API — `/api/v1/workflows/overseas/agent/crm/tasks`

Conventions are the agent CRM's (Hyrum's law): snake_case, lowercase enums, FastAPI `{"detail": ...}` errors, pages
`{items, total, limit, offset}`, single objects `{"task": {...}}`. Gate = `api/agent_students._gate` (agent role, overseas
division, active agency; super_admin refused 403). Out of scope is **404**, never 403.

| Method / path | Body / query | Success | Errors |
|---|---|---|---|
| `GET /tasks` | `view` = `open` (default) \| `overdue` \| `done` \| `cancelled` \| `all`; `student` (UUID, optional); `limit` 1–100 (20); `offset` 0–10000 | 200 page | 403, 422 |
| `POST /tasks` | `agent_student_id`, `title`, `due_at`, `notes?`, `application_id?` | 201 `{task}` | 403; 404 "Student not found"; 409 "Unarchive this student first" / cap; 422 |
| `GET /tasks/{id}` | | 200 `{task}` | 403; 404 "Task not found" |
| `PATCH /tasks/{id}` | any of `title`, `notes`, `due_at`, `application_id` — **or** `status` (`done`\|`cancelled`) alone | 200 `{task}` | 403; 404; 409 "This task is closed" / archived; 422 |

- **Validation (Pydantic, `extra="forbid"`):** `title` via `clean_free_text(…, 200)`, required non-blank; `notes` via
  `clean_free_text(…, 2000)` (blank → null); `due_at` `AwareDatetime` (naive → 422); `status` `Literal["done","cancelled"]`;
  status together with any other field → 422; `title` and `due_at` cannot be cleared (null → 422). An empty PATCH is a 200 no-op.
- **Application link:** the application must be in the caller's `application_scope`, belong to the student (AGN-008 rule:
  `agent_student_id = student`, or a pre-AGN-008 row whose `student_id` is the student's login), not School-bridged and not
  `withdrawn`; otherwise 422 "Choose an application of this student". `null` clears it.
- **List order:** `open`/`overdue`: `due_at, id`; `done`/`cancelled`: `closed_at desc, id`; `all`: open first by `due_at`, then
  closed by `closed_at desc`. `open` and `overdue` leave out archived students' tasks unless `student` is given. `student` only
  filters inside scope (an out-of-scope id yields an empty page).
- **Task shape (allowlist):** `id, title, notes, due_at, status, overdue, student {id, full_name, status}, application {id,
  university} | null, assigned_to {code, full_name, status} | null, created_by, closed_by, closed_at, created_at, updated_at`.
  `created_by`/`closed_by` are names; no user id leaves the server.

## 4. Transactions, concurrency, scope

- Scope clause: `AgentTask.agent_student_id IN (SELECT agent_students.id WHERE student_scope(user))` — always in SQL.
- Every write: `lock_active_org` (agency lock, the order every agency write uses; it also serialises with assign and archive) →
  load the task (scoped) `FOR UPDATE` → load its student → checks → write + audit row → one commit. Create locks the student row
  through `_locked_row`.
- Two concurrent completes: the second waits for the row lock, then sees `done` → 409. A Staff member reassigned away mid-edit gets
  404 on the next write. An `IntegrityError` at commit (an FK or CHECK disagreeing with the checks) rolls back and answers 409
  "The task changed; reload and try again", never 500.

## 5. Audit, activity, logging

- Audit (same transaction, fail closed): `agent_student.task_add`, `task_update`, `task_complete`, `task_cancel`;
  `entity_type="agent_student"`, `entity_id` = the student; metadata = `task_id` and changed field **names** only — never title,
  notes or due values (they may hold student PII).
- `STAFF_ACTIVITY_ACTIONS` (AGN-021) gains the four actions; `lib/agentStaff.ts` gains their labels.
- Logs (`app.agent_tasks`): `agent_task_created|updated|completed|cancelled`, and `agent_task_write_refused` (warning) for a 409,
  with `org_id`, `actor_id`, `student_id`, `task_id`, field names — no free text.

## 6. Dashboard KPI

`services/portal._agent` dashboard: after "Applications", append `{"label": "Pending actions", "value": n}` where `n` is a SQL
`COUNT` of open tasks of active students in `student_scope(user)`. Same for Staff (own scope). The metric list order otherwise
unchanged; existing tests read metrics by label.

## 7. Frontend

Reuse first: `SearchableSelect`, `LocalTime`, `useFocusAfterRender`, `isPage`/`failureText` (`lib/apiErrors`), the shortlist
panel's loading/error/paging/inline-confirm pattern, `btn`/`grid`/`form-error`/`muted` classes. No new dependency.

- **Navigation:** `"tasks"` added to the `"overseas/agent"` list in `lib/navigation.ts` (both roles). `portal._agent` returns a
  header-only `tasks` payload (the Universities precedent), so the page gate is unchanged; `PortalPage` mounts
  `AgentTasksSection`.
- **`AgentTasksSection`:** h2 "Tasks & follow-ups", role-specific intro, the create form, the view filter as links (`?view=`,
  `aria-current`), and `AgentTasksPanel`.
- **`AgentTasksPanel({ view, studentId?, readOnly? })`:** `<ul>` of cards in `grid` (one column on phones). A card: title (h3/h6
  by context), student name, due time (`LocalTime`), an **"Overdue" text badge**, assigned staff, application, notes
  (`white-space: pre-wrap`). Actions: Mark done, Edit (inline `AgentTaskForm`), Cancel task (inline confirm). States: first load
  "Loading tasks…" (`aria-busy`); reload dims old data; empty text per view; load error `role="alert"` + Retry; 404/409 on an
  action → `aria-live` notice and reload; Previous/Next paging.
- **`AgentTaskForm` (create/edit):** student (`SearchableSelect`; fixed when given), title (required, 200), due date-time
  (`datetime-local`, sent as an ISO string with offset), application (optional select of the student's applications from
  `GET /applications?student=`), notes (2000, counter). Past due → inline hint. Submit disabled while busy; errors
  `role="alert"`; a 422 keeps the form open; Escape cancels editing; focus returns to the opener.
- **Student detail:** `AgentStudentDetailPanel` gains a "Tasks" section = `AgentTasksPanel` for that student with its own add
  form; read-only when archived.
- `searchStudents` moves from `AgentApplicationCreatePanel` to `lib/agentStudents.ts` (shared; behaviour unchanged).

## 8. Security review (security-and-hardening)

AuthN unchanged (cookie session, `get_current_user`). AuthZ: `_gate` + scope in SQL on every route. IDOR: task id, student id and
application id from another agency or another staff member → 404/422 (tests per route). Escalation: no assignee field; server
fields not writable (`extra="forbid"`); student fixed after create. XSS: React escaping only. CSRF: existing SameSite=Lax cookie +
CORS allowlist + JSON bodies (unchanged). SQLi: SQLAlchemy expressions only. Secrets: none added. Logs/audit: ids and field
names only. DoS: length caps, page cap, offset cap, open-task cap (T7). Audit: every write.

## 9. Numbering and parallel lanes

`DEC-SCOPE-051` and `0058_agent_tasks` are provisional: `feature/agn-009-agent-documents` is open in parallel from the same base.
The lane that merges second renumbers its decision and migration (`AGENT_CRM_BACKLOG.md` §6.2).

## 10. Acceptance criteria

- **AGN-016-AC01** Master and assigned Staff create a task (201, `status=open`) for a student with and without a login; one audit row.
- **AGN-016-AC02** Staff cannot read, list, create or edit tasks of unassigned or other-agency students (404 / empty page); another
  agency's Master likewise; non-agents and pending agencies 403.
- **AGN-016-AC03** After the Master reassigns a student, the old Staff get 404 on its tasks and the new Staff see them (open ones in
  their open list) with no task write.
- **AGN-016-AC04** `overdue` is true exactly for open tasks with `due_at < now`; `view=overdue` returns exactly those.
- **AGN-016-AC05** PATCH edits fields; `status=done|cancelled` closes with `closed_at`/`closed_by`; any write to a closed task → 409.
- **AGN-016-AC06** Archived student: create/edit/close → 409; its open tasks leave `view=open` and the KPI; reads by `student` work.
- **AGN-016-AC07** Application link: another student's, another agency's, or a withdrawn application → 422.
- **AGN-016-AC08** Validation: blank/long title, long notes, naive `due_at`, unknown field, status + field → 422.
- **AGN-016-AC09** Two concurrent completes → one 200, one 409.
- **AGN-016-AC10** Dashboard "Pending actions" = open tasks of active students in scope (Master: agency; Staff: own); other metrics unchanged.
- **AGN-016-AC11** Audit metadata and logs carry no title or notes; AGN-021 activity lists task work.
- **AGN-016-AC12** UI: Tasks nav for both roles; create, edit, complete, cancel; overdue badge as text; loading, empty, error states;
  keyboard-only flow; usable at 320 px.
- **AGN-016-AC13** Cap: the 101st open task on one student → 409.

## 11. Regression risks

`portal._agent` (shared dashboard), `AgentStudentDetailPanel` and `AgentApplicationCreatePanel` (refactor of `searchStudents`),
`lib/navigation.ts` (nav list), `STAFF_ACTIVITY_ACTIONS`, the alembic head (parallel AGN-009). Lite tests: the new AGN-016 tests
plus `test_agn_004_staff_scope`, `test_agn_001_team`, `test_agn_008_dashboard`, `test_agn_021_activity`. The full suite is run
separately by the owner.
