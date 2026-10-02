# bdm-001 — BDM and BDM Manager Roles, BDM Profile, Account Provisioning — Design

**Status:** design approved in-session on 2026-10-02, in three sections: (1) data and backend, (2) frontend, (3) tests and regression. No code has been written.

**Revision 2 (2026-10-02):** reviewed against the `api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening` skills. The findings are applied inline below and listed in §12. No approved decision changed.

**Branch:** `feature/bdm-001-bdm-profile`, cut from `main` (`268d132`, after AGN-014 #41).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-001.

**Source:** `functionalities/edusphere_markdown/BDM Functionalities.md` (`EVID-016`, `DERIVED_BLUEPRINT`), §1 and the Part 2 intro.

**Decision record:** **`DEC-SCOPE-052`**, written in this change. It contains:
- the BDM CRM answers from 2026-09-28 (D1–D32), which the backlog mis-cites as `DEC-SCOPE-037` (that number belongs to ENH-015);
- this item's answers from 2026-10-02 (B1–B9, §3).

**Gate:** `APPROVAL_GATES.md` GATE-09.

---

## 1. Scope

**In scope:**
- Two new roles: `bdm` and `bdm_manager`.
- A 1:1 BDM profile: type, Employee ID, designation, department, territory and reporting manager. Name, email, mobile and active status stay on `users`.
- Provisioning through the existing `POST /admin/users`, with the set-password link (`DEC-SCOPE-019`).
- Profile editing through `PATCH /admin/users/{id}`.
- Read routes: `GET /bdm/me`, `GET /bdm/manager/team`, `GET /admin/bdms`, `GET /admin/bdm-managers`.
- Landing shells: `/bdm/my-day` and `/bdm/manager/dashboard`.
- Pages: `/bdm/profile`, `/bdm/manager/team` and `/bdm/sign-in`.
- An admin BDM page.
- The scope helpers that later bdm items call.

**Out of scope, owned by later items:**

| Not in this item | Owner |
|---|---|
| My Day content | bdm-014 |
| Manager dashboard content | bdm-023 |
| Changing a BDM's type | bdm-025 |
| Reassignment on deactivation | bdm-025 |
| Approval routing when a manager is inactive | bdm-010 / bdm-025 |
| Organizations and everything after them | bdm-002 onward |

**Unchanged:**
- the `auth.login` division rule;
- `get_current_user`;
- token claims;
- the `users` columns;
- `AuditLog`;
- `School.edusphere_bdm`;
- the agent and school role code;
- the `GET /admin/users` response;
- set-password URLs.

## 2. Approaches considered

| | Approach | Verdict |
|---|---|---|
| **A** | Extend `POST/PATCH /admin/users` with a `bdm_profile` branch, written like the existing `role == "agent"` → `ensure_agent_org` branch, plus a new `bdm_profiles` table. | **Chosen (B5).** One provisioning path: the password ban, email validation, welcome token, audit row and delivery are all reused. |
| B | A separate `POST /admin/bdms`. | Rejected: it would duplicate provisioning or force a refactor of `create_user`, and give two ways to create an account. |
| C | Store the profile in the `users.profile` JSON. | Rejected: the database can't enforce a unique `employee_id` (so the 409 isn't race-safe), there is no foreign key to the manager, and the generic profile edit can overwrite it. |

**Structural note:** the backlog proposed an `app/api/bdm/` package, but the codebase has no route packages. Every feature is a flat `app/api/<feature>.py` plus `app/services/<feature>.py`, with Pydantic models in `schemas.py`, as in `agent_team.py` with `services/agent_orgs.py`. This design follows that convention: `api/bdm.py` and `services/bdm.py`.

## 3. Decisions

`EXPLICIT_APPROVAL`, owner, in-session, 2026-10-02. They are recorded in `DEC-SCOPE-052` and build on D3, D4, D10 (Q-01) and D26 (Q-17).

| # | Question | Answer |
|---|---|---|
| B1 | How does a `bdm_manager` (division `global`) sign in? | At `/admin/login`. After resetting a password, the user is sent to the portal named in the response (§5.6). The login rule is unchanged. |
| B2 | Landing pages for AC5 | **Minimal shells**: My Day shows a profile summary, and the manager dashboard shows the team count and a link to the team page. bdm-014 and bdm-023 fill them in. |
| B3 | Scope of this item | All of: `/bdm/me` + `/bdm/profile`, `/bdm/manager/team` + page, `/admin/bdms` (and the manager picker), and the scope helpers. |
| B4 | Decision record | Register under the next free number, **`DEC-SCOPE-052`**, and correct the backlog's references to 037. |
| B5 | Approach | **A** (§2). |
| B6 | Does a manager have a profile row? | **No.** `bdm_profiles` rows exist only for role `bdm`. |
| B7 | Can a BDM's type change? | **No, it's fixed in bdm-001.** A PATCH with a different `bdm_type` → 422. bdm-025 owns transfers. |
| B8 | Required profile fields | **Type, Employee ID and reporting manager.** Designation, department, territory and mobile are optional. |
| B9 | Signed-out visitor to `/bdm/*` | `/bdm/manager/*` → `/admin/login?next=…`. Any other `/bdm/*` → a public `/bdm/sign-in?next=…` page with two links: "College BDM" → `/it/login` and "Agent / School BDM" → `/overseas/login`. |

**Carried forward:**
- D3: division is derived from the type (college → `it`, agent/school → `overseas`).
- D4: a manager sees only the BDMs who report to them, and `super_admin` sees all.
- D10: `super_admin` creates both roles and any type, `it_admin` creates College BDMs, `overseas_admin` creates Agent and School BDMs, and only `super_admin` creates managers.
- D26: a manager's division is `global`, and managers own no appointments or trips.

## 4. Data model — migration `0058_bdm_profiles`

