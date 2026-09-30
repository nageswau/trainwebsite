# AGN-004 — Agent Students: Master/Staff Create, Edit, View and Archive Students Who Never Log In — Design

**Status:** Design approved in-session, 2026-09-30, section by section (data model, backend, frontend,
acceptance/tests/risks). Superpowers architectural path: brainstorming → this design doc → `writing-plans`
next. Reviewed the same day against the `api-and-interface-design`, `frontend-ui-engineering` and
`security-and-hardening` skills; findings folded into §5.1, §5.4, §5.5, §6, §7, §9 and §11. Written spec
awaiting user review. No code written.

**Source requirement:** the user's `AGN-004` statement (2026-09-30): *"Master/Staff create, edit, view and
archive students who never log in (§2 Students, §5 Step 1; DEC-ROLE-004; DEC-SCOPE-035 D3)."* Source
sections: `functionalities/edusphere_markdown/Agent CRM Functionalities.md` (`EVID-015`,
`DERIVED_BLUEPRINT`) §1B, §2 "Students", §3, §5 Step 1, §6.

**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-040` (to be recorded with
this spec's commit; provisional number): D1–D8 below, `EXPLICIT_APPROVAL` (user, in-session, 2026-09-30).
`DEC-ROLE-004` (no login for agent-referred students; the agent acts on their behalf) applies unchanged.

**Citation correction (recorded, not silently fixed):** the requirement cites `DEC-SCOPE-035 D3`.
`DEC-SCOPE-035` is ENH-027's psychometric decision; the agent tenancy decision is `DEC-SCOPE-038`, whose D3
is the account-code rule. Neither decides agent students. This feature's decisions are `DEC-SCOPE-040`.

**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §AGN-004 (to be added; AGN-004-AC01…AC14 = §8).

**Branch:** `feature/agn-004-agent-students` (from `main` at `9d355e8`, AGN-001 merged).

## 1. Scope

**In scope:** a Staff member type in an agent organisation (invite, deactivate, S-codes); students with no
login stored on `agent_students`; create / edit / view / archive / unarchive / assign; Staff see only their
assigned students; a within-agency duplicate warning; Staff restricted to the Students area.

**Out of scope:** applications, documents and commissions for students with no login (D8 — a later feature,
which will add an `agent_student_id` bridge like SCH-010's `school_student_id`); hard delete; bulk import;
Staff performance; CRM settings; Staff dashboards; any change to `users`, `overseas_applications`,
`student_documents`, `agent_commissions`, JWT/cookies, or non-agent roles.

## 2. Approaches considered

| Choice | Option | Verdict |
|---|---|---|
| Staff representation | **A. `User.role='agent'` + `AgentOrgMember.role='staff'`** | **Chosen.** Reuses the AGN-001 invite, welcome-link, throttle and suspension gate. Staff are denied every existing agent route by one change in `agent_denial_reason` (fail closed, no call-site edits). |
| | B. New `User.role='agent_staff'` | Rejected: the new role must be threaded through the portal role map, nav, login redirect, admin role validator, RBAC permissions and the suspension gate (~10 more touch points). |
| Student storage | **A. Extend `agent_students`** | **Chosen.** One table for both kinds of student; old link/application code keeps working; archive reuses the existing `status` column. |
| | B. New `agent_crm_students` table | Rejected: the "all students" list, archive and assignment would each merge two sources. |
| Agency key on `agent_students` | **Scope by `agent_id IN org_member_ids(user)`** | **Chosen (F1).** Same as AGN-001 E1: membership is permanent (`uq_agent_org_members_user`), so `agent_id` fixes the row's agency. |
| | Add `org_id` | Rejected (F1): AGN-001 §2 rejected exactly this — `org_id` and `agent_id` could drift apart. |

## 3. Decisions

`DEC-SCOPE-040` (user, in-session, 2026-09-30, `EXPLICIT_APPROVAL`):

- **D1 — Staff in scope.** Lifts the Staff-login, assignment and ownership part of `DEC-SCOPE-038` D13 /
  `C-10`. Staff performance, CRM settings and the rest of `EVID-015` stay blocked.
- **D2 — Staff accounts.** A Master invites Staff by email, exactly as Masters are invited (D9 welcome link,
  same token and expiry rules). Codes `<PREFIX>-S001`, monotonic per agency, never reused. Staff invites
  share the agency's 10-per-24-hours invite limit (R1). No cap on Staff count.
- **D3 — Two kinds of student, side by side.** The existing "link a student who has an account" flow stays.
  A new flow creates a student with no login; their details live on `agent_students` and no `users` row is
  ever created for them.
- **D4 — Assignment.** A student created by Staff is assigned to that Staff member. A student created by a
  Master starts unassigned (visible to Masters only). Only a Master assigns or reassigns. Deactivating a
  Staff member unassigns their students.
- **D5 — Archive.** Master only; a Master can also unarchive. Archived students leave default lists but stay
  in history and reports.
- **D6 — Staff reach.** Staff see only the Students area, and only students assigned to them. Anything else
  in the agency is `404` (existence not revealed); every other agent route is `403`.
- **D7 — Duplicate warning.** Within the agency: same email (case-insensitive) or same normalised phone →
  a warning listing the matches; saving again with `confirm_duplicate: true` proceeds.
- **D8 — Downstream deferred.** Applications, documents and commissions for students with no login are a
  separate later feature.

Staff meaning (confirmed in-session): **agent organisation staff** — employees of one agency (`EVID-015`
§1B "Counselor / Executive"), invited and managed only by that agency's Masters. Not EduSphere internal
staff, not school staff, not independent agents; they cannot self-register and receive no commissions.

Design decisions (confirmed in-session, 2026-09-30):

- **F1 — No `org_id` on `agent_students`** (§2).
- **F2 — Linked students are not editable here.** Their name, email and phone belong to the student's own
  `users` account. For linked students AGN-004 allows view, archive, unarchive and assign only.
- **F3 — Duplicate scope includes archived and linked students**, marked as such.
- **F4 — Staff see matches they cannot view only as a count** (`hidden_matches`), never name or id.
- **F5 — Detail view is a side panel on the Students screen**, not a new route (avoids a
  `students/[id]` vs `[section]` routing clash).

## 4. Data model — migration `0047_agent_students_crm` (after `0046_agent_orgs`)

**`agent_orgs`:** add `staff_seq INTEGER NOT NULL DEFAULT 0` (highest Staff number ever issued).

**`agent_org_members`:** replace `ck_agent_org_members_role` (`role = 'master'`) with
`role IN ('master', 'staff')`. Codes stay unique by `uq_agent_org_members_code`.

**`agent_students`** — additive; every existing column keeps its meaning:

| Column | Type | Notes |
|---|---|---|
| `student_id` | `users.id` FK, **now nullable** | `NULL` = a student with no login |
| `agent_id` | unchanged, NOT NULL | now means "created or linked by"; fixes the agency (F1) |
| `status` | unchanged `String(30)` | new CHECK `status IN ('active', 'archived')`; existing rows are all `'active'` (checked before the constraint is added; the migration fails loudly otherwise) |
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

Constraints and indexes: CHECK `ck_agent_students_identity` = `student_id IS NOT NULL OR full_name IS NOT
NULL`; indexes `(agent_id, status)`, `(agent_id, lower(email))`, `(agent_id, phone_digits)`,
`(assigned_member_id)`. `uq_agent_student (agent_id, student_id)` is kept (PostgreSQL treats `NULL`s as
distinct, so rows with no login never collide).

**Upgrade** preserves every existing row unchanged (all new columns `NULL`, `staff_seq` 0).
**Downgrade** deletes rows with `student_id IS NULL` (count logged), drops the new columns, indexes and
constraints, restores `student_id NOT NULL` and the Master-only role CHECK; it refuses (raises) if any
`role='staff'` member exists, since those users would otherwise become Masters.

## 5. Backend

### 5.1 Gate (`core/rbac.py`)

- `agent_denial_reason(user, *, allow_staff: bool = False)`: after the existing membership, deactivation,
  suspension and pending checks, returns `STAFF_MESSAGE = "This area is for agency Masters"` when
  `membership.role == 'staff'` and `allow_staff` is false.
- The four existing call sites (`workflows._require`, `api/portal.py`, `lookups._allow`,
  `agent_team._require_master`) keep the default → Staff get `403` on every existing agent route.
- A deactivated Staff member gets `STAFF_DEACTIVATED_MESSAGE = "Your Staff account is deactivated"` (the
  existing Master message is unchanged). In practice deactivation also sets `users.active = false`, so
  `get_current_user` answers `401 "User unavailable"` on their next request.
- `agent_team._require_master` additionally requires `membership.role == 'master'` (second layer).
- `deps.get_current_user` already eager-loads `agent_membership` + `.org`; no change.

### 5.2 AGN-001 helpers made Master-only (`services/agent_orgs.py`)

| Helper | Change | Protects |
|---|---|---|
| `count_active_masters` | filter `role == 'master'` | D4 3-Master limit, D8 last-Master rule |
| `deactivate_master` | "other active Masters" query and the member lookup filter `role == 'master'` (a Staff id → `404 "Master not found"`) | R3 no self-lockout |
| `notification_recipients` | filter `role == 'master'` | D12 commission notifications |
| `_invite_wait_seconds` | counted actions add `agent_org.staff_invite` and `agent_org.staff_invite_rejected` | R1 shared invite limit |
| `set_org_status` (write-through) | unchanged — Staff assignments follow the organisation like Masters | AGT-001-AC02 |
| `org_member_ids` | unchanged — includes Staff user ids (their rows belong to the agency) | D1 |

`invite_master` becomes a thin wrapper over a new `invite_member(db, org, actor, *, kind, full_name, email,
phone)`: `kind='master'` keeps today's behaviour exactly (limit, `master_seq`, `M` code, audit
`agent_org.master_invite`); `kind='staff'` skips the Master limit, uses `staff_seq` and the `S` code, and
audits `agent_org.staff_invite` / `agent_org.staff_invite_rejected`. Both create `User(role='agent',
division='overseas')` with an unusable password and an approved `agent` assignment, and issue the welcome
token.

New `deactivate_staff(db, org, member_id, actor)` (no commit; `org` locked): `404 "Staff member not found"`
unless a `role='staff'` member of this organisation; `409 "Already deactivated"`; sets the member
`deactivated`, `users.active = false`, `revoke_welcome_tokens`, then `UPDATE agent_students SET
assigned_member_id = NULL WHERE assigned_member_id = <member>`; audits `agent_org.staff_deactivate` with
`{member_id, code, unassigned: n}`.

### 5.3 Team endpoints (`api/agent_team.py`, Masters only, organisation row locked for writes)

| Route | Behaviour |
|---|---|
| `GET /workflows/overseas/agent/team` | unchanged keys; `masters` now lists `role='master'` members only; **adds** `staff: [{id, code, full_name, email, status, invite_pending, assigned_students}]` |
| `POST /workflows/overseas/agent/team/staff` `{full_name, email, phone?}` (`AgentMasterInvite` schema reused) | as the Master invite: `429` over the limit, `409 "Email already exists"`, `201 {member, **delivery}` with the raw token stripped |
| `POST /workflows/overseas/agent/team/staff/{member_id}/deactivate` | `deactivate_staff`; `200 {member, unassigned}` |

### 5.4 Students router — new `app/api/agent_students.py`, prefix `/workflows/overseas/agent/crm/students`

Registered in `app/main.py`'s router tuple under `/api/v1`, next to `agent_team.router`.

**Caller gate:** `role == 'agent'`, `division == 'overseas'`, `agent_denial_reason(user, allow_staff=True)
is None`, else `403`. `super_admin` is not admitted (these routes are agency-internal).

**Scope** (one helper, `_scoped(stmt, user)`): `AgentStudent.agent_id IN org_member_ids(user)`; for Staff
also `AgentStudent.assigned_member_id == user.agent_membership.id`. Every by-id route loads with the scope
in the `WHERE` clause and returns `404 "Student not found"` when nothing matches. Scope is never checked
after loading.

| Route | Who | Behaviour |
|---|---|---|
| `GET ""` | Master: whole agency. Staff: assigned only | query `q` (name/email/phone, ≤100 chars, `LIKE`-escaped), `include_archived` (default `false`), `assigned` = `me` \| `none` \| `<member_id>` (Master only; Staff → 422), `limit` 1–100 (default 20), `offset` ≥ 0. Returns `{items, total, limit, offset}` ordered by name, id. |
| `POST ""` | Master, Staff | create a student with no login (§5.5). Staff creator → `assigned_member_id` = the Staff member; Master → `NULL`. `201 {student}` |
| `GET /{id}` | scoped | `200 {student}` (item shape plus every field, `created_by`, `archived_by`, timestamps) |
| `PATCH /{id}` | scoped | only for a student with no login (linked → `409 "Linked students are edited in their own account"`); archived → `409 "Unarchive this student first"`; absent key = unchanged, `null` clears an optional field, `full_name` cannot be cleared; re-runs the duplicate check when `email` or `phone` changes |
| `POST /{id}/archive` | Master | scoped `404` first, then Staff → `403`; already archived → `409` |
| `POST /{id}/unarchive` | Master | as archive; already active → `409` |
| `POST /{id}/assign` `{member_id: UUID \| null}` | Master | the target must be an **active `role='staff'` member of the same agency**, else `422 "Choose an active Staff member of this agency"`; archived → `409` |

**Item shape:** `{id, has_login, full_name, email, phone, preferred_country, preferred_intake, status,
assigned_to: {id, code, full_name} | null, created_at}`. For linked students the name, email and phone come
from `users`. Responses are built as explicit dicts (field allowlist), never an ORM dump; `agent_id`,
`student_id` and `phone_digits` are never returned.

**Contract details (API review, 2026-09-30):**

- **Error shape:** FastAPI `{"detail": ...}`, like every implemented endpoint (`API_CONTRACT.md` §0.3's
  `error_code` shape is implemented nowhere). String `detail` for `403/404/409`; the duplicate `409` uses a
  structured `detail` with a `message` key, following the existing precedent at `workflows.py:1232`.
  `detail` strings are stable and listed in `API_CONTRACT.md`.
- **Existence masking:** the out-of-scope `404` is an intentional existence mask; `API_CONTRACT.md` §0.3
  requires this to be written into `RBAC_MATRIX.md` §2.8, which this feature does.
- **Write responses** (`POST`, `PATCH`, archive, unarchive, assign) return the full `{student}` detail
  shape, so the client never needs a follow-up read.
- **Idempotency (§0.2):** no `Idempotency-Key` — not a financial action. `PATCH` is naturally idempotent;
  archive/unarchive answer `409` when the state has already changed (the ENH-005 precedent); assigning the
  current assignee again is `200` with no audit row; a `PATCH` with no changed field is `200` with no audit
  row. `POST` create is **not** idempotent: a retried create with the same email or phone is caught by the
  duplicate warning; one without either can create a second row. The UI prevents double-submit (§6).
  Recorded as a stated residual.
- **Concurrent edits:** last write wins per field (no ETag/`If-Match` — none is contracted anywhere, and
  `CLAUDE.md` forbids assuming one). The PATCH carries changed fields only, which limits clobbering.
- **Server-owned fields:** `agent_id`, `student_id`, `status`, `assigned_member_id`, `archived_*` and
  `phone_digits` are not in the create/update schemas, so a body carrying them changes nothing (tested —
  mass assignment).
- **Query validation:** unknown `assigned` value, `limit`/`offset` out of range, or `q` over 100 characters
  → `422`. A `member_id` from another agency in `assigned` simply matches nothing (scope is applied first).

**Transactions:** every write = one transaction: `lock_org(org)` → re-check `org.status == 'active'`
(`_locked_active_org`) → scoped load → validate → write → audit → commit. The organisation lock serialises
create vs create (so two concurrent creates cannot both pass the duplicate check), assign vs Staff
deactivate, and archive vs edit.

**Audit** (same transaction, fail closed, `SEC-001`): `agent_student.create | update | archive | unarchive |
assign | duplicate_override`, `entity_type='agent_student'`, `entity_id=<row id>`; metadata holds field
names, member ids and match counts only — never names, emails or phones.

### 5.5 Validation and duplicate warning

- Schemas `AgentStudentRecordCreate` / `AgentStudentRecordUpdate` (`schemas.py`): trimmed strings; control
  and bidi-override characters refused (`clean_free_text` in `schemas.py` reused); `email` pattern as
  `AgentMasterInvite`; `date_of_birth` not in the future and not before 1900; `graduation_year` range as §4;
  `notes` ≤ 2000; `confirm_duplicate: bool = False`. Errors: `422 "<field> <reason>"`, never echoing the
  value. Validation runs after the role and scope checks (a `403`/`404` always wins) and before any write.
- `phone_digits` = digits of `phone`; used for matching only when it has ≥ 7 digits.
- **Match** within the agency (`agent_id IN org_member_ids`), excluding the row being edited: `lower(email)`
  equal, or `phone_digits` equal. Linked students match on their `users.email` / `users.phone`. Archived
  students included (F3).
- No match, or `confirm_duplicate: true` → proceed (an override writes `agent_student.duplicate_override`
  with the match count).
- Otherwise `409 {"detail": {"message": "A student with this email or phone already exists in your
  agency", "code": "possible_duplicate", "matches": [{id, full_name, has_login, status, matched_on: ["email"
  | "phone"]}], "hidden_matches": n}}`. For Staff, `matches` holds only students they can see; the rest are
  counted in `hidden_matches` (F4). Nothing is written.
- The match only ever reads `agent_students` rows of the caller's agency (and, for linked rows, their own
  `users` row). It never searches `users` at large, so it cannot be used to discover platform accounts.

### 5.6 Existing routes (backward compatible)

| Route | Change |
|---|---|
| `GET /workflows/overseas/agent/students` (roster; `AgentApplicationCreatePanel`) | same response shape; now also excludes `status='archived'`. Rows with no login are already excluded by its inner join on `users`. |
| `POST /workflows/overseas/agent/students` (link) | unchanged, except relinking a student whose link is archived → `409 "This student is archived — unarchive them first"` instead of today's "already linked" (same status code) |
| `services/portal._agent` | `students` section: excludes archived; for Staff (only reachable with `allow_staff`, §5.7), only assigned rows. `dashboard` "Students" KPI counts non-archived. Applications/commissions untouched. |
| `create_overseas_application`, document upload/download, commissions, lookups | unchanged; Staff get `403` through the default gate |

### 5.7 Portal (`api/portal.py`)

`agent_denial_reason(user, allow_staff=(route_role == "agent" and section == "students"))`. Every other
section for Staff → `403`.

### 5.8 Session shape

`UserOut` gains `agent_member: {role: "master" | "staff", code: str} | null`, read from the eager-loaded
`user.agent_membership` (additive; every existing key unchanged).

## 6. Frontend

- **Types** (`lib/types.ts`): `User.agent_member?: {role: "master" | "staff"; code: string} | null`.
- **Navigation** (`lib/navigation.ts`): `agentNavFor(user)` returns `PORTAL_NAV["overseas/agent"]` for a
  Master and only the Students item for Staff; `dashboardPathFor(user)` returns `/overseas/agent/students`
  for Staff and `ROLE_DASHBOARD_PATH[user.role]` otherwise. `LoginForm`, `HeaderAuthActions` and
  `AccessUnavailable` use `dashboardPathFor`. `ROLE_DASHBOARD_PATH` is unchanged.
- **`PortalPage`:** for `overseas/agent`, builds nav from `agentNavFor(user)` and calls `notFound()` for a
  section not in it. `/auth/me` is fetched before the section payload for this key only, so a Staff member
  never triggers a `403` fetch for a Master section.
- **`lib/agentStudents.ts`** (pattern of `lib/schoolStudents.ts`): API client, payload building (changed
  fields only for PATCH), client-side validation mirroring §5.5, error-message mapping.
- **`AgentStudentsPanel`** (rendered by `WorkflowPanel` for `role === "agent" && section === "students"`,
  above the existing Master-only "Link student" form, which is kept unchanged):
  - toolbar: debounced search, "Show archived" toggle, Master-only "Assigned to" filter, "Add student";
  - table: name, contact, preferred country/intake, "Has login" badge, assigned to, status; row actions View
    and (Master) Archive/Unarchive, Assign; 20 per page with previous/next and "Showing x–y of n";
  - states: loading (skeleton row, `aria-busy`), empty ("No students yet" + Add student), empty with filters
    ("No matches" + Clear filters), error (message + Retry), 401 (sign-in link as `AccessUnavailable`),
    403 (the server's message);
  - detail side panel (F5): every field, has-login, assignment, created/archived by and when; Edit for a
    student with no login that is not archived;
  - Archive and Assign use the codebase's **inline confirmation** pattern (`AgentTeamPanel`,
    `AgentApprovalPanel`, `TierDowngradeConfirm`): the row shows "Archive <name>? Confirm / Cancel" in place;
    Cancel and completion return focus to the button that opened it; results are announced in the panel's
    single `role="status"` / `aria-live="polite"` region. No modal, so no focus trap is needed.
- **`AgentStudentForm`** (create/edit): labelled inputs for §4's fields; inline `422` messages; Save disabled
  while submitting; leave prompt on unsaved changes; on `409 possible_duplicate` lists the matches and "n more
  you can't view", with "Save anyway" (resends with `confirm_duplicate: true`) and "Go back".
- **`AgentTeamPanel`:** a "Staff" section — invite form (reuses the Master invite form and dialog), list with
  S-code, status, invite-pending and assigned-student count, and a deactivate confirmation stating "n
  students will become unassigned".
- **Responsive and accessible:** the table becomes cards below 640 px; no horizontal overflow at 320 px;
  keyboard-only operable, visible focus, every control labelled.

**Frontend review addendum (2026-09-30) — reuse first, existing design language kept:**

- **Reused, not rebuilt:** `lib/apiErrors.ts` (`detailMessage` for string/422-list `detail`, `isPage` to
  distrust a non-page 200, `NOT_COMPLETED` for network drops, `Page<T>`); `lib/focus.refocus` (focus back
  after a disabled-while-busy button); `AgentApprovalPanel`'s paging (20 per page, "Showing x–y of n",
  labelled Previous/Next, `page` in the URL); the `.table` + `data-label` stacked-card rule used by
  `.table.psy-records` in `globals.css` (a sibling class, same rule, no new visual language);
  `.record-details` for the detail panel's `dl`; `SchoolStudentFields`' field-group layout;
  `PsychometricResultsForm`'s leave prompt (`beforeunload` plus in-app link guard while dirty);
  `form`, `form-message`, `form-error`, `btn secondary small`, `muted` classes. `lib/agentStudents.ts` adds
  one helper, `duplicateDetail(detail)`, to read the structured `409`; everything else goes through
  `detailMessage`.
- **Visual hierarchy:** one `h2` "Students" per screen (the shell owns `h1`); toolbar above the list; the
  "Link a student with an account" form sits below under its own `h3` so the two flows are not confused;
  status and has-login are text badges, never colour alone.
- **Forms:** fields grouped as Personal, Contact, Academic, Preferences (as §5 Step 1) under `fieldset` +
  `legend`; only Full name required (marked in text); `type="email"`, `type="tel"`, `type="date"` with
  `max` = today, numeric year with `inputMode`; each error tied by `aria-describedby` with `aria-invalid`;
  after a failed submit focus moves to the first invalid field; a character counter on Notes.
- **Loading / perceived performance:** first load shows a skeleton row set with `aria-busy`; later loads
  (search, page, toggle) **keep the current rows visible** and dim them with `aria-busy`, so the list never
  flashes empty. Search is debounced (300 ms). Each list fetch uses an `AbortController`, and a response for
  an older query is discarded, so a slow earlier search can never overwrite a newer one. After a write, the
  row is updated from the write response in place (no full reload); the list is refetched only when the
  change moves the row out of the current filter (e.g. archive with "Show archived" off).
- **Empty and error states:** "No students yet" with an Add student button; with filters: "No students
  match" with Clear filters; list error: `detailMessage` text + Retry (keeps filters); 401: the existing
  `AccessUnavailable` sign-in link; 403: the server message (e.g. suspension). Detail panel has its own
  loading and "This student is no longer available" (404) states.
- **Keyboard and mobile:** Tab order toolbar → list → paging; row actions are real `<button>`s; the detail
  panel opens below the list on narrow screens and above-the-fold focus moves to its heading; Esc closes the
  detail panel and returns focus to the row's View button; touch targets ≥ 44 px on the card layout.
- **Double-submit:** Save is disabled while busy and re-enabled with `refocus`; the duplicate "Save anyway"
  resends the same payload plus `confirm_duplicate: true`.
- **Unchanged:** `AgentApplicationCreatePanel`, `AgentApprovalPanel`, `RegisterForm`.

## 7. Security (security-and-hardening review, 2026-09-30)

**Trust boundaries:** the new HTTP routes (JSON bodies and query strings from Masters and Staff); the Staff
invite (an email address typed by a Master); stored student text rendered back to other agency members.
**Assets:** personal data of students who have no account of their own (name, contact, date of birth — may
include minors), agency tenancy, Master-only authority.

| Area | Design |
|---|---|
| Authentication | Unchanged: `edusphere_access` httpOnly cookie (`secure` by setting, `SameSite=Lax`), `get_current_user` re-reads the user (`active`) and membership on every request. Staff use the existing welcome-link set-password flow (DEC-SCOPE-019 token and expiry); a Master never receives the raw token (stripped as for Master invites). No new auth flow, no new token type. |
| Authorization | Every route: role + division + `agent_denial_reason` (org pending/suspended, member deactivated, Staff default-deny). Master-only actions (archive, unarchive, assign, team) check `membership.role == 'master'` server-side; the UI hiding them is not the control. `super_admin` is not admitted to the new routes. |
| IDOR | UUID ids, but never relied on: every by-id load carries the agency scope (and, for Staff, the assignee) in the `WHERE` clause → `404`. `assign.member_id` must be an active Staff member of the **same** agency (`422` otherwise). Cross-agency and cross-Staff matrices tested per route. |
| Role escalation | Staff cannot invite, deactivate, assign, archive or reach any Master route. Server-owned fields (`agent_id`, `student_id`, `status`, `assigned_member_id`, `archived_*`) are absent from the schemas (mass assignment tested). A Staff invite always creates `role='staff'`; the role is never taken from the request. Downgrade refuses while Staff exist, so Staff can never be turned into Masters by a rollback. `ProfileUpdate` (`PATCH /auth/me`) cannot change `role` or membership (unchanged). |
| Input validation | Pydantic schemas at the boundary: length caps on every string, `clean_free_text` (control and bidi-override characters), email pattern, date and year ranges, `notes` ≤ 2000, `q` ≤ 100, paging bounds. Client validation mirrors it for usability only. |
| XSS | React escapes all rendered text; no `dangerouslySetInnerHTML`, no `innerHTML`; portal `PortalSection` renders values as text. A test renders a name containing `<script>` / `<img onerror>` and asserts it appears as text. |
| CSRF | Unchanged model: `SameSite=Lax` cookies are not sent on cross-site `POST`/`PATCH`, and bodies are JSON (a cross-site form cannot send `application/json` without a CORS preflight, which the API's CORS allowlist refuses). Body-less `POST …/archive`, `/unarchive` and team deactivate rely on `SameSite=Lax`, exactly as the existing AGN-001 approve/deactivate routes do. No change to CORS. |
| SQL injection | SQLAlchemy expressions only, bound parameters; search uses the existing `_like(..., escape="\\")` pattern with `%`, `_` and `\` escaped. No raw SQL except the migration's fixed DDL/DML. |
| Token/session handling | No change to cookies, JWT claims or lifetimes. Staff deactivation: `users.active = false` (next request `401`) and `revoke_welcome_tokens` (an unused invite link dies). Suspension applies on the next request (membership re-read). |
| Secret exposure | No new secret or config. Welcome token never returned to a Master; `development_welcome_token` stripped as today. |
| Sensitive logs | Logs and audit metadata carry ids, codes, field names and counts only — never names, emails, phones or dates of birth. The duplicate `409` returns personal data only for rows the caller can already see. |
| Rate limiting | Staff invites share the existing per-agency 10-per-24-hours limit (R1), with rejected attempts counted (QA-10). No new read/write rate limiting: no write endpoint in this codebase has one except invites and link search, and all new routes need an approved agency login. The duplicate check can only confirm an email/phone inside the caller's own agency (and to Staff only as a count), so it is not a platform-wide enumeration oracle. Stated residual. |
| Audit | Same-transaction audit for every write (`agent_student.*`, `agent_org.staff_*`); an audit failure rolls the write back (fail closed, `SEC-001`). The override of a duplicate warning is itself audited. |
| Data privacy | Collected fields are limited to §5 Step 1's list (stated purpose: counselling and applications). **Residual — `NEEDS_CONFIRMATION`:** a student with no login cannot file a data-subject request (the existing `data_subject_requests` flow is keyed to a requesting user), and AGN-004 has no hard delete (D5). Erasure of a login-less student's data therefore has no path yet; recorded in `PRD_OPEN_ITEMS.md` for a decision, not built here. |

Not added (stated residuals): no read-endpoint rate limiting (as elsewhere); no field-level edit history
(audit records field names only); no optimistic-concurrency check (last write wins); non-idempotent create
without email/phone (§5.4).

## 8. Acceptance criteria

| ID | Criterion |
|---|---|
| AGN-004-AC01 | A Master or Staff member creates a student with no login → `201`; one `agent_students` row with `student_id IS NULL` and `agent_id` = the creator; the `users` row count is unchanged. |
| AGN-004-AC02 | Created by Staff → assigned to that Staff member; created by a Master → unassigned. |
| AGN-004-AC03 | A Master and the assigned Staff member can view a student and edit one with no login; editing a linked student → `409`; editing an archived student → `409`; invalid input → `422` and nothing is written. |
| AGN-004-AC04 | A Master archives and unarchives. An archived student is absent from the default list, the roster `GET /overseas/agent/students` and the portal Students section/KPI; present with `include_archived=true`; still readable by id; its applications, commissions and audit history are unchanged. Staff archiving → `403`. |
| AGN-004-AC05 | Staff get `404` on read, edit and archive of a student assigned to someone else, an unassigned student, or any student of another agency; Staff lists contain only their assigned students. |
| AGN-004-AC06 | A Master of another agency gets `404` on every by-id route and never sees the rows in lists. |
| AGN-004-AC07 | Same email (any case) or phone (≥ 7 digits) within the agency — archived and linked students included — → `409 possible_duplicate`; resending with `confirm_duplicate: true` → `201` and an override audit row. A match in another agency never warns. Staff see matches they cannot view only as `hidden_matches`. |
| AGN-004-AC08 | A Master invites Staff → code `<PREFIX>-S00n`, never reused. Staff invites count toward the agency's 10-per-24-hours limit. Staff never count toward the 3-Master limit or the last-Master rule and never receive commission notifications. |
| AGN-004-AC09 | Staff get `403` on every existing agent route (dashboard, applications, documents, commissions, reports, team, link, lookups); their nav shows only Students; they land on `/overseas/agent/students`. |
| AGN-004-AC10 | Deactivating a Staff member disables their login, revokes their invite link and unassigns their students, in one transaction. |
| AGN-004-AC11 | Suspending the agency (or leaving it pending) denies its Staff on their next request. |
| AGN-004-AC12 | Every write writes an audit row in the same transaction with no personal data; if the audit write fails, nothing is written. |
| AGN-004-AC13 | Migration `0047`: existing rows unchanged; upgrade → downgrade → upgrade leaves pre-existing rows identical; downgrade refuses while Staff members exist. |
| AGN-004-AC14 | The Students and Team screens work at 320 px and keyboard-only, with loading, empty, error and 401 states. |

## 9. Tests (written first, per behaviour; real runs, never judged by reasoning)

**API** (`apps/api/tests/`):

- `test_agn_004_students.py` — AC01–AC07, AC12: create/edit/view/archive/unarchive/assign by role; `users`
  count unchanged; Staff `404` matrix (other Staff, unassigned, other agency); cross-agency matrix; duplicate
  warning by email case, by phone digits, archived, linked, other agency, override, `hidden_matches` for
  Staff; list filters, paging and `include_archived`; linked-student edit `409`; audit rows with no personal
  data; audit failure rolls back; two concurrent creates with the same email → exactly one `201` without
  override; mass assignment (server-owned fields in POST/PATCH bodies change nothing); `assign` to a member
  of another agency, a Master, or a deactivated Staff member → `422`; no-op PATCH / re-assign → `200`
  with no audit row; `LIKE` metacharacters in `q` match literally; response key allowlist (no `agent_id`,
  `student_id`, `phone_digits`); `super_admin` → `403`; log capture shows no personal data.
- `test_agn_004_staff.py` — AC08–AC11: invite, S-codes monotonic after deactivate, shared throttle, 3-Master
  limit and last-Master rule with Staff present, notifications to Masters only, deactivate unassigns,
  suspension denies Staff; Staff `403` on every existing agent endpoint (one parametrised list); roster and
  portal Students exclude archived.
- `test_agn_004_schemas.py` — field validation (§5.5).
- `test_agn_004_migration.py` — AC13 (upgrade → downgrade → upgrade on seeded rows; downgrade refusal).
- **Existing, run unedited:** `test_agt_002_referrals`, all six `test_agn_001_*` files,
  `test_agt_003_commission_accrual`, `test_agt_004_commission_payout`,
  `test_enh_031_lookups_students`, `test_sec_001_audit_trail`, `test_rpt_002_overseas_reporting`,
  `test_role_assignments`, `test_enh_027_migration`.

**Web** (`apps/web/tests/`, vitest): `lib/agentStudents.test.ts`; `navigation.agent.test.ts`
(`agentNavFor`, `dashboardPathFor`); `AgentStudentsPanel.test.tsx` (every state, filters, paging, Master vs
Staff actions, inline archive/assign confirmation with focus return, live region, rows kept visible while
refetching, a stale response discarded when an older search resolves last, markup in a name rendered as
text); `AgentStudentForm.test.tsx` (validation, changed-fields PATCH, focus to first invalid field,
double-submit blocked, duplicate confirm flow, leave prompt); `AgentTeamPanel.test.tsx` appended (Staff section). Existing
`Enh031ExistingPickers`, `AgentTeamPanel`, `RegisterForm`, `AccessUnavailable` tests run unedited.

**Playwright** `agn-004-agent-students.spec.ts`: a Master creates a student, gets the duplicate warning,
saves anyway, archives and finds them under "Show archived"; the Master invites Staff; Staff set a password,
sign in, land on Students, see only Students in the nav, create a student, and get "not found" for another
Staff member's student; keyboard-only run; 320 px run. Unique names per run. Existing specs
`agt-002-referrals`, `agn-001-multi-tenant`, `enh-031-searchable-pickers`, `agt-004-commission-payout` run
unedited.

## 10. Regression risks

| Risk | Mitigation |
|---|---|
| Staff counted as Masters (3-Master limit, last-Master rule, D12 notifications) | helpers filter by role (§5.2); AGN-001 tests unedited plus mixed Master/Staff tests |
| Staff reaching a Master route | fail-closed default at the shared gate; parametrised test over every agent endpoint |
| Rows with `student_id NULL` reaching code that joins `users` | old routes inner-join, so they drop such rows; tests show the application picker, link lookup, commissions and reports unchanged |
| Roster now hides archived links | intended (AC04), recorded in `API_CONTRACT.md`; `create_overseas_application` already refuses non-active links |
| Migration CHECK on `status` fails on unexpected values | pre-check in the migration; count queried before running |
| Organisation lock contention | same pattern as AGN-001 E12; writes are short |
| `UserOut` change breaks a consumer | additive optional key; web type optional |
| Shared E2E database | unique names per run |

## 11. Documentation (updated with the build)

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-040`, including the citation correction and the part of
`DEC-SCOPE-038` D13 it lifts); `ENHANCEMENT_BACKLOG.md` (AGN-004 entry and AC list; Appendix B note);
`DATA_MODEL.md` §6.8/§6.8a; `API_CONTRACT.md`; `RBAC_MATRIX.md` §2.8; `SECURITY_CONTROLS.md`;
`THREAT_MODEL.md` (the §7 boundaries and residuals); `PRD_OPEN_ITEMS.md` (erasure path for students with no
login, `NEEDS_CONFIRMATION`); `RTM.md`; `SCREEN_CATALOG.md` / `screen_catalog.json`; `ROLE_NAVIGATION.md`;
`CONFLICT_MATRIX.md` `C-10` note.

## 12. Completion gates (not claimed by implementation alone)

AGN-004 is COMPLETE only when: AC01–AC14 pass in real runs; the listed existing suites pass unedited; the
backend full suite shows no new failures beyond the recorded provider-credential baseline; migration
round-trip verified; web vitest, `tsc`, `eslint` and `npm run build` clean; Playwright AGN-004 spec and the
listed related specs pass on a rebuilt stack; responsive (320 px) and keyboard/accessibility checks done in a
real browser; docs in §11 updated; RTM row written with evidence.
