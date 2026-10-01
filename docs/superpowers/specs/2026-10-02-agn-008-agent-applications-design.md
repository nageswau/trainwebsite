# AGN-008 — Agent Applications: Create, Edit, View and Change Status, With Application ID, Submission Date and Deadlines; Staff Sidebar Filters — Design

**Status:** design approved in-session, 2026-10-02, in two sections: approach plus data/backend, then frontend/sidebar/states/tests. No code has been written.

**Source requirement.** The owner's `AGN-008` statement (in-session, 2026-10-01):

> "create, edit, view, change status, application ID, submission date and deadlines; Staff sidebar filters (§2, §4, §5)."

Its acceptance criteria are:

- Create, edit and status change work for an agent student, and write history rows.
- Filters return the correct subsets.
- The admin and university_rep lists include the application, with the owner shown correctly.
- No response anywhere crashes on a NULL `student_id`.
- A backward status change returns `422`.
- A duplicate returns `409`: same student, university and course, not withdrawn.

Source sections are in `functionalities/edusphere_markdown/Agent CRM Functionalities.md` (`EVID-015`, `DERIVED_BLUEPRINT`, provenance `NEEDS_CONFIRMATION`):

| Section | Lines | Content |
|---|---|---|
| §2 "Applications" | L69–81 | create, edit, view all, change status, monitor deadlines |
| §4 Staff Sidebar → Applications | L207–219 | All Applications, Draft, Submitted, Offer Received, Visa, Enrolled |
| §5 STEP 5 "Application" | L313–327 | university, course, intake, submit, Application ID, Submission date, Status |
| §5 STEP 6 | L331–343 | "Offer Deadline" only |

**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → **`DEC-SCOPE-050`** (provisional).
- Unmerged branches already claim the earlier numbers: AGN-006 has `DEC-SCOPE-048` / migration `0055`, and AGN-007 has `DEC-SCOPE-049` / `0056`.
- Whichever branch reaches `main` later renumbers, following the precedent set from `DEC-SCOPE-038` to `047`.
- This decision lifts `DEC-SCOPE-042` **D8**, which said "Applications … for students with no login are a later feature".
- It turns the AGN-003 `DEC-SCOPE-044` matrix rows "Edit Application" and "Change Application Status" from N/A into enforced rows.

**Impact analysis:** graphify-led, 2026-10-01 (this session). It used four read-only inventories: backend applications, agent CRM backend, frontend/e2e, and docs. The findings are summarised in §10.

---

## 1. Scope

**In scope**

- Agency Masters and their assigned Staff can create, edit, view and change status on overseas applications for **agent students**. This covers students with a login (`agent_students.student_id` set) and students without one (`student_id` NULL, AGN-004).
- Each application records:
  - `application_reference`, which is the "Application ID": the university's reference, typed in.
  - `submitted_on`, entered by hand.
  - `application_deadline` and `offer_deadline`.
- An Applications filter group in the agent sidebar, shown to Masters and Staff.
- NULL-safe owner display in every application list that today inner-joins `users` on `student_id`.
- Withdrawal as a terminal state.

**Out of scope** (accepted by the owner, 2026-10-01)

- Documents for no-login students. `student_documents.student_id` stays NOT NULL.
- Converting an AGN-007 shortlist entry into an application.
- Offer details from §5 STEP 6: offer date, conditional/unconditional, conditions, offer document. Only the offer deadline is in scope.
- Deadline reminders or notifications. "Monitor deadlines" is met by showing the nearest deadline in the list.
- New notifications when an agent changes status.
- Agents setting `enrolled`.
- Rejected, waitlisted and deferred outcomes, which stay open under `DEC-WF-001`.
- Backfilling `agent_student_id` onto applications that existed before this feature.

## 2. Approaches considered

**A — chosen.** A dedicated agent router plus NULL-safe fixes to the shared lists.
- The new router is `app/api/agent_applications.py` at `/workflows/overseas/agent/crm/applications`, next to AGN-004's `crm/students`.
- It reuses AGN-004's gate, organisation lock, 404 masking and same-transaction audit.
- It reuses the existing `overseas_applications` table, `application_status_history` and the commission trigger.
- Counselor, university_rep and admin endpoints are unchanged except for one guard against reviving a withdrawn application.

