# bdm-001 — BDM and BDM Manager Roles, BDM Profile, Account Provisioning — Design

**Status:** design approved in-session on 2026-10-02, in three sections: (1) data and backend, (2) frontend, (3) tests and regression. No code has been written.

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
  - `employee_id: str`: trimmed, 1–40 characters, not whitespace-only
  - `designation`, `department`, `territory: str | None`: max 120, `""` becomes `None`
  - `reporting_manager_user_id: UUID`
- **`BdmProfileUpdate`** (`extra="forbid"`): the same fields, all optional; omitted means unchanged. `bdm_type` is accepted only so that a value equal to the current one is a harmless no-op; a different value → 422 (B7).
- **Errors:** a validation failure raises `HTTPException(422)` with a message naming the field, wrapped by the service. This matches the existing `_fit` and `_valid_email` style, since the `/admin/users` payload stays an untyped `dict` to preserve its contract.

### 5.3 Service — new `app/services/bdm.py`

Functions only. Nothing here commits; callers own the transaction.

- **`BDM_DIVISION`** = `{"college": "it", "agent": "overseas", "school": "overseas"}`.
- **`CREATOR_TYPES`** = `{"super_admin": {all}, "it_admin": {"college"}, "overseas_admin": {"agent","school"}}`.
- **`require_creator_may(actor, bdm_type)`**: 403 "Your role cannot manage {type} BDMs" (D10).
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
8. **Response:** unchanged keys. When the user is a BDM it also includes `"bdm_profile": profile_out(...)`, which is backward-compatible.

### 5.5 `PATCH /admin/users/{id}` — the new branch (`admin.py:update_user`)

1. The existing 404 for an unknown user and 403 for another division, unchanged.
2. **If the target user is a BDM (`role == "bdm"`):**
   - `require_creator_may(actor, profile.bdm_type)` → 403. This stops `it_admin` editing Agent BDMs, which the division check alone already blocks; it also covers future types.
3. **If `"bdm_profile"` is in the payload:**
   - The target isn't a BDM → 422 "Only a BDM has a BDM profile".
   - `parse_profile_update` → 422.
   - A `bdm_type` different from the current one → 422 "BDM type cannot be changed" (B7).
   - A new `reporting_manager_user_id` → `locked_active_manager` → 422.
   - Apply the changed fields, then `flush_profile` → 409.
4. The existing field loop (`full_name`, `phone`, `active`, …), the trainer cascade guard and welcome-link revocation are unchanged.
5. The audit row `user.update`: its metadata is the payload as before, plus `bdm_profile_before` and `bdm_profile_after` when the profile changed (AC7).
6. One commit. The response stays `{"ok": true}`, unchanged.

**Deactivating a manager** goes through the existing `active` path and is allowed. Their BDMs are reported with `manager_active: false` (§5.7). Reassigning them belongs to bdm-025.

### 5.6 `POST /auth/reset-password` — one extra response field

- The response is `{"ok": true}` today. It becomes `{"ok": true, "login_portal": "admin"}` **only** when the user whose password was reset has role `bdm_manager`; for everyone else it stays exactly `{"ok": true}`.
- This fixes two broken journeys, both of which today end at `/it/login` and get a 403 from `auth.login`'s division rule:
  - a manager following their welcome link (`/it/reset-password`, from `_set_password_url`);
  - a manager using forgot-password.
- Set-password URLs don't change, and super_admin's behavior doesn't change.

### 5.7 New router — `app/api/bdm.py`

Two routers, both registered in `main.py`'s router tuple:

| Route | Who | Returns / errors |
|---|---|---|
| `GET /bdm/me` | `bdm` | `{id, full_name, email, phone, active, division, bdm_profile: {bdm_type, employee_id, designation, department, territory, reporting_manager: {id, full_name, active}}}`. 403 for other roles, or a BDM with no profile. |
| `GET /bdm/manager/team` | `bdm_manager` (own team), `super_admin` (all) | `{rows: [{id, full_name, email, phone, active, bdm_type, employee_id, designation, department, territory}], total}`, sorted by name. Includes inactive BDMs, with their status (AC6). 403 for other roles. |
| `GET /admin/bdms` | `super_admin`, `it_admin` (college), `overseas_admin` (agent, school) | Rows as above, plus `reporting_manager: {id, full_name, active}` and `manager_active`. Optional filters `bdm_type` and `active`; a `bdm_type` outside what the caller may see → 403. |
| `GET /admin/bdm-managers` | the three admin roles | `{rows: [{id, full_name, email}]}` for **active** `bdm_manager` users only (the picker). |

- **No list caps:** the BDM count is bounded by the organization's headcount. A cap can be added later in the same style as `USER_LIST_CAP` if it's ever needed.
- **No N+1 queries:** profiles join to the user and the manager, with `aliased(User)` for the manager, in one query.

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
- **`ResetPasswordForm`:** after success, `router.push(\`/${data.login_portal ?? division}/login\`)` (§5.6).
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

### 6.3 Admin page — `AdminBdmPanel`

A new client component, mounted on the new static pages `/admin/bdms` (super_admin), `/it/admin/bdms` (it_admin, super_admin) and `/overseas/admin/bdms` (overseas_admin, super_admin). A static route takes precedence over `[module]`/`[section]`.

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
- **Responsive and accessible:** existing `.form`, `.field` and `.table-wrap` styles, a label on every input, and no new dependencies.

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
- **Validation:** over-length fields and whitespace-only Employee IDs → 422.

**Migration:** `upgrade` → `downgrade` (refused while a profile row exists; succeeds on an empty table) → `upgrade`. `alembic heads` shows exactly one head.

**Web (vitest):**
- `AdminBdmPanel.test.tsx`: AC13 states, type options per admin role, an inline 409/422, edit with read-only type, no update before the server replies.
- `ResetPasswordForm.test.tsx`: follows `login_portal`, otherwise uses the `division` prop.
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
