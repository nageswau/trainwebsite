# AGN-004 — Agent Students: Master/Staff Create, Edit, View and Archive Students Who Never Log In — Design

**Status:** Design approved in-session, 2026-09-30, section by section (data model, backend, frontend,
acceptance/tests/risks), then reviewed the same day against the `api-and-interface-design`,
`frontend-ui-engineering` and `security-and-hardening` skills. **Revision 2 (2026-09-30):** the parallel
`feature/agn-002-staff-logins` branch (AGN-002, its own `DEC-SCOPE-040`, migration `0047_agent_org_staff`) was
found to own the Staff model. The owner chose (in-session, `EXPLICIT_APPROVAL`): AGN-004 stays independent of
AGN-002 but carries only the minimal Staff code its scoping needs, **written with AGN-002's exact names**;
Staff keep AGN-002's reach (S1) but are narrowed to assigned students everywhere; a deactivated Staff member
keeps their assignments. §3 G1–G5 record this. Staff creation, edit, deactivation, reactivation, reset and the
Team-screen Staff panel are AGN-002's and are **removed** from this spec. No code written.

**Source requirement:** the user's `AGN-004` statement (2026-09-30): *"Master/Staff create, edit, view and
archive students who never log in (§2 Students, §5 Step 1; DEC-ROLE-004; DEC-SCOPE-035 D3)."* Acceptance: create/
edit/view/archive work for the right roles; an archived student leaves default lists but remains in history and
reports; Staff cannot see a student assigned to someone else (`404`); no `users` row is ever created for an agent
student; the within-org duplicate warning fires. Source sections: `functionalities/edusphere_markdown/Agent CRM
Functionalities.md` (`EVID-015`, `DERIVED_BLUEPRINT`) §2 "Students", §5 Step 1, §6.