**B — rejected.** Extend the generic `POST`/`PATCH /workflows/overseas/applications` to accept agents and `agent_student_id`.
- It changes a contract shared by four roles.
- It mixes the agent's forward-only rule into the counselor/admin PATCH, which deliberately allows corrections.
- It puts OVS-002/003/004 at risk.

**C — rejected.** A separate `agent_applications` table.
- Admin, university_rep, commissions and reports would never see these applications, which fails an acceptance criterion.
- The status/history/commission pipeline would be duplicated.

## 3. Decisions (owner, in-session, `EXPLICIT_APPROVAL`, 2026-10-01/02)

| ID | Decision |
|---|---|
| **A1** | Statuses keep the `DEC-WF-001` enum: `enquiry → eligibility_evaluation → university_selection → offer → visa_documentation → status_tracking → enrolled`. **`withdrawn`** is added as a terminal value. Sidebar filters map onto groups of stages (A7). |
| **A2** | The "Application ID" is the existing `overseas_applications.application_reference`: the university's reference, typed in. It is not an agency-generated code. A university_rep can still edit it through the existing PATCH. |
| **A3** | `application_deadline` and `offer_deadline` are optional dates, entered by hand. `submitted_on` is an optional date, entered by hand. There are no reminders. |
| **A4** | Agents (Master and Staff in scope) may only move **forward**, up to `status_tracking`, and skipping stages is allowed (as counselor `/advance` allows). They may **withdraw** from any stage except `enrolled`. `enrolled` stays with counselor, admin and university_rep, so an agent never triggers commission accrual on itself (`DEC-SCOPE-005`). |
| **A5** | `DEC-SCOPE-042` D8 is lifted. A nullable `overseas_applications.agent_student_id` links an application to the agency's student record. This is the `DEC-SCOPE-018` `school_student_id` pattern. |
| **A6** | Agent-student applications appear, with the owner's name, in all of these: admin and university_rep lists, commission lists, the RPT-002 report and visa views, the application lookup, and AGN-021 staff activity. |
| **A7** | The sidebar filters are links under Applications, for both Master and Staff. Each one is the same page with `?status=<group>`. Staff see only the applications of students assigned to them (G4). |
| **A8** | A student with a login keeps today's "Application created" notification. No new notifications are added. |
| **A9** | **Draft and Submitted are told apart by `submitted_on`.** Both cover the stages before an offer; `submitted_on` decides which group an application is in. |
| **A10** | **The university is fixed after creation.** To change it, withdraw the application and create a new one. Course (same university), intake, Application ID, the three dates and the next action stay editable. |
| **A11** | For a student with a login, the application also stores `student_id`. The student still sees it in their own portal, and the existing student-level duplicate rule still covers applications made before this feature. |
| **A12** | School-bridged applications (`school_student_id` set) stay excluded from every list that excludes them today. Switching inner joins to outer joins must not make them appear. |
| **A13** | The old `POST /workflows/overseas/applications` stays unchanged for agents (backward compatible). The agent UI moves to the new routes. |

**Conflicts recorded, not resolved silently**

1. The EVID-015 sidebar labels (Draft, Submitted, Offer Received, Visa, Enrolled) do not match the confirmed enum. This is resolved by A1, A7 and A9: the filters map onto groups of stages, and the enum is not extended.
2. `DEC-SCOPE-036` (ENH-017) lists "started/submitted" as `NEEDS_CONFIRMATION`. AGN-008 adds a `submitted_on` date but **no** submitted status, so ENH-017 is unaffected.
3. `models.py`'s comment calls it "correct" that inner joins drop rows with a NULL `student_id`. That was true for school rows only. For agent students it is replaced by A6 and A12.

## 4. Data model — migration `0057_agent_applications`

The migration is provisional. Its `down_revision` is `0054_school_onboarding_bulk`, and it is re-chained after AGN-006's `0055` and AGN-007's `0056` when they merge. It only adds columns; no existing row changes.

| Column on `overseas_applications` | Type | Notes |
|---|---|---|
| `agent_student_id` | `UUID NULL` FK → `agent_students.id` | Index `ix_overseas_applications_agent_student_id`. No cascade: agent students are archived, never deleted. |
| `submitted_on` | `DATE NULL` | A3 |
| `application_deadline` | `DATE NULL` | A3 |
| `offer_deadline` | `DATE NULL` | A3 |