There is a single head after `0057_agent_applications`. I re-checked on `main` `268d132`: AGN-014 added no migration.

New table `bdm_profiles` (model `BdmProfile` with `TimestampMixin`):

| Column | Type | Constraint |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID → `users.id` | NOT NULL, **unique** (`uq_bdm_profiles_user`) |
| `bdm_type` | String(20) | NOT NULL, `ck_bdm_profiles_type`: `bdm_type IN ('agent','school','college')` |
| `employee_id` | String(40) | NOT NULL. Unique index **`uq_bdm_profiles_employee_id` on `lower(employee_id)`**, following the `uq_agent_universities_org_name_country` precedent. Stored trimmed, case kept. |
| `designation` / `department` / `territory` | String(120) | nullable |
| `reporting_manager_user_id` | UUID → `users.id` | NOT NULL, indexed (`ix_bdm_profiles_reporting_manager`) |
| `created_at` / `updated_at` | timestamptz | from `TimestampMixin` |

- **Existing data:** the migration only adds a table, so no existing row is read or written. Each operation is guarded by an inspector check, the same pattern 0054 and 0057 use, because 0001 builds a fresh database from the current models.
- **`downgrade()`** refuses while any `bdm_profiles` row exists. It would otherwise destroy the only record of each BDM's type and manager.
- **No manager CHECK in the database:** whether the manager is an active `bdm_manager` can't be expressed as a CHECK across tables. It is enforced by the application under a row lock (§5.4).

## 5. Backend

### 5.1 Roles — `core/rbac.py`

Add `"bdm": {"bdm:self"}` and `"bdm_manager": {"bdm:team"}`. These are coarse bundles; scope is enforced in the query layer (§5.3), as for the school roles. The admin roles page (`services/portal.py`) lists them automatically.

### 5.2 Schemas — `schemas.py`

- **`BdmProfileCreate`** (`extra="forbid"`):
  - `bdm_type: Literal["agent","school","college"]`
  - `employee_id: str`: trimmed, 1–40 characters, not whitespace-only, and no control characters (`\x00–\x1f`, `\x7f`)
  - `designation`, `department`, `territory: str | None`: max 120, `""` becomes `None`
  - `reporting_manager_user_id: UUID`
- **`BdmProfileUpdate`** (`extra="forbid"`): the same fields, all optional; omitted means unchanged.
  - `bdm_type` is accepted only so that a value equal to the current one is a harmless no-op; a different value → 422 (B7).
  - **Null rules:** `designation`, `department` or `territory` sent as `null` or `""` clears the field. `employee_id` or `reporting_manager_user_id` sent as `null` → 422, because both are required.
  - `user_id` is not a field, so a profile can never be moved to another user (`extra="forbid"` rejects it).
- **Response models** (new): `BdmProfileOut`, `BdmManagerRef` (`id`, `full_name`, `active`), `BdmMeOut`, `BdmTeamRow`, `BdmAdminRow`, `BdmManagerOption` (`id`, `full_name`). Lists use a `Page`-shaped dict, `{items, total, limit, offset}`, the AGN-008 list convention that the web's `lib/apiErrors.Page<T>` already types. The new read routes declare `response_model`, so no field reaches a client unless it is listed.
- **Errors:** a validation failure raises `HTTPException(422)` with a message naming the field, wrapped by the service. This matches the existing `_fit` and `_valid_email` style, since the `/admin/users` payload stays an untyped `dict` to preserve its contract.

### 5.3 Service — new `app/services/bdm.py`

Functions only. Nothing here commits; callers own the transaction.

- **`BDM_DIVISION`** = `{"college": "it", "agent": "overseas", "school": "overseas"}`.
- **`CREATOR_TYPES`** = `{"super_admin": {all}, "it_admin": {"college"}, "overseas_admin": {"agent","school"}}`.
- **`require_creator_may(actor, bdm_type)`**: 403 "Your role cannot manage {type} BDMs" (D10). A refusal is logged as a WARNING with `actor_id`, `route` and `bdm_type` only, never email, phone or Employee ID, following `_reject_supplied_password`.
- **`parse_profile_create(raw)` / `parse_profile_update(raw)`**: turn the nested dict into the §5.2 models; a `ValidationError` becomes a 422.
- **`locked_active_manager(db, manager_id)`**: `SELECT users … FOR UPDATE`. Returns 422 "Reporting manager must be an active BDM manager" when the user is missing, inactive, or has a role other than `bdm_manager` (AC4).
- **`flush_profile(db)`**: an `IntegrityError` on `uq_bdm_profiles_employee_id` becomes 409 "Employee ID already exists" (AC3), following `provisioning.flush_unique_email`. Like that helper, it rolls back the whole transaction (user, profile and token) before raising, so nothing is half-written.
- **`profile_out(profile, user, manager)`**: the one place the profile response is assembled.
- **Scope helpers** for later items:
  - `bdm_context(db, user)`: requires role `bdm` and a profile row; otherwise 403 "BDM profile not set up".
  - `require_manager(user)`: allows `bdm_manager` or `super_admin`; otherwise 403.
  - `team_filter(user)`: the SQL condition `BdmProfile.reporting_manager_user_id == user.id`, or none for `super_admin`.
  - `admin_type_filter(actor)`: the types an admin may see.

### 5.4 `POST /admin/users` — the new branch (`admin.py:create_user`)

Every role other than `bdm` and `bdm_manager` takes exactly the same code path as before. The steps in order:

1. `allowed_by_division` gains `"it"`/`"overseas"`: `bdm`, and `"global"`: `bdm_manager`.
2. **If `role == "bdm"`:**
   - 2a. `bdm_profile` is missing or not an object → 422 "BDM profile is required".
   - 2b. `parse_profile_create` → 422 on invalid fields.
   - 2c. `require_creator_may` → **403**.
   - 2d. Division: if `"division"` is absent from the payload, use `BDM_DIVISION[type]`. If present and different from it → **422** "Division must be {mapped} for a {type} BDM" (AC2). This runs **before** the existing cross-division 403, so a `super_admin` with a mismatched division gets the AC2 422. A non-super admin's type is already settled by 2c, so the cross-division 403 can't fire for them.
3. **If `role == "bdm_manager"`:** the actor is not `super_admin` → 403 "Only a Super Admin can create BDM managers". Division must be `global`, which the existing role-set check enforces.
4. The existing steps run unchanged: cross-division 403, password ban (422), role-set check, email validation and the 409 for a duplicate email, then building `User` and `_flush_unique_email`.
5. **If `role == "bdm"`:**
   - `locked_active_manager` → 422 (AC4).
   - Add a `BdmProfile` and run `flush_profile` → 409 (AC3).
6. The existing steps: `issue_welcome_token`, then the `AuditLog` row `user.create`. Its metadata gains `bdm_profile` (type, employee_id, designation, department, territory, reporting_manager_user_id) when present (AC7).
7. One `commit`. Then `deliver_welcome_link` runs **after** the commit, as today, so the email can never announce an account that was rolled back.
8. **Response:** the existing keys are unchanged. One key is added for **every** role, so the response shape is the same whatever the role: `"bdm_profile"` is `profile_out(...)` for a BDM and `null` for anyone else. Adding a field is backward-compatible.
9. **Retrying:** POST is not idempotent. A retry after a lost response gets 409 "Email already exists", the existing natural guard, and no second account or email is created. No `Idempotency-Key` header is added; the existing contract has none.

### 5.5 `PATCH /admin/users/{id}` — the new branch (`admin.py:update_user`)

1. The existing 404 for an unknown user and 403 for another division, unchanged.
2. **If the target user is a BDM (`role == "bdm"`):**
   - `require_creator_may(actor, profile.bdm_type)` → 403. This stops `it_admin` editing Agent BDMs, which the division check alone already blocks; it also covers future types.
3. **If `"bdm_profile"` is in the payload:**
   - The target isn't a BDM → 422 "Only a BDM has a BDM profile".
   - `parse_profile_update` → 422.
   - The profile row is read `FOR UPDATE`, so two admins editing the same BDM are serialized and each audit row's before/after is exact. The last write wins, and both are audited.
   - A `bdm_type` different from the current one → 422 "BDM type cannot be changed" (B7).
   - A new `reporting_manager_user_id` → `locked_active_manager` → 422.
   - Apply the changed fields, then `flush_profile` → 409.
4. The existing field loop (`full_name`, `phone`, `active`, …), the trainer cascade guard and welcome-link revocation are unchanged.
5. The audit row `user.update`: its metadata is the payload as before, plus `bdm_profile_before` and `bdm_profile_after` when the profile changed (AC7).
6. One commit. The response stays `{"ok": true}`, unchanged.

**Deactivating a manager** goes through the existing `active` path and is allowed. Their BDMs are reported with `manager_active: false` (§5.7). Reassigning them belongs to bdm-025.

### 5.6 `POST /auth/reset-password` — one extra response field

- The response is `{"ok": true}` today. It becomes `{"ok": true, "login_portal": "admin" | null}`. The key is **always present**, so the shape doesn't vary: it is `"admin"` when the user whose password was reset has role `bdm_manager`, and `null` for everyone else. The value is computed on the server from the user's role, never from the request, and appears only after a successful reset; the 400 for an invalid link is unchanged.
- This fixes two broken journeys, both of which today end at `/it/login` and get a 403 from `auth.login`'s division rule:
  - a manager following their welcome link (`/it/reset-password`, from `_set_password_url`);
  - a manager using forgot-password.
- Set-password URLs don't change, and super_admin's behavior doesn't change.

### 5.7 New router — `app/api/bdm.py`

Two routers, both registered in `main.py`'s router tuple:

| Route | Who | Returns / errors |
|---|---|---|
| `GET /bdm/me` | `bdm` | `{id, full_name, email, phone, active, division, bdm_profile: {bdm_type, employee_id, designation, department, territory, reporting_manager: {id, full_name, active}}}`. 403 for other roles, or a BDM with no profile. |
| `GET /bdm/manager/team` | `bdm_manager` (own team), `super_admin` (all) | `{items: [{id, full_name, email, phone, active, bdm_type, employee_id, designation, department, territory}], total, limit, offset}`. Includes inactive BDMs, with their status (AC6). 403 for other roles. |
| `GET /admin/bdms` | `super_admin`, `it_admin` (college), `overseas_admin` (agent, school) | Same page shape. Items as above, plus `reporting_manager: {id, full_name, active}` and `manager_active`. Optional filters `bdm_type` (`agent\|school\|college`; any other value → 422; a valid type the caller may not see → 403) and `active` (bool). |
| `GET /admin/bdm-managers` | the three admin roles | `{items: [{id, full_name}], total, limit, offset}`: **active** `bdm_manager` users only, for the picker. **No email**, because division admins only need a name to pick from (data minimization). |

- **Pagination:** every list takes `limit` (default 50, max 100) and `offset` (≥ 0). Rows are sorted by `full_name, id`, so pages are stable. `total` is computed from the same filters.
- **No N+1 queries:** profiles join to the user and the manager, with `aliased(User)` for the manager, in one query, plus one `count()`.
- **No request parameter selects another user:** `/bdm/me` and `/bdm/manager/team` take no user ID, so the scope always comes from the session (no IDOR). `/admin/bdms` filtering by type happens in SQL, so rows outside the caller's types are never loaded.
- **GETs change nothing:** all four routes are read-only.

### 5.8 Transactions, races and authorization