**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → **`DEC-SCOPE-042`** (provisional; recorded
with this feature's first docs commit). `DEC-SCOPE-040` is taken by AGN-002 on its branch; whichever reaches
`main` second renumbers, per the existing precedent. `DEC-ROLE-004` (no login for agent-referred students; the
agent acts on their behalf) applies unchanged.

**Citation correction (recorded, not silently fixed):** the requirement cites `DEC-SCOPE-035 D3`.
`DEC-SCOPE-035` is ENH-027's psychometric decision and `DEC-SCOPE-038` D3 is AGN-001's account-code rule;
neither decides agent students. This feature's decisions are `DEC-SCOPE-042`.

**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §AGN-004 (to be added; AGN-004-AC01…AC13 = §8).

**Branch:** `feature/agn-004-agent-students` (from `main` at `9d355e8`, AGN-001 merged). Independent of
`feature/agn-002-staff-logins`; merge notes in §12.

## 1. Scope

**In scope:** students with no login stored on `agent_students`; create / edit / view / archive / unarchive /
assign; a within-agency duplicate warning; Staff narrowed to their assigned students across every agent
student, application and document path; the minimal Staff model pieces this needs (G2), identical to AGN-002.

**Out of scope:** creating, editing, deactivating, reactivating or resetting Staff logins and the Team-screen
Staff panel (AGN-002); applications, documents and commissions for students with no login (D8 — a later
feature, which will add an `agent_student_id` bridge like SCH-010's `school_student_id`); hard delete; bulk
import; Staff performance; CRM settings; session versioning (AGN-002); any change to `users`,
`overseas_applications`, `student_documents` or `agent_commissions` tables.

## 2. Approaches considered

| Choice | Option | Verdict |
|---|---|---|
| Staff representation | **A. `User.role='agent'` + `AgentOrgMember.role='staff'`** | **Chosen** — and it is exactly AGN-002's S2 model. |
| | B. New `User.role='agent_staff'` | Rejected: ~10 more touch points; contradicts AGN-002. |
| Student storage | **A. Extend `agent_students`** | **Chosen.** One table for both kinds; old link/application code keeps working; archive reuses `status`. |
| | B. New table | Rejected: every list, archive and assignment merges two sources. |
| Agency key | **`agent_id IN org_member_ids(user)`** (F1) | **Chosen**, as AGN-001 E1: membership is permanent, so `agent_id` fixes the agency. |
| | Add `org_id` | Rejected: AGN-001 §2 rejected exactly this (drift between `org_id` and `agent_id`). |
| Relation to AGN-002 | Build on AGN-002's branch | Rejected by the owner. |
| | **Independent, minimal, identical names (G1/G2)** | **Chosen by the owner.** |
| | Independent, full Staff management | Rejected by the owner (duplicate work). |

## 3. Decisions

`DEC-SCOPE-042` (owner, in-session, 2026-09-30, `EXPLICIT_APPROVAL`):

- **D1 — Staff in scope for students.** Staff (as modelled by AGN-002 S2) create, edit and view students; this
  lifts the "staff assignment/ownership" part of `DEC-SCOPE-038` D13 / `C-10` that AGN-002 S1 left blocked.
  Staff performance, permission levels and CRM settings stay blocked.
- **D3 — Two kinds of student, side by side.** The existing "link a student who has an account" flow stays. A
  new flow creates a student with no login; their details live on `agent_students` and no `users` row is ever
  created for them.
- **D4 — Assignment.** A student created (or linked) by Staff is assigned to that Staff member. A student
  created or linked by a Master starts unassigned (Masters only). Only a Master assigns or reassigns.
- **D5 — Archive.** Master only; a Master can also unarchive. Archived students leave default lists but stay in
  history and reports.
- **D7 — Duplicate warning.** Within the agency: same email (case-insensitive) or same normalised phone → a
  warning listing the matches; saving again with `confirm_duplicate: true` proceeds.
- **D8 — Downstream deferred.** Applications, documents and commissions for students with no login are a later
  feature.

(D2 "Staff invite" and D6 "Students area only" of revision 1 are withdrawn — replaced by G3/G4.)

**Revision 2 decisions (owner, in-session, 2026-09-30, `EXPLICIT_APPROVAL`):**

- **G1 — Independent of AGN-002.** AGN-004 branches from `main`; the two branches are reconciled at merge.
- **G2 — Minimal Staff code, AGN-002's exact names.** AGN-004 adds only: the member role `staff` (`MASTER`,
  `STAFF` constants), `agent_orgs.staff_seq`, `uq_agent_org_members_org_role_seq`, `rbac.is_agent_staff`, the
  role filters on the Master rules and Master listings, the Master-only guards on team and commissions,
  `UserOut.agent_member_role` on `GET /auth/me`, and `agentNavFor`. Each is byte-for-byte the AGN-002 version
  where AGN-002 has one. No Staff management endpoint or UI. Tests create Staff through fixtures.
- **G3 — Staff reach = AGN-002 S1.** Staff reach every agent page and route except Team and Commissions, which
  stay Master-only.
- **G4 — Assigned-only everywhere.** Staff see and act on only the students assigned to them — on the new
  student routes **and** on the existing roster, link, application, document, lookup and portal paths — so no
  other Staff member's student is visible through an application or document. Out-of-scope by-id access is
  `404` on the new routes; the existing routes keep their existing status codes for out-of-scope access.
  This narrows AGN-002 S1's agency-wide Staff scope.
- **G5 — Deactivation keeps assignments.** A deactivated Staff member's students stay assigned; Masters still
  see them and can reassign; if AGN-002 reactivates the Staff member, they regain the same students. Only an
  **active** Staff member can be the target of a new assignment.

Design decisions (confirmed in-session, 2026-09-30):

- **F1 — No `org_id` on `agent_students`** (§2).
- **F2 — Linked students are not editable here.** Their name, email and phone belong to the student's own
  `users` account. For linked students AGN-004 allows view, archive, unarchive and assign only.
- **F3 — Duplicate scope includes archived and linked students**, marked as such.
- **F4 — Staff see matches they cannot view only as a count** (`hidden_matches`), never name or id.
- **F5 — Detail view is a side panel on the Students screen**, not a new route.

## 4. Data model — migration `0049_agent_students_crm` (after AGN-002's `0047_agent_org_staff`; cut as `0047_agent_students_crm` after `0046_agent_orgs`, re-chained on merge 2026-10-01 — the staff pieces below are now AGN-002's)

**Staff pieces (G2) — identical to AGN-002's `0047_agent_org_staff`, each guarded so it is a no-op when already
applied** (so after the merge, whichever migration runs second skips them):

- `agent_orgs.staff_seq INTEGER NOT NULL DEFAULT 0` + `ck_agent_orgs_staff_seq` (`staff_seq >= 0`) — added only
  if the column is missing (AGN-002's `_columns` guard).
- `ck_agent_org_members_role` → `role IN ('master', 'staff')` (drop and re-create; idempotent).
- `uq_agent_org_members_org_seq` → `uq_agent_org_members_org_role_seq (org_id, role, seq)` — only if the old
  constraint still exists (so M001 and S001 coexist).
- Not taken: `users.session_version` (AGN-002 only).

**`agent_students`** — additive; every existing column keeps its meaning:

| Column | Type | Notes |
|---|---|---|
| `student_id` | `users.id` FK, **now nullable** | `NULL` = a student with no login |
| `agent_id` | unchanged, NOT NULL | "created or linked by"; fixes the agency (F1) |
| `status` | unchanged `String(30)` | new CHECK `ck_agent_students_status` `status IN ('active', 'archived')`; pre-checked, fails loudly on any other value |
| `full_name` | `String(160)` null | required by the API for a student with no login |
| `email` | `String(320)` null | stored trimmed and lowercased |
| `phone` | `String(40)` null | as entered |
| `phone_digits` | `String(20)` null | server-set, digits only; duplicate check |
| `date_of_birth` | `Date` null | |
| `highest_qualification` | `String(200)` null | |
| `institution` | `String(200)` null | |
| `graduation_year` | `SmallInteger` null | 1950 … current year + 6 |
| `preferred_country` | `String(120)` null | |
| `preferred_course` | `String(200)` null | |
| `preferred_intake` | `String(40)` null | free text, e.g. "Sep 2027" |
| `notes` | `Text` null | ≤ 2000 characters (API) |
| `assigned_member_id` | `agent_org_members.id` FK null | `NULL` = unassigned |
| `archived_at` | `DateTime(tz)` null | |
| `archived_by_user_id` | `users.id` FK null | |
| `updated_by_user_id` | `users.id` FK null | |

Constraints and indexes: `ck_agent_students_identity` = `student_id IS NOT NULL OR full_name IS NOT NULL`;
indexes `(agent_id, status)`, `(agent_id, lower(email))`, `(agent_id, phone_digits)`, `(assigned_member_id)`.
`uq_agent_student (agent_id, student_id)` kept (PostgreSQL treats `NULL`s as distinct).

**Upgrade** preserves every existing row unchanged (all new columns `NULL`, `staff_seq` 0, existing members all
`master`). **Downgrade** removes only AGN-004's `agent_students` additions: it refuses (raises) while any row has
`student_id IS NULL` or `assigned_member_id IS NOT NULL` — it never silently deletes students or drops
assignments — then drops the columns, indexes and CHECKs and restores `student_id NOT NULL`. It then reverts
the G2 Staff pieces only if no `role='staff'` member exists (AGN-002's `assert_no_staff` rule), else raises.

## 5. Backend

### 5.1 Staff pieces (G2 — copied from AGN-002, same names and wording)

- `core/rbac.py`: `is_agent_staff(user) -> bool` (AGN-002's docstring). `agent_denial_reason` is **unchanged**:
  suspension, pending and deactivation already apply to every member, Staff included.
- `services/agent_orgs.py`: `MASTER, STAFF = "master", "staff"`; `count_active_masters`, the "other active
  Masters" query and member lookup in `deactivate_master`, and `notification_recipients` filter
  `role == MASTER`.
- `api/agent_team.py`: `_require_master` refuses Staff with `403 MASTER_ONLY` (`"Only an agency Master can
  manage the team"`); `GET /team` lists `role == MASTER` members only.
- `api/workflows.py`: `_require_agent_master` on `GET /overseas/agent/commissions` and the claim route
  (`403 "Only an agency Master can view commissions"`).
- `api/portal.py`: Staff on `team` / `commissions` → `403 "Only an agency Master can open this page"`.
- `services/portal._agent`: Staff never read commissions (dashboard KPIs and the reports "Paid commission" row
  omitted); the `team` section lists Masters only.
- `api/admin.py`: Overseas Admin's per-agent approve/reject refuses a Staff user (`422 "Staff accounts are
  managed by their agency"`) and `/overseas-admin/agents` and the agent-org search/list show Masters only.
- `schemas.UserOut.agent_member_role: str | None = None`; `GET /auth/me` sets it from the eager-loaded
  membership (login/refresh leave it `None`, as AGN-002).

### 5.2 Scope helpers — new `app/services/agent_students.py` (functions only)

```text
student_scope(user)        -> [AgentStudent.agent_id IN org_member_ids(user)]
                              + [AgentStudent.assigned_member_id == user.agent_membership.id]   if is_agent_staff(user)
visible_student_user_ids(user) -> select(AgentStudent.student_id).where(*student_scope(user), student_id IS NOT NULL)
application_scope(user)    -> [OverseasApplication.agent_id IN org_member_ids(user)]
                              + [OverseasApplication.student_id IN visible_student_user_ids(user)] if is_agent_staff(user)
```

For a Master these return exactly today's AGN-001 clauses, so Master behaviour is unchanged by construction.
The same module holds the record serialisers, the duplicate check (§5.5) and the write functions (no commit),
following `services/agent_orgs.py`'s shape.

### 5.3 Existing agent paths narrowed for Staff (G4)

| Path | Today (AGN-001) | After, for Staff | Masters |
|---|---|---|---|
| `GET /workflows/overseas/agent/students` (roster) | org-wide links | `student_scope` | unchanged, plus archived hidden (§5.6) |
| `POST /workflows/overseas/agent/students` (link) | org-wide duplicate check, `agent_id = user.id` | same check; the new link gets `assigned_member_id` = the Staff member (D4) | unchanged |
| `POST /workflows/overseas/applications` link check | link in org, `status='active'` | link must satisfy `student_scope` | unchanged |
| `GET /workflows/overseas/applications` | `agent_id IN org` | `application_scope` | unchanged |
| `workflows._assigned_application` (agent branch: document upload/download, updates) | `agent_id IN org` | also `student_id IN visible_student_user_ids` → existing `403 "Application is outside your assigned scope"` | unchanged |
| `POST /workflows/overseas/documents` link check | link in org | `student_scope` → existing `403` | unchanged |
| `GET …/documents/{id}/download` (agent branch) | link in org | `student_scope` → existing `403` | unchanged |
| `GET /lookups/overseas-students` (agent, non-link) | linked in org | `visible_student_user_ids` | unchanged |
| `GET /lookups/overseas-students?purpose=link` | excludes the org's links | unchanged (org-wide exclusion, so Staff cannot re-link another's student) | unchanged |
| `GET /lookups/overseas-applications` (agent) | `agent_id IN org` | `application_scope` | unchanged |
| `services/portal._agent` students / applications / documents / dashboard / reports | org-wide | `student_scope` / `application_scope` | unchanged, plus archived hidden from students list and the "Students" KPI |

Commission creation (`_maybe_trigger_agent_commission`) is untouched.

### 5.4 Students router — new `app/api/agent_students.py`, prefix `/workflows/overseas/agent/crm/students`

Registered in `app/main.py`'s router tuple under `/api/v1`, next to `agent_team.router`.

**Caller gate:** `role == 'agent'`, `division == 'overseas'`, `agent_denial_reason(user) is None`, else `403`.
`super_admin` is not admitted (these routes are agency-internal).

**Scope:** every query uses `student_scope(user)` in its `WHERE` clause; by-id routes return `404 "Student not
found"` when nothing matches. Scope is never checked after loading.

| Route | Who | Behaviour |
|---|---|---|
| `GET ""` | Master: whole agency. Staff: assigned only | query `q` (name/email/phone, ≤100 chars, `LIKE`-escaped), `include_archived` (default `false`), `assigned` = `me` \| `none` \| `<member_id>` (Master only; Staff → `422`), `limit` 1–100 (default 20), `offset` ≥ 0. Returns `{items, total, limit, offset}` ordered by name, id. |
| `POST ""` | Master, Staff | create a student with no login (§5.5). Staff creator → assigned to them; Master → unassigned. `201 {student}` |
| `GET /{id}` | scoped | `200 {student}` (item shape plus every field, `created_by`, `archived_by`, timestamps) |
| `PATCH /{id}` | scoped | only for a student with no login (linked → `409 "Linked students are edited in their own account"`); archived → `409 "Unarchive this student first"`; absent key = unchanged, `null` clears an optional field, `full_name` cannot be cleared; re-runs the duplicate check when `email` or `phone` changes |
| `POST /{id}/archive` | Master | scoped `404` first, then Staff → `403 "Only an agency Master can archive students"`; already archived → `409` |
| `POST /{id}/unarchive` | Master | as archive; already active → `409` |
| `POST /{id}/assign` `{member_id: UUID \| null}` | Master | target must be an **active `role='staff'` member of the same agency** (G5), else `422 "Choose an active Staff member of this agency"`; archived → `409` |

**Item shape:** `{id, has_login, full_name, email, phone, preferred_country, preferred_intake, status,
assigned_to: {id, code, full_name, status} | null, created_at}`. Linked students' name, email and phone come from
`users`. Explicit dicts only; `agent_id`, `student_id` and `phone_digits` are never returned. `assigned_to.status`
shows a deactivated assignee (G5).

**Transactions:** every write = one transaction: `lock_org(org)` → re-check `org.status == 'active'` → scoped
load → validate → write → audit → commit. The organisation lock serialises create vs create (so two concurrent
creates cannot both pass the duplicate check), assign vs archive, and archive vs edit.

**Audit** (same transaction, fail closed, `SEC-001`): `agent_student.create | update | archive | unarchive |
assign | duplicate_override`, `entity_type='agent_student'`, `entity_id=<row id>`; metadata holds field names,
member ids and match counts only — never names, emails or phones. The legacy link route's audit
(`agent.student_link`) gains `assigned_member_id` for a Staff link.

**Operational logging** (`logger = logging.getLogger("app.agent_students")`, the `extra_fields` pattern):
`agent_student_created|updated|archived|unarchived|assigned` at INFO and `agent_student_duplicate_warned` /
`agent_student_duplicate_overridden` at INFO with `{org_id, actor_id, student_id, match_count}`; ids and counts
only. A lock or commit failure is not caught: FastAPI returns `500` and the transaction rolls back.

**Contract details (API review):**

- **Error shape:** FastAPI `{"detail": ...}`, as every implemented endpoint. String `detail` for `403/404/409`;
  the duplicate `409` uses a structured `detail` with a `message` key (precedent `workflows.py:1232`). `detail`
  strings are stable and listed in `API_CONTRACT.md`.
- **Existence masking:** the out-of-scope `404` is an intentional existence mask, written into
  `RBAC_MATRIX.md` §2.8 as `API_CONTRACT.md` §0.3 requires.
- **Write responses** return the full `{student}` detail shape.
- **Idempotency (§0.2):** no `Idempotency-Key`. `PATCH` is naturally idempotent; archive/unarchive answer `409`
  when the state has already changed; re-assigning the current assignee is `200` with no audit row; a `PATCH`
  with no changed field is `200` with no audit row. `POST` create is not idempotent when it has neither email nor
  phone (stated residual); the UI prevents double-submit.
- **Concurrent edits:** last write wins per field (no ETag — none is contracted); PATCH carries changed fields
  only.
- **Server-owned fields** (`agent_id`, `student_id`, `status`, `assigned_member_id`, `archived_*`,
  `phone_digits`) are not in the schemas (`extra="forbid"` as AGN-002's `AgentStaffUpdate`, so a body carrying
  them is `422`) — tested.
- **Query validation:** unknown `assigned` value, paging out of range, or `q` over 100 characters → `422`.

### 5.5 Validation and duplicate warning

- Schemas `AgentStudentRecordCreate` / `AgentStudentRecordUpdate` (`schemas.py`, `extra="forbid"`): trimmed
  strings; `clean_free_text` (control and bidi-override characters refused); `email` pattern as
  `AgentMasterInvite`; `date_of_birth` not in the future and not before 1900; `graduation_year` range as §4;
  `notes` ≤ 2000; `confirm_duplicate: bool = False`. Errors: `422`, never echoing the value. Validation runs
  after the role and scope checks and before any write.
- `phone_digits` = digits of `phone`. **Match key (browser QA-04, owner Q2, 2026-10-01):** the last 10 digits when there are at least 10 (country code and trunk 0 ignored), otherwise all digits, used only when ≥ 7.
- **Match** within the agency (`agent_id IN org_member_ids`), excluding the row being edited: `lower(email)`
  equal, or match keys equal. Linked students match on their `users.email` / `users.phone`. Archived
  students included (F3). The match never reads `users` beyond the agency's own linked rows, so it cannot
  discover platform accounts.
- No match, or `confirm_duplicate: true` → proceed (an override writes `agent_student.duplicate_override`).
- Otherwise `409 {"detail": {"message": "A student with this email or phone already exists in your agency",
  "code": "possible_duplicate", "matches": [{id, full_name, has_login, status, matched_on: ["email" |
  "phone"]}], "hidden_matches": n}}`. For Staff, `matches` holds only students in their `student_scope`; the rest
  are counted in `hidden_matches` (F4). Nothing is written.

### 5.6 Existing routes — Master-visible changes (backward compatible)

| Route | Change |
|---|---|
| `GET /workflows/overseas/agent/students` | same response shape; now excludes `status='archived'` (D5). Rows with no login are already excluded by its inner join on `users`. |
| `POST /workflows/overseas/agent/students` | relinking a student whose link is archived → `409 "This student is archived — unarchive them first"` (same status code as today's "already linked") |
| `services/portal._agent` | `students` section and "Students" KPI exclude archived. Applications, documents and history of archived students still show (D5). |

## 6. Frontend

- **Types** (`lib/types.ts`): `User.agent_member_role?: "master" | "staff" | null` (AGN-002's line).
- **Navigation** (`lib/navigation.ts`): `agentNavFor(nav, memberRole)` (AGN-002's function: Staff lose Team and
  Commissions). `PortalPage` applies it and shows "Agency Staff" as the role label (AGN-002's lines).
- **`lib/agentStudents.ts`** (pattern of `lib/schoolStudents.ts`): API client, payload building (changed fields
  only for PATCH), client-side validation mirroring §5.5, and `duplicateDetail(detail)` for the structured `409`;
  every other error goes through `lib/apiErrors.detailMessage`.
- **`AgentStudentsPanel`** (rendered by `WorkflowPanel` for `role === "agent" && section === "students"`, above
  the existing "Link student" form, which is kept unchanged under its own `h3`):
  - toolbar: debounced search, "Show archived" toggle, Master-only "Assigned to" filter, "Add student";
  - table: name, contact, preferred country/intake, "Has login" badge, assigned to (with "deactivated" text when
    so), status; row actions View and (Master) Archive/Unarchive, Assign; 20 per page with previous/next and
    "Showing x–y of n";
  - Master-only controls are shown from `user.agent_member_role === "master"`; the server enforces them anyway;
  - states: loading (skeleton row, `aria-busy`), empty ("No students yet" + Add student), empty with filters
    ("No students match" + Clear filters), error (message + Retry), 401 (`AccessUnavailable` sign-in link), 403
    (server message);
  - detail side panel (F5): every field, has-login, assignment, created/archived by and when; Edit for a student
    with no login that is not archived; its own loading and 404 ("This student is no longer available") states;
  - Archive and Assign use the codebase's **inline confirmation** pattern (`AgentTeamPanel`,
    `AgentApprovalPanel`, `TierDowngradeConfirm`): Confirm / Cancel in place; focus returns to the opener;
    results announced in the panel's single `role="status"` / `aria-live="polite"` region.
- **`AgentStudentForm`** (create/edit): fields grouped Personal, Contact, Academic, Preferences under `fieldset`
  + `legend`; only Full name required (marked in text); `type="email"`, `type="tel"`, `type="date"` with `max` =
  today; each error tied by `aria-describedby` with `aria-invalid`; focus to the first invalid field after a
  failed submit; Notes counter; Save disabled while busy (re-focused with `lib/focus.refocus`); leave prompt while
  dirty (`PsychometricResultsForm` pattern); on `409 possible_duplicate` lists the matches and "n more you can't
  view", with "Save anyway" (same payload + `confirm_duplicate: true`) and "Go back".
- **Reused, not rebuilt:** `lib/apiErrors.ts` (`detailMessage`, `isPage`, `NOT_COMPLETED`, `Page<T>`),
  `lib/focus.refocus`, `AgentApprovalPanel`'s paging (and `page` in the URL), the `.table` + `data-label`
  stacked-card rule of `.table.psy-records` (a sibling class, same rule), `.record-details`, `SchoolStudentFields`'
  layout, `form`, `form-message`, `form-error`, `btn secondary small`, `muted`.
- **Perceived performance:** first load shows a skeleton; later loads keep the current rows visible and dimmed
  with `aria-busy`; search debounced 300 ms; each list fetch uses an `AbortController` and a response for an
  older query is discarded; after a write the row is updated from the response in place, and the list is
  refetched only when the change moves the row out of the current filter.
- **Keyboard and mobile:** Tab order toolbar → list → paging; row actions are `<button>`s; detail panel below
  the list on narrow screens with focus moved to its heading; Esc closes it and returns focus to the row's View
  button; the table becomes cards below 640 px; no horizontal overflow at 320 px; touch targets ≥ 44 px.
- **Unchanged:** `AgentApplicationCreatePanel`, `AgentApprovalPanel`, `AgentTeamPanel`, `RegisterForm`.

**Browser-QA revisions (2026-10-01, `docs/quality/AGN-004_BROWSER_QA_2026-10-01.md`):** `PortalPage` renders the agent Students
page as a "Students" header with the panel first and full width (heading "All students"), then the AGT-002 roster retitled
"Application status", then `WorkflowPanel` (Link student) — the panel is no longer rendered by `WorkflowPanel` (QA-01/02, owner
Q1). The form asks before Cancel or an in-app link discards unsaved input (QA-03); a server 422 is shown on its field (QA-05); the
main Save is disabled while the duplicate warning is open (QA-08). The panel keeps `q`, `archived` and `page` in the URL (QA-06),
offers Retry on a failed detail (QA-09), every panel button is 44 px on phones (QA-07), and emails break after `@`/`.` (QA-10).

## 7. Security (security-and-hardening review)

**Trust boundaries:** the new HTTP routes (JSON bodies and query strings from Masters and Staff); stored student
text rendered back to other agency members. **Assets:** personal data of students who have no account (name,
contact, date of birth — may include minors), agency tenancy, Master-only authority.

| Area | Design |
|---|---|
| Authentication | Unchanged: `edusphere_access` httpOnly cookie (`secure` by setting, `SameSite=Lax`); `get_current_user` re-reads `users.active` and the membership on every request. No new auth flow or token. |
| Authorization | Every route: role + division + `agent_denial_reason` (org pending/suspended, member deactivated). Master-only actions (archive, unarchive, assign; team; commissions) check `is_agent_staff` server-side; hiding them in the UI is not the control. `super_admin` not admitted to the new routes. |
| IDOR | Never relies on UUIDs being unguessable: every by-id load carries `student_scope` in the `WHERE` clause → `404`; applications and documents carry `application_scope` for Staff. `assign.member_id` must be an active Staff member of the same agency. Cross-agency and cross-Staff matrices tested per route, new and existing. |
| Role escalation | Staff cannot archive, unarchive, assign, manage the team, see commissions, or be approved/rejected by Overseas Admin. Server-owned fields are rejected by `extra="forbid"`. The member role is never taken from a request. Downgrade refuses while Staff exist. |
| Input validation | Pydantic at the boundary: length caps, `clean_free_text`, email pattern, date/year ranges, `notes` ≤ 2000, `q` ≤ 100, paging bounds. Client validation is usability only. |
| XSS | React escapes all text; no `dangerouslySetInnerHTML`/`innerHTML`; `PortalSection` renders values as text. A test renders `<script>` / `<img onerror>` in a name and asserts plain text. |
| CSRF | Unchanged: `SameSite=Lax` cookies are not sent on cross-site `POST`/`PATCH`; JSON bodies need a preflight, which CORS (`allow_origins=[settings.frontend_url]`, `main.py:58`) refuses. Body-less archive/unarchive rely on `SameSite=Lax`, as AGN-001's approve/deactivate. |
| SQL injection | SQLAlchemy expressions with bound parameters; search uses `ilike(..., escape="\\")` with `%`, `_`, `\` escaped; migration uses fixed DDL/DML only. |
| Token/session | No change. (AGN-002 adds session versioning; not needed here because no Staff credential changes in AGN-004.) |
| Secret exposure | No new secret or config. |
| Sensitive logs | Logs and audit metadata: ids, codes, field names, counts only. The duplicate `409` returns personal data only for rows the caller can already see. |
| Rate limiting | No new limit: no write endpoint in this codebase has one except invites and link search, and every new route needs an approved agency login. The duplicate check only confirms an email/phone inside the caller's own agency (to Staff only as a count). Stated residual. |
| Audit | Same-transaction audit for every write; failure rolls the write back (`SEC-001`); duplicate overrides audited. |
| Data privacy | Fields limited to §5 Step 1 (purpose: counselling and applications). **Residual — `NEEDS_CONFIRMATION`:** a student with no login cannot file a data-subject request (`data_subject_requests` is keyed to a requesting user) and AGN-004 has no hard delete (D5), so erasure has no path yet; recorded in `PRD_OPEN_ITEMS.md`, not built. |

Stated residuals: no read-endpoint rate limiting; no field-level edit history; last write wins; non-idempotent
create without email/phone; no erasure path for students with no login.

## 8. Acceptance criteria

| ID | Criterion |
|---|---|
| AGN-004-AC01 | A Master or Staff member creates a student with no login → `201`; one `agent_students` row with `student_id IS NULL` and `agent_id` = the creator; the `users` row count is unchanged. |
| AGN-004-AC02 | Created (or linked) by Staff → assigned to that Staff member; by a Master → unassigned. |
| AGN-004-AC03 | A Master and the assigned Staff member view a student and edit one with no login; editing a linked student → `409`; editing an archived student → `409`; invalid input or a server-owned field → `422` and nothing is written. |
| AGN-004-AC04 | A Master archives and unarchives. An archived student is absent from the default list, the roster and the portal Students section/KPI; present with `include_archived=true`; readable by id; its applications, commissions and audit history unchanged. Staff archiving → `403`. |
| AGN-004-AC05 | Staff get `404` on read, edit and archive of a student assigned to someone else, an unassigned student, or any student of another agency; Staff lists contain only their assigned students. |
| AGN-004-AC06 | Staff see only their assigned students' links, applications and documents on every existing agent path (roster, application list/create, document upload/download, lookups, portal pages); another Staff member's student is refused with that path's existing out-of-scope status. |
| AGN-004-AC07 | A Master of another agency gets `404` on every by-id route and never sees the rows in lists. |
| AGN-004-AC08 | Same email (any case) or phone (same last 10 digits; under 10 digits exact, ≥ 7) within the agency — archived and linked students included — → `409 possible_duplicate`; resending with `confirm_duplicate: true` → `201` and an override audit row. A match in another agency never warns. Staff see matches they cannot view only as `hidden_matches`. |
| AGN-004-AC09 | Assignment targets only an active Staff member of the same agency (`422` otherwise). A deactivated Staff member keeps their students; Masters still see them and can reassign. |
| AGN-004-AC10 | Staff get `403` on Team and Commissions (API and portal pages) and do not see those nav items; Staff never count toward the 3-Master limit or last-Master rule and never receive commission notifications; Overseas Admin cannot approve/reject a Staff user. |
| AGN-004-AC11 | Every write writes an audit row in the same transaction with no personal data; if the audit write fails, nothing is written. |
| AGN-004-AC12 | Migration `0049_agent_students_crm`: existing rows unchanged; upgrade → downgrade → upgrade leaves pre-existing rows identical; downgrade refuses while students with no login, assignments or archived students exist (the Staff pieces and their Staff-exist refusal moved to AGN-002's `0047_agent_org_staff` on the 2026-10-01 merge); each new column, CHECK and index is a no-op on a database that already has it. |
| AGN-004-AC13 | The Students screen works at 320 px and keyboard-only, with loading, empty, error and 401 states. |

## 9. Tests (written first, per behaviour; real runs, never judged by reasoning)

Staff are created by a test helper (`tests/agn004_helpers.py`: a `role='agent'` user, an approved `agent`
assignment and an `AgentOrgMember(role='staff', seq=staff_seq+1, code=<PREFIX>-S###)`), mirroring AGN-002's
`create_staff` data shape.

**API** (`apps/api/tests/`):

- `test_agn_004_schema.py` — migration constants, model constraints (role CHECK, org-role-seq unique, identity
  CHECK, status CHECK).
- `test_agn_004_migration.py` — AC12 (round trip on seeded rows; refusals; Staff pieces idempotent).
- `test_agn_004_schemas.py` — field validation, `extra="forbid"`.
- `test_agn_004_students.py` — AC01–AC05, AC07, AC08, AC11: create/edit/view/archive/unarchive/assign by role;
  `users` count unchanged; Staff `404` matrix; cross-agency matrix; duplicate warning by email case, phone
  digits, archived, linked, other agency, override, `hidden_matches`; list filters, paging, `include_archived`;
  linked-student edit `409`; no-op PATCH / re-assign `200` without audit; `LIKE` metacharacters literal;
  response key allowlist; `super_admin` `403`; audit rows without personal data; audit failure rolls back; two
  concurrent creates with one email → exactly one `201`; log capture without personal data.
- `test_agn_004_staff_scope.py` — AC02 (Staff link assigned), AC06 (every existing path, parametrised), AC09,
  AC10 (team, commissions, portal pages, Master rules, notifications, admin approve/reject).
- **Existing, run unedited:** `test_agt_002_referrals`, all six `test_agn_001_*` files,
  `test_agt_003_commission_accrual`, `test_agt_004_commission_payout`, `test_enh_031_lookups_students`,
  `test_sec_001_audit_trail`, `test_rpt_002_overseas_reporting`, `test_role_assignments`,
  `test_enh_027_migration`. (`test_agn_001_schema.py` pins `ck_agent_org_members_role = 'master'`; AGN-002 edits
  it for the same widening. If it fails here, the edit is AGN-002's identical one — a changed decision, not a
  test bent to pass — and is recorded.)

**Web** (vitest): `lib/agentStudents.test.ts`; `navigation.test.ts` (`agentNavFor`, AGN-002's cases);
`AgentStudentsPanel.test.tsx` (every state, filters, paging, Master vs Staff controls, inline confirmation with
focus return, live region, rows kept while refetching, stale response discarded, markup rendered as text);
`AgentStudentForm.test.tsx` (validation, changed-fields PATCH, focus to first invalid field, double-submit
blocked, duplicate flow, leave prompt). Existing `Enh031ExistingPickers`, `AgentTeamPanel`, `RegisterForm`,
`AccessUnavailable` tests run unedited.

**Playwright** `agn-004-agent-students.spec.ts` (Master flows only on this branch — Staff logins need AGN-002):
create, duplicate warning, save anyway, edit, archive, find under "Show archived", unarchive, assign; keyboard-only
run; 320 px run. Unique names per run. Existing `agt-002-referrals`, `agn-001-multi-tenant`,
`enh-031-searchable-pickers`, `agt-004-commission-payout` run unedited. **Staff browser flows are validated after
the AGN-002 merge** (stated gap, §11).

## 10. Regression risks

| Risk | Mitigation |
|---|---|
| Master behaviour changes while adding Staff scoping | `student_scope`/`application_scope` return exactly today's clauses for a Master; every existing agent suite run unedited |
| A Staff path missed in G4 | one parametrised test over every agent path in §5.3; grep of `org_member_ids` call sites in the plan |
| Staff counted as Masters | role filters identical to AGN-002; mixed Master/Staff tests |
| Rows with `student_id NULL` reaching code that joins `users` | old routes inner-join and drop them; tests show roster, picker, link lookup, commissions and reports unchanged |
| Roster now hides archived links | intended (D5), recorded in `API_CONTRACT.md`; application create already refuses non-active links |
| Migration CHECK on `status` fails on unexpected values | pre-check query in the migration |
| AGN-002 merge conflicts | G2 code identical to AGN-002's; guarded migration; §12 merge notes |
| Organisation lock contention | same pattern as AGN-001 E12; short writes |
| Shared E2E database | unique names per run |

## 11. Documentation (updated with the build)

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-042`: D1, D3–D5, D7, D8, G1–G5, the citation correction, the part of
`DEC-SCOPE-038` D13 / AGN-002 S1 it narrows); `ENHANCEMENT_BACKLOG.md` (AGN-004 entry, ACs, Appendix B note);
`DATA_MODEL.md` §6.8/§6.8a; `API_CONTRACT.md`; `RBAC_MATRIX.md` §2.8 (Staff assigned-only; `404` mask);
`SECURITY_CONTROLS.md`; `THREAT_MODEL.md`; `PRD_OPEN_ITEMS.md` (erasure, `NEEDS_CONFIRMATION`); `RTM.md`;
`SCREEN_CATALOG.md` / `screen_catalog.json`; `CONFLICT_MATRIX.md` `C-10` note.

## 12. Merge with AGN-002 (notes for whoever merges second)

- Migrations: re-chain the later one (`0047_agent_org_staff` → `0047_agent_students_crm` or the reverse); the
  guarded Staff pieces make the second a no-op for them; rename the file number to `0048` for order. AGN-004's
  `downgrade()` also reverts each Staff piece only if still present (final review I1), so rolling back through both works
  whichever runs first; AGN-002's own `downgrade()` is unguarded, so if AGN-004's migration is the later one, it is
  rolled back first — or AGN-002 adopts the same guards on merge.
- Decision IDs: `DEC-SCOPE-040` (AGN-002) and `DEC-SCOPE-042` (AGN-004) do not collide.
- G2 code is identical to AGN-002's; take either side. AGN-002's `_agent` portal and `lookups` changes do not
  narrow Staff scope — keep AGN-004's G4 narrowing on top.
- After the merge: run the AGN-002 and AGN-004 suites together and the Staff browser flows (Staff sign-in, sees
  only assigned students, another's student is "not found").
- **Merged 2026-10-01** (`git pull origin main`, AGN-002 PR #28): migration renamed `0049_agent_students_crm`,
  `down_revision = "0047_agent_org_staff"`; the Staff pieces and their tests removed here (AGN-002 owns them). Shared Staff
  code (`admin.py`, `agent_team.py`, `agent_orgs.py`) taken from main, with `lock_active_org` re-added. AGN-002's
  `test_staff_see_the_organisations_students` asserted S1's agency-wide reach; it now assigns the student and also asserts
  an unassigned one is hidden (G4, owner-approved). AGN-001/002/004, AGT and ENH-031 API suites: 357 passed after that
  change; web vitest 1231 passed, tsc 0 errors, eslint 0 errors (31 warnings, unchanged), build OK. E2E and the Staff
  browser flows wait for the `agn004` stack to be rebuilt from the merged code.
- **Merged again 2026-10-01** (ENH-030, PR #27, on main first): ENH-030's `0048_school_attendance_records` also followed
  `0047_agent_org_staff` (two Alembic heads), so this migration became `0049_agent_students_crm`, `down_revision =
  "0048_school_attendance_records"`; its test now also asserts the single head. ENH-030 holds `DEC-SCOPE-041` on main, so this
  feature's decision became `DEC-SCOPE-042` (register ID note). Main's ENH-030 renumbering had also turned three AGN-001 backlog
  references from `DEC-SCOPE-038` into `041`; restored to `038` in the merge.

## 13. Completion gates (not claimed by implementation alone)

AGN-004 is COMPLETE only when: AC01–AC13 pass in real runs; the listed existing suites pass unedited (or with
the recorded AGN-002-identical schema-test edit); the backend full suite shows no new failures beyond the
recorded provider-credential baseline; migration round trip verified; web vitest, `tsc`, `eslint` and
`npm run build` clean; Playwright AGN-004 spec and the listed related specs pass on a rebuilt stack; browser
validation (responsive 320 px, keyboard, screen-reader labels) done in a real browser; an **independent Codex
review** done and its findings resolved; Staff browser flows validated after the AGN-002 merge; docs in §11
updated; RTM row written with evidence.