- **No DB enum or CHECK is added for status.** `status` is `String(50)`. `withdrawn` needs no DDL, matching this table's style of app-level invariants.
- **Owner invariant**, enforced at every write site and not as a DB CHECK (the `DEC-SCOPE-018` style):
  - `school_student_id` excludes `student_id` and `agent_student_id`.
  - An agent-created application always has `agent_student_id`, plus `student_id` when the agent student has a login (A11).
- **Downgrade** drops the index and the four columns.
- Model: `OverseasApplication` (`models.py:424`) gains the four mapped columns. The misleading comment is updated (conflict 3).

## 5. Backend

### 5.1 Scope — `services/agent_students.py`

`application_scope(user)` keeps the org clause on `agent_id`. For staff, the extra clause becomes:

`or_(OverseasApplication.student_id.in_(visible_student_user_ids(user)), OverseasApplication.agent_student_id.in_(select(AgentStudent.id).where(*student_scope(user))))`

Masters are unchanged.

Every existing caller still gets the same rows for applications made before this feature:
- `_assigned_application`
- `lookups`
- the portal `_agent` section
- document review

### 5.2 Service — new `app/services/agent_applications.py` (functions only; never commits)

- `STATUS_GROUPS`: the A7/A9 mapping.

  | Group | Rule |
  |---|---|
  | `draft` | Stages before offer, and `submitted_on IS NULL` |
  | `submitted` | Stages before offer, and `submitted_on IS NOT NULL` |
  | `offer` | `offer` |
  | `visa` | `visa_documentation` or `status_tracking` |
  | `enrolled` | `enrolled` |
  | `withdrawn` | `withdrawn` |
  | `all` (default) | Everything except `withdrawn` |

  "Stages before offer" means `enquiry`, `eligibility_evaluation` and `university_selection`.
- `AGENT_MAX_STAGE = "status_tracking"`. `OVERSEAS_APPLICATION_STAGES` moves from `api/workflows.py:1722` into this module, and `workflows.py` imports it from here (`workflows.py` already imports `services.agent_students`). That keeps one definition, and `workflows.OVERSEAS_APPLICATION_STAGES` stays importable. The copies in `schools.py` and `portal.py` are left alone, since they are unrelated modules.
- `owner_name()`: `func.coalesce(User.full_name, AgentStudent.full_name)`.
- `list_page(db, user, *, group, agent_student_id, limit, offset)`:
  - Outer joins to `User` and `AgentStudent`; inner join to `University`; outer join to `OverseasCourse`.
  - Scoped by `application_scope(user)`.
  - Ordered by `updated_at DESC, id`.
  - Returns `{items, total, limit, offset}`.
- `item()` / `detail()`: explicit allowlists. Detail adds the history (oldest first: `from_status`, `to_status`, `next_action`, `notes`, `changed_by` name, `created_at`) and the editable fields.
  - Never returns `agent_id`, `counselor_id` or `student_id`.
  - Returns `has_login` and `agent_student_id`.
  - Shows `nearest_deadline` as `{kind: "application"|"offer", date}`. It is the earliest of the two deadlines that is today or later. If neither is upcoming, it is the most recent past one, which the UI marks "past". With no deadlines it is `null`.
- `load_scoped(db, user, application_id, *, lock=False)`: the scope is in the WHERE clause. Out of scope returns `404 "Application not found"`. With `lock=True`, it uses `SELECT … FOR UPDATE`.
- `duplicate_exists(db, *, agent_student, university_id, course_id, exclude_id=None) -> bool`:
  - Same `university_id` and `course_id` (`IS NULL` when there is no course), `status != 'withdrawn'`.
  - Matches when `agent_student_id` equals this student's id, **or**, when the student has a login, `student_id` equals that login. The second branch catches applications made before this feature and those made through the old path.

### 5.3 Router — new `app/api/agent_applications.py`, prefix `/workflows/overseas/agent/crm/applications`

**Gate.** Each route calls `_gate(user)`, copied from `agent_students._gate`:
- `role == "agent"` and division `overseas`, otherwise `403`.
- `agent_denial_reason`, otherwise `403` with its message.
- `super_admin` is not admitted.

**Write pattern.** Every write locks the organisation first (`lock_active_org`), then the row. That is AGN-004's lock order. Each write adds its history and audit rows in the same transaction and commits once. `_log` writes structured logs on `app.agent_applications`.