| Concern | Handling |
|---|---|
| A partial create | The user, profile, token and audit row are written in one transaction with one commit. Any 4xx raised before the commit leaves nothing behind (session rollback). The email goes out after the commit. |
| A duplicate Employee ID under concurrency | The unique index decides; the loser's transaction rolls back and it gets a 409. Two IDs that differ only in letter case collide by design. |
| A manager deactivated at the same moment a BDM is assigned to them | `locked_active_manager` uses `FOR UPDATE`, and the deactivation's `UPDATE users` takes the same row lock, so one waits for the other. Either the assignment sees the manager as inactive (422), or the deactivation commits after it and the BDM is flagged `manager_active: false`. |
| Assigning yourself a team | The reporting manager must be an active `bdm_manager`, and only `super_admin` creates managers. No route lets a BDM or manager write their own profile. |
| Admin across divisions | The existing division-lock 403 still applies, and `CREATOR_TYPES` narrows it further by type. |
| BDM without a profile | Can't be created (422). `bdm_context` returns 403 for a profile row that has gone missing. |

## 6. Frontend

### 6.1 Navigation and sign-in

- **`lib/navigation.ts`:**
  - `ROLE_DASHBOARD_PATH` gains `bdm: "/bdm/my-day"` and `bdm_manager: "/bdm/manager/dashboard"`. This is AC5, and it is enough on its own: `LoginForm`, `HeaderAuthActions`, `AccessUnavailable` and the password and profile pages already read this map.
  - New `BDM_NAV` (My Day, Profile) and `BDM_MANAGER_NAV` (Dashboard, Team).
  - A "BDMs" entry in `SUPER_ADMIN_NAV` (→ `/admin/bdms`), `PORTAL_NAV["it/admin"]` and `PORTAL_NAV["overseas/admin"]`.
- **`middleware.ts`:**
  - The matcher adds `"/bdm/:path*"`, and the protected regex adds `bdm`, except `/bdm/sign-in`.
  - Signed-out visitors: `/bdm/manager/*` → `/admin/login?next=…`; any other `/bdm/*` → `/bdm/sign-in?next=…`.
  - `next` keeps the query string, as it does today.
- **`/bdm/sign-in`** (new, public): two buttons that link to `/it/login?next=…` and `/overseas/login?next=…`. `next` is passed through as-is; `LoginForm`'s `safeNextPath` already refuses anything that isn't a same-site path.
- **`ResetPasswordForm`:** after success, `router.push(\`/${data.login_portal ?? division}/login\`)` (§5.6). Only the literal `"admin"` is honored; any other value falls back to `division`, so a response can never steer the redirect elsewhere.
- **`/admin/login` heading (B1):** the h2 "Super Admin Login" becomes "Administration sign-in", with the subtitle "For Super Admins and BDM Managers." This is a text-only change: the layout, the `LoginForm division="global"` and the demo box are untouched.
- **`WorkflowPanel`:** `ROLES_BY_DIVISION.global` gains `bdm_manager`; only `super_admin` is offered `global`. `bdm` is deliberately **not** added, because it can't be created without a profile.

### 6.2 BDM pages

All are server components that follow the `overseas/admin/school-transfers` pattern: `serverApi` → `accessUnavailable(e, "/bdm/sign-in")` on failure → role check → `accessDenied` → `PortalShell`.

| Page | Data | Content and states |
|---|---|---|
| `/bdm/my-day` | `GET /bdm/me` | Greeting, a profile summary card (type, territory, reporting manager), and the neutral note "Your appointments, travel and follow-ups will appear here." A 403 for a missing profile shows its message: "BDM profile not set up — contact your administrator". |
| `/bdm/profile` | `GET /bdm/me` | A read-only definition list of every §1 field |
| `/bdm/manager/dashboard` | `GET /bdm/manager/team` | Team counts (active and inactive) and a link to the team page. Empty: "No BDMs report to you yet." |
| `/bdm/manager/team` | `GET /bdm/manager/team` | Table: name, Employee ID, type, territory, mobile, status. Empty: as above. |

These pages are server-rendered, so there is no client-side loading state. The error state is the existing `AccessUnavailableCard`.

- **Hierarchy:** the existing `portal-title` block gives the eyebrow, an h2 with the page name, and a muted line of context. The profile is a `<dl>` in one `.card` (label/value pairs, so screen readers announce them as pairs). The team uses a `<table>` with a `<caption>` inside a labelled, focusable `.table-wrap` region. The heading order is never skipped.
- **Status is never shown by color alone:** the `.badge` contains the word ("Active" / "Inactive").
- **Mobile:** at 390px, `PortalShell` already collapses its navigation. The `.table-wrap` scrolls inside its own region, so the page itself never scrolls sideways. The `<dl>` stacks.
- **Perceived performance:** each page makes one server fetch (`/bdm/me` or `/bdm/manager/team?limit=50`) and has no client-side request chain. The manager dashboard reads only the first page; its counts come from `total` and the returned items. `/bdm/manager/team` pages with the same Previous/Next `nav` as `AgentStaffPanel`, kept in `?offset=` in the URL so a page can be linked.
- **`/bdm/sign-in`:** the `auth-page` layout; two full-width `.btn` links stacked on phones and side by side from 640px; an h1; one line explaining which to choose.

### 6.3 Admin page — `AdminBdmPanel`