| Method | Path | Body / params | Behaviour and errors |
|---|---|---|---|
| GET | `""` | `status` (`all`\|`draft`\|`submitted`\|`offer`\|`visa`\|`enrolled`\|`withdrawn`, default `all`), `student` (UUID, optional), `limit` 20 (1–100), `offset` ≥ 0 | 200 with the page. Unknown `status` returns 422 (FastAPI `Literal`). `student` outside scope returns an empty page, not an error. |
| POST | `""` | `AgentApplicationCreate` | 201 `{"application": detail}`. See the create sequence below. |
| GET | `/{id}` | — | 200 `{"application": detail}`; out of scope returns 404. |
| PATCH | `/{id}` | `AgentApplicationUpdate` (all optional): `course_id`, `intake`, `application_reference`, `submitted_on`, `application_deadline`, `offer_deadline`, `next_action` | See the edit rules below. |
| POST | `/{id}/status` | `AgentApplicationStatus`: `to_status`, `notes?` (≤ 2000), `next_action?` | See the status-change rules below. |

**Create sequence (POST `""`):**
1. Lock the organisation.
2. `load_scoped` the agent student: out of scope returns 404 `"Student not found"`; archived returns 409 `"Unarchive this student first"`.
3. Check the university exists (404).
4. Check the course belongs to the university (422 `"Course does not belong to selected university"`).
5. Duplicate check: 409 `"An application for this university/course already exists"`.
6. Insert the application with:
   - `agent_id = user.id`
   - `agent_student_id`
   - `student_id = agent_student.student_id`
   - `status = "enquiry"`
   - the default next action used by OVS-002
7. Write a history row `None → enquiry`.
8. Audit `overseas.application.create`.
9. A student with a login gets today's notification.
10. Commit.

**Edit rules (PATCH `/{id}`):**
- Lock the organisation, then the row.
- A withdrawn application returns 409 `"This application is withdrawn"`.
- `university_id` is not accepted: `extra="forbid"` returns 422.
- A course change re-checks the course belongs to the university (422) and re-runs the duplicate check (409), excluding this application.
- No changes means 200 and no audit row.
- A `next_action` change writes a history row with the same status, as the existing PATCH does.
- Audit `overseas.application.update` with the field names.

**Status-change rules (POST `/{id}/status`):**
- Lock the organisation, then the row.
- Already withdrawn returns 409.
- `to_status == "withdrawn"`: allowed unless the current status is `enrolled` (409 `"An enrolled application cannot be withdrawn"`). Audit `overseas.application.withdraw`.
- `to_status == "enrolled"` returns 403 `"Only a counselor, university representative or admin can mark an application enrolled"`.
- `to_status` not in the stages returns 422.
- A target index at or below the current one returns **422** `"Cannot move from '<a>' to '<b>' -- an agent can only move an application forward"`.
- A target past `status_tracking` returns 403. This is already covered by the enrolled rule.
- On success: write the history row, call `_maybe_trigger_agent_commission` (a no-op because the target is never `enrolled`, but this keeps one code path), then audit `overseas.application.advance`.
- No notification (A8).

Register the router in `main.py` after `agent_students.router`.

**Error body:** `{"detail": "…"}` throughout. Whether `422` or `409` wins is fixed by the order of checks above: scope (404), then terminal state (409), then role (403), then validation (422), then duplicate (409).

### 5.4 Schemas — `schemas.py`, after `AgentStudentAssign`

- `AgentApplicationCreate`:
  - `agent_student_id: UUID`, `university_id: UUID`, `course_id: UUID | None`
  - `intake: str` (1–80, trimmed)
  - `application_reference: str | None` (≤ 140, trimmed, empty becomes None)
  - `submitted_on`, `application_deadline`, `offer_deadline`: `date | None`
  - `next_action: str | None` (≤ 500)
  - `extra="forbid"`
- `AgentApplicationUpdate`: the editable fields only, all optional, `extra="forbid"`.
- `AgentApplicationStatus`: `to_status: str` (≤ 50), `notes: str | None` (≤ 2000), `next_action: str | None` (≤ 500), `extra="forbid"`.
- Date sanity: `submitted_on` must not be in the future (422). Deadlines may be any date. The UI flags a past deadline instead of refusing it.

### 5.5 Withdrawn guard on existing endpoints (A1 terminal, minimal)