**Component structure.** This follows the AGN-002 `AgentStaff*` split, keeping each file under about 160 lines:
- **`lib/bdm.ts`:** types, `BDM_TYPE_LABEL`, `creatableTypes(role)` (a copy of the server's `CREATOR_TYPES`, used only for display, since the server decides) and URL constants.
- **`AdminBdmPanel`:** the container. It loads the list, shows the loading/error/empty states and pages through results.
- **`AdminBdmCreateForm`:** the create form.
- **`AdminBdmRow`:** one row, with inline edit and activate/deactivate.

**Reused, nothing new invented:**
- `lib/apiErrors` (`sendJson`, `detailMessage`, `NOT_COMPLETED`, `Page<T>`);
- `lib/welcomeLink` (`welcomeLinkFeedback`, `toneClass`);
- `lib/useFocusAfterRender`;
- `lib/usersChanged.announceUsersChanged()`, so the generic user directory refreshes after a BDM is created;
- CSS: `.action-card`, `.form`, `.field`, `.table-wrap`, `.badge`, `.empty`, `.form-error`, `.form-message`, `.btn secondary small`;
- the pager markup from `AgentStaffPanel`.

**No new dependencies.** The manager picker is a native `<select>`. `SearchableSelect` is built for search-backed lookups, and the number of managers is small.

Mounted on the new static pages `/admin/bdms` (super_admin), `/it/admin/bdms` (it_admin, super_admin) and `/overseas/admin/bdms` (overseas_admin, super_admin). A static route takes precedence over `[module]`/`[section]`.

- **List** (`GET /admin/bdms`):
  - Loading: "Loading BDMs…" (`role="status"`).
  - Error: an alert with a **Retry** button.
  - Empty: "No BDMs yet."
  - Rows show name, email, Employee ID, type, territory, manager, and status. A **"No active manager"** badge appears when `manager_active` is false.
  - The table sits in a labelled, focusable `.table-wrap` region.
- **Create:**
  - Fields: full name, email, mobile; a type dropdown limited to `CREATOR_TYPES` for the viewer; Employee ID; designation, department, territory; and a manager `<select>` loaded from `/admin/bdm-managers`.
  - If no managers exist, the picker shows "No active BDM manager — a Super Admin must create one first" and submit is disabled.
  - Submit is disabled while the request is running, so it can't be sent twice.
  - On success, the message reuses `lib/welcomeLink.welcomeLinkFeedback`.
  - A 403, 409 or 422 shows the server's message inline, with `aria-live="polite"`, and focus moves to it.
- **Edit:**
  - Editable: name, mobile, Employee ID, designation, department, territory and manager. Type is displayed read-only (B7).
  - Activate/deactivate uses the existing `PATCH active`.
  - The list refreshes only after the server succeeds; it is never updated in advance of the reply.
- **List loading:** an `action-card` with `aria-busy="true"` and the text "Loading BDMs…", following the existing `AgentStaffPanel` pattern. Previous rows stay visible while the next page loads, so the list never flashes empty.
- **List empty:** an `.empty` block, `role="status"`, reading "No BDMs yet. Use Create BDM above to add the first one."
- **Error states:** a load failure shows `.form-error role="alert"` with a Retry `<button>`. A network failure on save shows `NOT_COMPLETED` ("…your entry is kept"), and the form keeps what was typed.
- **Forms:**
  - Every input has a `<label htmlFor>`, and required fields are marked in the label text, not by color.
  - Native constraints match the server: `required`, `maxLength` 160/40/120, `type="email" autoComplete="off"`, `type="tel" inputMode="tel"`.
  - A server error goes into a message region linked by `aria-describedby` and `aria-live="polite"`, and focus moves there with `useFocusAfterRender`.
  - The submit label changes to "Creating…" / "Saving…" and the button is disabled while busy.
  - When an admin may create only one type (`it_admin` → College), the type shows as fixed text with a hidden input rather than a one-option `<select>`.
- **Keyboard:** only native `<button>`, `<select>` and `<input>` are used, with no `div` click handlers.
  - Edit opens inline in the row and moves focus to its first field.
  - Esc or Cancel closes it, and focus returns to that row's Edit button. Save also returns focus there.
  - Deactivating asks for confirmation inline: a second button, "Confirm deactivate", with the reason text "Their reporting line and data stay; they can no longer sign in." No modal is needed.
- **Mobile:** the create form uses `.form` (one column at 390px) and the list scrolls inside `.table-wrap`. Touch targets are the existing `.btn small` buttons, which are at least 36px tall. The page itself never scrolls sideways.
- **XSS:** every value renders as React text. There is no `dangerouslySetInnerHTML`.

**Unchanged:** `AdminUserManagementPanel`, `LoginForm`, `PortalShell`. BDMs and managers still appear in the generic user directory under their role names.

## 7. Acceptance criteria

| ID | Criterion |
|---|---|
| BDM-001-AC01 | An authorized admin creates a `bdm` with a type, Employee ID and reporting manager. The account gets a set-password link; the stored password is unusable; a `password` field in the payload → 422. |
| BDM-001-AC02 | The BDM's division equals `BDM_DIVISION[type]`. A division that is sent and doesn't match → 422. When it is omitted, it is derived. |
| BDM-001-AC03 | A duplicate `employee_id` (letter case ignored) → 409, on both create and edit, and nothing is written. |
| BDM-001-AC04 | A reporting manager that is missing, inactive or not a `bdm_manager` → 422, on both create and edit. |
| BDM-001-AC05 | After login, a `bdm` lands on `/bdm/my-day` and a `bdm_manager` on `/bdm/manager/dashboard`. A manager's password reset ends at `/admin/login`. |
| BDM-001-AC06 | `GET /bdm/manager/team` returns exactly the BDMs whose `reporting_manager_user_id` is the caller (inactive ones included). `super_admin` gets all. A `bdm` gets 403. |
| BDM-001-AC07 | Every create or edit of a BDM (user fields or profile) writes one `AuditLog` row, with the profile values in its metadata. |
| BDM-001-AC08 | Creator rules (D10): `it_admin` creates College BDMs only, `overseas_admin` Agent and School BDMs only, only `super_admin` creates `bdm_manager`. Anything else → 403. |
| BDM-001-AC09 | `role=bdm` with no `bdm_profile` → 422. `bdm_profile` sent for a user who isn't a BDM → 422. Changing `bdm_type` → 422. |
| BDM-001-AC10 | `GET /bdm/me` returns the caller's profile. A role other than `bdm`, or a BDM with no profile → 403. |
| BDM-001-AC11 | `GET /admin/bdms` lists only the types the admin may manage and flags `manager_active: false`. `GET /admin/bdm-managers` lists active managers only. |
| BDM-001-AC12 | A signed-out visitor to `/bdm/manager/*` is redirected to `/admin/login?next=…`; any other `/bdm/*` goes to `/bdm/sign-in?next=…`. `/bdm/sign-in` is public. |
| BDM-001-AC13 | `AdminBdmPanel` shows loading, empty, error with Retry, and a "no managers" state that disables submit. Server errors appear inline. Type is read-only on edit. |
| BDM-001-AC14 | Every non-BDM create, edit, login or reset behaves exactly as before. The existing ADM, ENH-003, ENH-006, ENH-029 and AGN-001 tests pass unchanged. |
| BDM-001-AC15 | Response shapes don't vary. `POST /admin/users` always has `bdm_profile` (null for roles other than BDM), `reset-password` always has `login_portal` (null except for a manager), and every list is `{items, total, limit, offset}` with `limit` ≤ 100 and a stable order. |
| BDM-001-AC16 | Nothing can be escalated or reached outside the caller's scope: `PATCH` ignores `role`/`division`; a `bdm_profile` with an unknown key (for example `user_id`) → 422; a manager must be an active `bdm_manager`; `/bdm/*` reads only the caller's own data; the picker returns emails to admin roles only (amended by B10, §13); logs contain IDs and type only, never email, phone or Employee ID. |

## 8. Tests

Tests are written first, and every result comes from a real run.

**API — `apps/api/tests/test_bdm_001_profiles.py`:**
- **AC01:** a happy-path create by super_admin, it_admin and overseas_admin. Checks the profile row, `password_hash` is unusable, a welcome token exists, and the link is in the response; a sent `password` → 422.
- **AC02:** the division is derived for each of the 3 types; a mismatch from super_admin → 422.
- **AC03:**
  - duplicate and different-case IDs → 409, with the user-row count unchanged;
  - a duplicate on PATCH → 409;
  - two concurrent creates (`asyncio.gather`, separate sessions) → `{201, 409}`.
- **AC04:** the manager is missing, inactive, a `counselor`, or a `bdm` → 422, on create and on PATCH.
- **AC05 (API part):** the BDM logs in through its own division and the manager through `global`; `reset-password` returns `login_portal` only for a manager.
- **AC06:** M1 sees its 2 BDMs (one inactive) and not M2's; super_admin sees all; a `bdm` → 403.
- **AC07:** the audit row and its metadata for a create, a profile edit, a user-field edit, and deactivation.
- **AC08–AC11:** each negative path in their rows.
- **Validation:** over-length fields, whitespace-only Employee IDs and control characters → 422; `null` for `employee_id` or manager on PATCH → 422; `null` for designation clears it.
- **AC15:** key presence for a BDM and a counselor create; `login_portal` is `null` for a student reset; list paging (`limit=1`, `offset`), `limit=101` → 422, and the order is stable.
- **AC16:**
  - PATCH with `role: "super_admin"` or `division` → ignored, and the role is unchanged;
  - `bdm_profile.user_id` → 422;
  - an admin PATCHing a type it doesn't manage → 403;
  - the picker items have no `email`;
  - `caplog` shows no email, phone or Employee ID on a creator 403.
- **Concurrency:** two concurrent PATCHes of the same profile both write audit rows, and their before/after values chain correctly.

**Migration:** `upgrade` → `downgrade` (refused while a profile row exists; succeeds on an empty table) → `upgrade`. `alembic heads` shows exactly one head.

**Web (vitest):**
- `AdminBdmPanel.test.tsx`, `AdminBdmCreateForm.test.tsx`, `AdminBdmRow.test.tsx`:
  - AC13 states;
  - type options per admin role, shown as fixed text when there is only one;
  - an inline 409/422 with focus on the message;
  - the entry is kept after a network failure;
  - edit with read-only type;
  - Esc returns focus to Edit;
  - the deactivate confirmation step;
  - no update before the server replies;
  - `announceUsersChanged` is called after a create.
- `ResetPasswordForm.test.tsx`: follows `login_portal: "admin"`; falls back to the `division` prop for `null`, a missing key or any other value (for example `"//evil"`).
- `navigation.test.ts`: the two new dashboard paths.
- `middleware.test.ts`: AC12.
- Page tests for `/bdm/my-day` (the no-profile message) and `/bdm/manager/team` (empty state, role gate).

**Playwright — `bdm-001-bdm-profile.spec.ts`**, at desktop and 390px width:
1. A super_admin creates a manager, then a College BDM.
2. The BDM sets a password through the development token and lands on `/bdm/my-day`.
3. The manager sets a password, is sent to `/admin/login`, and lands on `/bdm/manager/dashboard`.
4. The BDM is in the team list.
5. A signed-out visit to `/bdm/my-day` → `/bdm/sign-in`.

**Regression set.** I run these for this feature; you run the full suite every 4–5 stories.
- **API:** `test_adm_001`, `test_adm_004`, `test_adm_012`, `test_adm_014`, `test_enh_003_first_time_provisioning`, `test_enh_006_change_password`, `test_enh_029_provision_refactor`, `test_sch_school_staff_provisioning`, `test_rbac`, `test_role_assignments`, and the AGN-001 admin-created agent test.
- **Web:** `HeaderAuthActions.test`, `LoginForm.next.test`, `AdminUserManagementPanel.test`, the `WorkflowPanel` tests.
- **e2e:** `auth-001-login`, `enh-003-first-time-provisioning`, `adm-001`, `adm-012`, `desktop-nav-dropdown`, `trn-001-mobile-nav`.
- **Build:** `ruff`, `tsc --noEmit`, `next build`.

## 9. Regression risks

| Risk | Why | Mitigation |
|---|---|---|
| `create_user` / `update_user` | Every admin provisioning flow and the AGN-001 Master creation use them. | The new code is gated on `role ∈ {bdm, bdm_manager}` or on `bdm_profile` being present; the full ADM, ENH and AGN-001 regression set is re-run (AC14). |
| `PERMISSIONS` gains two roles | `test_adm_012` asserts every role is on the roles page. | The page reads `PERMISSIONS` itself, so the test should pass unchanged; run it to confirm. |
| `ROLE_DASHBOARD_PATH` | Read in five places. | Entries are only added. |
| `middleware.ts` | Guards every portal. | The regex is only extended; there are unit tests for the old and new paths. |
| `reset-password` response | Shared by every role. | The extra key appears only for managers; `test_enh_003` and `test_enh_006` are re-run. |
| `WorkflowPanel` role options | The generic create form. | One more option, only under `global`. |
| A later merge of the migration | Parallel branches may also add `0058`. | Re-check `alembic heads` on `main` before merging, and re-chain if needed (the 0057 precedent). |

## 10. Documentation (updated in the same change)

- `PRODUCT_DECISION_REGISTER.md`: **`DEC-SCOPE-052`**, containing D1–D32 from 2026-09-28 and B1–B9.
- `BDM_CRM_BACKLOG.md`: replace "`DEC-SCOPE-037`" with "`DEC-SCOPE-052`" and mark bdm-001 status.
- `docs/architecture/RBAC_MATRIX.md`: the two roles and their scope rules.
- `docs/ux/ROLE_NAVIGATION.md`: the BDM and manager navigation, landing pages and `/bdm/sign-in`.
- Traceability: `EVID-016` §1 → `DEC-SCOPE-052` → bdm-001 → BDM-001-AC01…14 → tests → code.

## 11. Completion gates

bdm-001 is COMPLETE only when all of the following pass:
- AC01–AC14, each with test evidence from a real run;
- the security and RBAC/scope negatives;
- the migration up/down/up check;
- `ruff`, `tsc` and `next build`;
- the responsive check at 390px and desktop;
- the accessibility check (labels, focus, live regions);
- the regression set;
- the documentation in §10.

## 12. Revision 2 — skill reviews (2026-10-02)

Each finding is applied in the section named. Nothing here changes an approved decision (B1–B9) or adds anything beyond bdm-001.

### 12.1 API and interface design

| # | Finding | Applied |
|---|---|---|
| A1 | The lists had a custom `{rows, total}` shape with no paging | `{items, total, limit, offset}` with `limit` ≤ 100 and a stable order, the AGN-008 convention (§5.7) |
| A2 | Some response keys appeared only for certain roles | `bdm_profile` and `login_portal` are always present, null when they don't apply (§5.4, §5.6) |
| A3 | The new reads had no typed output | `response_model` on every new route (§5.2) |
| A4 | PATCH didn't say what `null` means | Clears the optional fields, 422 for the required ones (§5.2) |
| A5 | It wasn't stated whether retrying a create is safe | Not idempotent; a retry gets the existing 409 for a duplicate email, and no header is added (§5.4) |
| A6 | An invalid filter and a forbidden filter weren't told apart | Unknown `bdm_type` → 422; valid but forbidden → 403 (§5.7) |
| — | Kept as the existing code does it, for compatibility | The `/admin/users` payload stays an untyped `dict`; errors stay FastAPI `{"detail": "…"}`; fields stay snake_case; `PATCH /admin/users` still returns `{"ok": true}` |

### 12.2 Frontend UI engineering

| # | Finding | Applied |
|---|---|---|
| F1 | One large panel would grow past 200 lines | Split into a container, create form, row and `lib/bdm.ts`, following AGN-002 `AgentStaff*` (§6.3) |
| F2 | Possible reinvention | Reuse `sendJson`, `detailMessage`, `Page<T>`, `welcomeLink`, `useFocusAfterRender`, `announceUsersChanged`, the pager markup and the existing CSS classes (§6.3) |
| F3 | The form error and focus behavior wasn't specified | `aria-describedby` with a live region, focus moves to the error, the entry is kept on network failure, busy labels (§6.3) |
| F4 | Keyboard behavior for edit and deactivate | Inline edit, Esc to cancel, focus returns to Edit, an inline confirmation step (§6.3) |
| F5 | A select with only one option | Shown as fixed text when the admin has one creatable type (§6.3) |
| F6 | Status shown by color | Badges contain the words (§6.2, §6.3) |
| F7 | Mobile and perceived performance | One server fetch per page, the table scrolls inside its own region, the old page stays visible while the next loads (§6.2, §6.3) |
| F8 | B1's login heading had been left out of §6 | `/admin/login` text change (§6.1) |

### 12.3 Security and hardening — threat model

**Trust boundaries:** the admin's JSON body (`POST/PATCH /admin/users`), query parameters (`bdm_type`, `active`, `limit`, `offset`), the `next` parameter on `/bdm/sign-in`, the reset-password response read by the browser, and the session cookie.

**Assets:** BDM contact details (PII), the reporting line (which decides what a manager can see), the right to create accounts, and set-password tokens.

| Threat (STRIDE) | Check | Result |
|---|---|---|
| Authentication / spoofing | Cookies unchanged (`httponly`, `secure` from settings, `samesite=lax`); the token carries `sv`; `get_current_user` re-checks `active` on every request | A deactivated BDM or manager loses access on their next request. No change to authentication. |
| Session handling | Does deactivation need a `session_version` bump? | No: the per-request `active` check already refuses. A profile edit doesn't change what a session may do. |
| Authorization / elevation (role escalation) | Can a BDM or manager gain rights? | PATCH never writes `role` or `division` (the existing allowlist); only `super_admin` creates managers; the manager must be an active `bdm_manager`; no route lets a BDM or manager write their own profile; `extra="forbid"` blocks `user_id`. |
| IDOR | Can a caller name another user's data? | `/bdm/me` and `/bdm/manager/team` take no ID; `/admin/bdms` filters by type in SQL; `PATCH /admin/users/{id}` keeps the division check and adds `CREATOR_TYPES`. |
| Input validation | Every input field | Pydantic `extra="forbid"`, lengths, a type enum, a UUID manager ID, no control characters in the Employee ID, bounded `limit`/`offset`. The client-side limits are only a convenience. |
| SQL injection | Query construction | SQLAlchemy ORM with bound parameters only. The `lower(employee_id)` index is DDL, not user input. There is no raw SQL. |
| XSS | Rendering | React text only. `next` is URL-encoded and still checked by `safeNextPath`. `login_portal` is honored only for the literal `"admin"`. |
| CSRF | State-changing calls | Every write is a JSON `POST`/`PATCH` with SameSite=Lax cookies and CORS limited to `frontend_url`, the existing posture. No GET changes state. |
| Token handling | Set-password token | Unchanged (hashed at rest, 72 h, single use). `login_portal` appears only after a successful reset and says nothing about an invalid link. |
| Information disclosure | Responses, errors, logs | The picker returns id and name only; a 409 says "Employee ID already exists" and doesn't name the holder; logs contain IDs, route and type only; the development token stays development-only (existing). |
| Audit / repudiation | Who changed what | Each create and edit writes one `AuditLog` row with before/after profile values; a creator 403 is logged as a WARNING. |
| Rate limiting / denial of service | Account and email creation | Admin-only routes. The existing 429 throttle on re-sending links already covers repeated link mail. **No new limiter is added**: changing rate limits needs approval first, and nothing in bdm-001 asks for one. Bounded `limit` keeps list queries cheap. |
| Secrets | Code and config | No new secrets or settings. Before each commit, `git diff --cached` is checked for secrets. |
| Personal data | Purpose and retention | The fields are exactly the ones §1 requires, with no extras. Retention follows the user account; deletion is outside bdm-001 and unchanged. |

## 13. Addendum — browser QA fixes (2026-10-02)

The first exploratory browser QA pass raised six Medium issues; the owner approved two decision changes (`DEC-SCOPE-052` B10, B11). Each fix was written test-first and re-verified in the browser.

| QA | Problem | Fix |
|---|---|---|
| QA-01 | On desktop the BDM list sat in half a two-column grid; actions and the header were clipped | The list card spans the row (`.action-card.wide`, the existing convention) |
| QA-02 | The picker loaded only the first 100 managers, with no search | The picker is `SearchableSelect` in server mode; `GET /admin/bdm-managers` gains `q` (name or email, literal, case-insensitive, ≤ 200). `SearchableSelect` gains an optional `initial` pick (additive) for the row editor |
| QA-03 | Same-name managers were indistinguishable | **B10:** the picker returns and shows each manager's email (admin roles only) — supersedes §12.3's "no email" |
| QA-04 | A new BDM could not be found without paging; no search | `GET /admin/bdms` gains `q` (name, email or Employee ID, ANDed with the type scope); the list has a search box with Clear and a "No BDMs match …" state; after a create the list filters to the new Employee ID |
| QA-05 | Managers had no password recovery in their own portal | **B11:** public `/admin/forgot-password` and `/admin/reset-password`; "Forgot your password?" on `/admin/login`; a `bdm_manager`'s set-password link opens `/admin/reset-password` (other roles unchanged) |
| QA-06 | Keyboard focus fell to `<body>` after save, an error, or a status change | Focus returns to the row's own controls after success and moves to the message after an error (so Esc keeps working) |

The ten Low issues from the same pass are not addressed here.

## 14. Addendum — browser QA, Low issues (2026-10-02)

Each fix was written test-first and re-checked in the browser. No new owner decision was needed.

| QA | Fix |
|---|---|
| QA-07 | A sign-in at the wrong portal names the right one: `403 "Use the correct EduSphere portal for this account: sign in at /it/login"` (or `/overseas/login`, `/admin/login`). The password is checked first, so only a holder of valid credentials learns their own portal. |
| QA-08 | BDM profile validation errors read as sentences ("Employee ID is required", "Module: …", "Reporting manager: choose a manager from the list", "Unknown field: …"); no pydantic path or "Value error," prefix. |
| QA-09 | `/bdm` redirects to `/bdm/my-day`; `/bdm/manager` redirects to `/bdm/manager/dashboard`. |
| QA-10 | `/admin` shows the shared access card (own dashboard; sign-in at `/admin/login`) to any signed-in non-Super-Admin, instead of a Login button to `/it/login`. |
| QA-11 | Resolved by the QA-02 picker rewrite (no "Loading managers…" option exists); pinned by a test. |
| QA-12 | A Super Admin on `/it/admin/bdms` or `/overseas/admin/bdms` keeps the "Super Administrator" label and nav. |
| QA-13 | The admin BDM list keeps `offset` and `q` in the URL: refresh keeps the page, Back returns to the previous page. |
| QA-14 | A page past the last row (team page or admin list) says so and offers "Go to the first page". |
| QA-15 | Once the admin grid is one column (≤ 980px), the BDM list comes before the create form (CSS `order`, `.bdm-list`). |
| QA-16 | "1 BDM reports to you"; the team table caption is screen-reader only. Found while verifying: `.sr-only` is not a defined class here, so the caption and the list's "Actions" header now use the project's `.visually-hidden`. |