- `PATCH /workflows/overseas/applications/{id}` with `status` on a `withdrawn` application returns 409 `"This application is withdrawn"`. Non-status edits are unchanged.
- `POST …/{id}/advance` on a `withdrawn` application returns 409. Without this, `current_index = -1` lets any target through and would revive it.

Nothing sets `withdrawn` today, so existing behaviour is unchanged.

### 5.6 NULL-safe owner in shared lists (A6, A12)

Each of these sites changes from an inner `join(User, …student_id)` to an `outerjoin(User, …)` plus `outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)`.

The owner is `coalesce(User.full_name, AgentStudent.full_name)`. Each site keeps the rows it shows today and excludes school rows exactly where they are excluded now, adding `OverseasApplication.school_student_id.is_(None)` where the inner join used to do that implicitly.

| Site | Today | Change |
|---|---|---|
| `workflows.py:1845` `GET /overseas/applications` (student, counselor, admin, rep, agent) | inner `User` | outer + coalesce; `student_id` in the response may be `null`; `school_student_id IS NULL` |
| `workflows.py:2378` agent commissions | inner `User` | same |
| `admin.py:314` `/admin/applications` | inner `User` | same |
| `portal.py:684-692` `_agent` | inner `User` | same; `latest_application_by_student` skips rows with no `User` |
| `portal.py:945` shared counselor/rep/admin (feeds dashboard, offer letters, Application Tracking, documents, reports, RPT-002 funnel) | inner `User` | same |
| `portal.py:1013` visa, `:1144` visa aging, `:1423` admin commissions | inner `User` | same |
| `lookups.py:155` `/lookups/overseas-applications` | coalesce(User, SchoolStudent) | add `AgentStudent.full_name` to the coalesce, plus an outer join |
| `services/staff_activity.py` `_subjects` | outer `User` | add an `AgentStudent` outer join to the name; add `overseas.application.update`, `.advance` and `.withdraw` to `STAFF_ACTIVITY_ACTIONS` |
| `inbound.py:69` `_notify_student` | `db.get(User, None)` | guard: return when `student_id` is None |

Sites that filter by `student_id == user.id` are unaffected and are not touched. These are the student's own views, chat, visa prep and appointments.

### 5.7 Transactions, races and authorization summary

- **Duplicate race.** Each agent student belongs to exactly one organisation, and only this router writes `agent_student_id`. Creates and course edits run under `lock_active_org`, so two concurrent requests cannot both pass the duplicate check. No new DB index is needed. The old cross-agency race on `student_id` through the old path is unchanged and out of scope.
- **Status race.** The organisation lock plus the row `FOR UPDATE` serialise agent changes on one application. A concurrent counselor PATCH blocks on the row lock until the agent commits. Its stale `from_status` in history is an existing limitation of that endpoint and is recorded, not fixed.
- **Authorization:**
  - Agents of an active org only.
  - Masters see the whole org; Staff see only assigned students (`student_scope` / `application_scope`).
  - Every by-id read and write uses `load_scoped`, so an application outside scope returns 404 (another org or another staff member's student).
  - Role limits on status (`enrolled`) return 403.
  - `super_admin` and other roles are refused by the gate with 403. The existing roles keep their own endpoints.
- **Audit:** same transaction as the write (fail closed). Metadata is ids, field names and from/to status only, with no free text.

## 6. Frontend

### 6.1 Page

- `PortalPage.tsx` adds a branch: `agent && section === "applications"` renders `<AgentApplicationsSection user={user}/>`. It replaces the generic `PortalSection` table on that section only. The backend portal payload is kept (contract preserved).
- `AgentApplicationsSection` shows an eyebrow and a "Applications" heading.
- The intro depends on the viewer:
  - Staff: "Applications of students assigned to you."
  - Master: "Every application of your agency."
  - A non-agent viewer (`super_admin`) sees a note instead of the panel, following `AgentStudentsSection`.
- `WorkflowPanel.tsx:468`: `showAgentApplicationCreate` no longer mounts the create panel. The section now owns it, so it is not shown twice.

### 6.2 `AgentApplicationsPanel` (new client component)

It follows `AgentStudentsPanel`: 20 per page, the latest request wins (`AbortController`), focus returns to the opener, and URL state is read once on mount.

**Filter.** `status` comes from `useSearchParams`. An unknown value falls back to `all`. Changing a sidebar link re-renders and refetches; `offset` resets.

**List rows (cards on narrow screens):**
- Student, with a "no login" tag when `has_login` is false
- University, course, intake
- Status, as a human label
- Application ID, or "—"
- Submitted on
- Nearest deadline, with "past" or "within 7 days" text (text, not colour only)
- Next action
- A View button

**Detail region** (`aria-live="polite"` heading):
- The fields as a `<dl>`.
- Status history, as an ordered list.
- **Edit** opens an inline form with the editable fields. University is shown read-only with the hint "To change university, withdraw and create a new application."
- **Change status:** a `<select>` lists only the stages after the current one, up to `status_tracking`, plus an "Update status" button.
- **Withdraw:** an inline confirmation, then focus returns to the opener.
- Withdrawn and enrolled applications are read-only, with the reason as text.

**States:**

| State | Behaviour |
|---|---|
| Initial load | Skeleton text "Loading applications…" with `aria-busy` |
| Refetch | Rows dimmed, `aria-busy` |
| Empty, unfiltered | "No applications yet. Use Create application to add the first one." |
| Empty, filtered | "No applications match this filter." with a link to All applications |
| Load error | `role="alert"` with the message and a Retry button |
| Detail load error | Retry; a 404 says "This application is no longer available." and refreshes the list |
| Write errors | The server `detail` shown inline next to the form, `role="alert"` |
| 409 duplicate / withdrawn, 422 backward | Shown verbatim; the form keeps its input |
| Network error | "Network error. Check your connection and try again." (AGN-004 wording) |
| Writing | Buttons disabled while busy, which prevents double submits |

### 6.3 `AgentApplicationCreatePanel` (reused and extended)

- **Students:**
  - Source: `RECORDS_URL` (`/workflows/overseas/agent/crm/students`, active, in scope), paged up to 100. It replaces `/workflows/overseas/agent/students`.
  - Each option carries `agent_student_id`.
  - Option text: `"<name> — <masked email>"` for students with a login (unchanged format), and `"<name> — no login"` otherwise.
- **University and course:** unchanged (public universities, with courses cascading from the chosen university).
- **New fields:** Application ID, Submitted on, Application deadline, Offer deadline (optional, `type="date"`).
- **Submit:** POSTs to the new route. On success it shows "Application created.", resets the form and calls `onCreated()` so the list refetches.
- **Kept for compatibility** (ENH-031 e2e and unit tests):
  - ids `#agent-app-student`, `#agent-app-student-list`, `#agent-app-university`
  - the combobox accessible name "Linked student"
  - the button name "Create application"
  - the success text "Application created."

### 6.4 Sidebar filters

- `navigation.ts`: the agent `applications` item gains `children`. Each child's href is `/overseas/agent/applications?status=<group>`:

  | Label | `status` |
  |---|---|
  | Draft | `draft` |
  | Submitted | `submitted` |
  | Offer received | `offer` |
  | Visa | `visa` |
  | Enrolled | `enrolled` |
  | Withdrawn | `withdrawn` |

  The parent keeps its href and label, and acts as "All".
- **Unchanged:** top-level hrefs, `agentNavFor`, the `PortalPage` guard (it matches top-level `href`), `STAFF_HIDDEN`, and `navigation.agent.test.ts`'s href lists.
- `PortalShell.tsx` renders `item.children` as an indented `<ul>` of links under their parent, for any portal that defines children (only the agent one does).
  - `aria-current="page"` goes on the child whose `pathname + "?" + search` matches.
  - The parent is current only when the path matches and no `status` is present.
  - It uses `useSearchParams`, as `LoginForm` does.
- `MobileNavToggle` receives the nav with children flattened after their parent, labelled "Applications: Draft" and so on.

### 6.5 Activity labels

`lib/agentStaff.ts` `ACTIVITY_LABELS` gains:

| Action | Label |
|---|---|
| `overseas.application.update` | "edited an application" |
| `overseas.application.advance` | "moved an application forward" |
| `overseas.application.withdraw` | "withdrew an application" |

## 7. Security

- Authorization is server-side only. UI controls only follow it: the status options shown and the edit button hidden for withdrawn applications.
- IDOR: every by-id route resolves the row through scope in the WHERE clause, and the response does not reveal whether a row exists.
- Mass assignment: `extra="forbid"` schemas; `university_id`, `agent_id`, `student_id` and `status` cannot be set through PATCH.
- Commission self-dealing is prevented by A4 (agents cannot reach `enrolled`).
- Output allowlist: no internal user ids. `agent_student_id` is the agency's own record id.
- Input bounds: lengths as in §5.4; `limit` ≤ 100; `status` is a `Literal`.
- Audit and log metadata never contain notes text or personal data.

## 8. Acceptance criteria (AGN-008-AC01…AC14)

1. **AC01** — A Master creates an application for a student with no login and one with a login. The response is 201, `status = enquiry`, with one history row (`None → enquiry`), and the student's own portal shows it only when the student has a login.
2. **AC02** — Staff can create, edit and change status for an assigned student. For an unassigned student, or another org's student or application, the response is 404.
3. **AC03** — A duplicate (same student, university and course; status not withdrawn) returns 409. This includes an application made before this feature for a student with a login. After a withdrawal, the same combination can be created again (201).
4. **AC04** — Edit updates Application ID, the three dates, intake, course and next action. A course from another university returns 422. Changing the university returns 422. Editing a withdrawn application returns 409.
5. **AC05** — Forward status changes, including skips up to `status_tracking`, return 200 and write one history row each. Backward or same-stage changes return 422. An unknown status returns 422. `enrolled` returns 403. No commission row is ever created by an agent's status change.
6. **AC06** — Withdraw from any stage before `enrolled` returns 200 with a history row. After that, any edit or status change returns 409. Counselor `/advance` and the existing PATCH with `status` also return 409 on a withdrawn application.
7. **AC07** — Each filter (`draft`, `submitted`, `offer`, `visa`, `enrolled`, `withdrawn`, `all`) returns exactly the matching subset, within scope. Pagination totals are correct.
8. **AC08** — `/admin/applications`, the university_rep's `GET /workflows/overseas/applications`, and the rep and admin portal application sections list an application for a student with no login, with that student's name as owner.
9. **AC09** — No response crashes on a NULL `student_id`. This covers every endpoint and portal section listed in §5.6, plus inbound email matching. School-bridged rows stay excluded exactly where they are today.
10. **AC10** — When a counselor or admin later sets `enrolled`, the commission is accrued as today, and it appears in the agent and admin commission lists with the owner's name.
11. **AC11** — Each sidebar filter link shows the matching subset with `aria-current` on the active link. Staff and Masters both have the links. The mobile menu includes them.
12. **AC12** — The page shows correct loading, empty (unfiltered and filtered), error-with-retry, and write-error states. It has no horizontal scroll at 320px, and keyboard focus returns to the opener after actions.
13. **AC13** — Agent edit, advance and withdraw actions appear in AGN-021 staff activity with the student's name.
14. **AC14** — Existing behaviour is preserved:
    - OVS-002/003/004, AGT-002/003/004, SCH-010, UNI-001, RPT-002, ENH-031 and AGN-001/002/003/004/005/021 tests pass unchanged, except the documented updates in §9.
    - The old agent create path still works.

## 9. Tests (written first; real runs only)

**Backend (pytest, Docker `API_TEST`, isolated compose project `-p agn008`):**

| File | Covers |
|---|---|
| `test_agn_008_migration.py` | upgrade/downgrade; columns, FK and index exist; existing rows untouched |
| `test_agn_008_create.py` | AC01, AC02 (create), AC03 |
| `test_agn_008_edit.py` | AC04 |
| `test_agn_008_status.py` | AC05, AC06 (agent side), no commission |
| `test_agn_008_scope.py` | Master org-wide, Staff assigned-only, cross-org 404, super_admin and other roles 403, gate denial reasons |
| `test_agn_008_filters.py` | AC07 |
| `test_agn_008_null_owner.py` | AC08, AC09, AC10: every §5.6 site, with a no-login application, a linked application and a school-bridged application present together |
| `test_agn_008_withdrawn_guard.py` | AC06 (counselor `/advance` and PATCH) |

Helpers: `agn004_helpers.mk_record` / `mk_staff`, `agn001_helpers`, `agn003_helpers.mk_university`.

**Existing tests updated, because the requirement changes them:**
- `test_agn_003_matrix.py`: the rows "Edit Application" and "Change Application Status" move from N/A to enforced for both Master and Staff.
- `test_agn_021_activity.py`: gains the new actions.
- `Enh031ExistingPickers.test.tsx`: fetch mocks for the new student source (option text unchanged).

**Frontend (vitest):**
- `AgentApplicationsPanel.test.tsx`: states, filter from the URL, status options, withdraw confirmation, error rendering.
- `AgentApplicationCreatePanel.test.tsx`: students with and without a login, new fields, POST body.
- `PortalShell.test.tsx`: children with `aria-current`, mobile flattening.
- `navigation.agent.test.ts`: the children list. Existing assertions are unchanged.

**Playwright:** `agn-008-agent-applications.spec.ts`
- A Master creates an application for a student with no login, edits it, moves it forward, sees no backward option, and withdraws it.
- Staff see only their students' applications through the sidebar filters.
- The admin and university_rep lists show the owner's name.
- No horizontal scroll at 320px.

**Re-run:**
- e2e: enh-031, agn-004, agt-002, agt-003, ovs-002/003/004 and uni-001.
- Backend: the lite set per task (owner runs the full suite every 4–5 stories).

## 10. Regression risks

| # | Risk | Guard |
|---|---|---|
| R1 | `portal.py:945` and RPT-002 counts change when rows are no longer dropped | Only no-login agent rows are added; school rows are excluded explicitly; tests assert counts with the three kinds of row present together |
| R2 | `application_scope` is wider for staff | The OR clause covers only scoped `agent_students`; the AGN-004 staff-scope tests are re-run |
| R3 | `PortalShell` and `navigation.ts` are shared by every portal | Children render only where defined; top-level structure unchanged; existing tests stay green |
| R4 | ENH-031 picker ids, label and text | Kept verbatim (§6.3) |
| R5 | Withdrawn guard on counselor and admin endpoints | Applies only to `status == "withdrawn"`, which nothing sets today |
| R6 | `student_id` may be null in the `GET /workflows/overseas/applications` response | Frontend consumers checked (DataTable renders null as "—"); the university_rep update uses the application id |
| R7 | Merge with AGN-006/007, which touch the same anchors | Renumber DEC and migration on merge; insert at distinct anchors; notes for whoever merges second (§12) |
| R8 | The commission trigger | Unchanged; agents cannot reach `enrolled` |

## 11. Documentation (updated with the build)

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-050`.
- `ENHANCEMENT_BACKLOG.md`: an AGN-008 summary row and a section with AC01–AC14.
- `RTM.md`: an AGN-008 row.
- `DATA_MODEL.md` §6.2: new columns, `withdrawn`, owner invariant.
- `API_CONTRACT.md`: the agent applications table; nullable `student_id` in the list response.
- `RBAC_MATRIX.md`, `SECURITY_CONTROLS.md`, `THREAT_MODEL.md`.
- `PRD_OPEN_ITEMS.md`: item 68 (agent half resolved for applications).
- `CONFLICT_MATRIX.md` C-10: a note that the EVID-015 Applications slices are decided.
- `SCREEN_CATALOG.md` / `.json`.

## 12. Merge notes

- AGN-006 (`0055`, `DEC-SCOPE-048`) and AGN-007 (`0056`, `DEC-SCOPE-049`) are unmerged.
- If either reaches `main` first, re-chain `0057`'s `down_revision` onto the latest head and keep `DEC-SCOPE-050`. If AGN-008 merges first, they renumber.
- Shared anchors:
  - `models.py`: AGN-008 edits `OverseasApplication` only.
  - `schemas.py`: insert after `AgentStudentAssign`; AGN-006/007 also insert there, so place AGN-008's block last.
  - `services/staff_activity.py` `STAFF_ACTIVITY_ACTIONS`.
  - `test_agn_003_matrix.py`.
  - `lib/agentStaff.ts`.
  - `navigation.ts` and `PortalPage.tsx`: AGN-007 adds a nav item and branch.
  - `main.py` router tuple.

## 13. Completion gates (not met by implementation alone)

AGN-008 is complete only when all of these pass:
- Every AC
- The backend lite set
- vitest
- Playwright (new and re-run specs)
- `next build`
- Migration upgrade/downgrade
- Responsive check at 320px
- Accessibility (keyboard, `aria-current`, alerts)
- Documentation (§11)

Browser QA and independent review are done by the owner.
