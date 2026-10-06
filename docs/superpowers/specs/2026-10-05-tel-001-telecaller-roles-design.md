# tel-001 — Telecaller and Telecaller Manager Roles, Profile, Provisioning, Sign-in, Shell — Design

**Status:** design approved in-session on 2026-10-05, in three sections: (1) data and backend, (2) frontend, (3) tests, regression
and docs. No code has been written.

**Branch:** `feature/tel-001`, cut from `origin/main` @ `ce1f07c2` (after #67).

**Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` §4 tel-001.

**Source:** `functionalities/edusphere_markdown/Telecaller Functionalities.md` (`EVID-019`, `DERIVED_BLUEPRINT`), §22 ("Telecaller should
not have access to everything") and the "Management" references in §15, §16, §17 and §21. Under the owner's account-lifecycle
convention, creating a user implies the full lifecycle (profile, profile update, welcome set-password link, forgot and change password).

**Decision record:** **`DEC-SCOPE-073`**, written in this change. It holds:
- the Telecaller CRM answers T1–T29 of 2026-10-05 (backlog §3.1), registered here as the backlog requires;
- this item's answers TL1–TL7 (§3).

`DEC-SCOPE-072` (bdm-017) is the highest number on `main` @ `ce1f07c2`; no open branch claims 073. Re-check `origin/main` before the
first commit of code and again before merge, and renumber if another item lands first.

**Gate:** `APPROVAL_GATES.md` GATE-09.

**Template:** bdm-001 (`docs/superpowers/specs/2026-10-02-bdm-001-bdm-profile-design.md`, `DEC-SCOPE-055`). Where this spec says "as
bdm-001", the bdm-001 spec's section, including its revision-2 and browser-QA addenda, applies with `bdm` → `telecaller`.

---

## 1. Scope

**In scope:**
- Two new roles: `telecaller` and `telecaller_manager`.
- A 1:1 telecaller profile: team, Employee ID and reporting manager. Name, email, mobile and active status stay on `users`.
- Provisioning through the existing `POST /admin/users`, with the set-password link (`DEC-SCOPE-019`).
- Profile editing by admins through `PATCH /admin/users/{id}`, and by the telecaller (phone only) through `PATCH /telecaller/profile`.
- Read routes: `GET /telecaller/me`, `GET /telecaller/manager/team`, `GET /admin/telecallers`, `GET /admin/telecaller-managers`.
- Landing shells: `/telecaller/dashboard` and `/telecaller/manager/team`.
- Pages: `/telecaller/profile`, `/telecaller/sign-in`, and the admin Telecallers page at three mount points.
- The scope helpers that later tel items call.
- Fixes to the two bdm-001 hard-codes that would otherwise send a telecaller manager to the wrong portal after a password reset.

**Out of scope, owned by later items:**

| Not in this item | Owner |
|---|---|
| Dashboard content (tiles, daily activity) | tel-021 |
| Manager performance and reports | tel-023, tel-024 |
| Products, campaigns | tel-002 |
| Leads and everything that works on them | tel-003 onward |
| Targets | tel-022 |
| Changing a telecaller's team | tel-025 |
| Reassignment on deactivation | tel-025 |
| IT counselors | tel-017 (runs after this item; shares `rbac.py`, `ROLES_BY_DIVISION`, `create_user`, `middleware.ts`) |
| The §22 permission sweep | tel-026 |

**Unchanged:**
- the `auth.login` division rule (it already gives AC3's wrong-portal 403);
- `get_current_user`, token claims, the `users` columns, `AuditLog`;
- the `UserRoleAssignment` model and the unused `require_*` dependencies (inline-RBAC convention, 2026-09-28);
- everything BDM except the two shared hard-codes in §5.6;
- the `GET /admin/users` response;
- `enquiries`, `/admin/leads` and the lead admin panel.

## 2. Approaches considered

| | Approach | Verdict |
|---|---|---|
| **A** | Extend `POST/PATCH /admin/users` with a `telecaller_profile` branch, written like bdm-001's `bdm_profile` branch, plus a new `telecaller_profiles` table and read-only admin routes. | **Chosen (TL4).** One provisioning path: the password ban, email validation, welcome token, audit row and delivery are all reused. |
| B | Separate `POST/PATCH /admin/telecallers`, as the backlog's API line literally reads. | Rejected: it either duplicates provisioning or forces a refactor of `create_user`, and gives two ways to create an account whose 403/422 rules must be kept identical. |
| C | Store the profile in `users.profile` JSON. | Rejected: no database-enforced unique Employee ID (the 409 isn't race-safe), no foreign key to the manager, and the generic profile edit could overwrite it. |

The backlog's "`GET/POST/PATCH /admin/telecallers`" therefore becomes "`GET /admin/telecallers`; create and edit through `/admin/users`".
`DEC-SCOPE-073` records this, and the backlog's tel-001 API line is updated in the same change.

**Structure:** flat `app/api/telecaller.py` plus `app/services/telecaller.py`, with Pydantic models in `schemas.py`, as bdm-001.

## 3. Decisions

`EXPLICIT_APPROVAL`, owner, in-session, 2026-10-05. Recorded in `DEC-SCOPE-073`. They build on T2, T21, T22 and T23.

| # | Question | Answer |
|---|---|---|
| TL1 | Signed-out visitor to `/telecaller/*` (AC5) | `/telecaller/manager/*` → `/admin/login?next=…`. Any other `/telecaller/*` → a public `/telecaller/sign-in?next=…` chooser with "IT team" → `/it/login?next=…` and "Overseas team" → `/overseas/login?next=…`. |
| TL2 | Where active status lives | **`users.active` only.** `telecaller_profiles` has no `active` column. (Pausing a telecaller from distribution, if ever needed, is Q-07 in tel-007.) |
| TL3 | What a telecaller may edit about themselves | **Phone only**, through `PATCH /telecaller/profile`. Employee ID, team and reporting manager are admin-only. |
| TL4 | Approach | **A** (§2). |
| TL5 | Does a manager have a profile row? | **No**, as bdm-001 B6. `telecaller_profiles` rows exist only for role `telecaller`. |
| TL6 | Required profile fields | **Team, Employee ID and reporting manager.** No optional profile fields (the backlog says "required fields only"). Mobile is optional on `users`. |
| TL7 | Can the team change in tel-001? | **No.** A PATCH with a different `team` → 422 "Team cannot be changed here". tel-025 owns team moves (T22: open leads must be reassigned first). |

**Carried forward:**
- T2: roles `telecaller` and `telecaller_manager`; `super_admin` sees all.
- T21: `super_admin` creates both roles; division admins create telecallers for their own team; set-password welcome email; a telecaller
  signs in at its division portal and lands on `/telecaller/dashboard`; the manager is division `global` and signs in at `/admin/login`.
- T22: one team each (`it` or `overseas`); division follows the team.
- T23: a manager sees their direct reports (the unassigned-queue part arrives with tel-007); `super_admin` sees all.

## 4. Data model — migration `0075_telecaller_profiles`

It follows `0074_enquiry_bdm_attribution` (one head).

New table `telecaller_profiles` (model `TelecallerProfile` with `TimestampMixin`):

| Column | Type | Constraint |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID → `users.id` | NOT NULL, **unique** (`uq_telecaller_profiles_user`) |
| `team` | String(20) | NOT NULL, `ck_telecaller_profiles_team`: `team IN ('it','overseas')` |
| `employee_id` | String(40) | NOT NULL. Unique index **`uq_telecaller_profiles_employee_id` on `lower(employee_id)`**. Stored trimmed, case kept. |
| `reporting_manager_user_id` | UUID → `users.id` | NOT NULL, indexed (`ix_telecaller_profiles_reporting_manager`) |
| `created_at` / `updated_at` | timestamptz | from `TimestampMixin` |

- **Separate from `bdm_profiles`:** Employee IDs are unique within each table, not across them. A person can't hold both roles (one
  `users.role`), so no cross-table rule is needed.
- **Existing data:** the migration only adds a table. Each operation is guarded by an inspector check (the 0061 pattern), because 0001
  builds a fresh database from the current models.
- **`downgrade()`** refuses while any row exists, as 0061.
- **Not in the database:** "the manager is an active `telecaller_manager`" and "`team` = `users.division`" span tables, so the
  application enforces them (§5.3, §5.4).

## 5. Backend

### 5.1 Roles — `core/rbac.py`

Add `"telecaller": {"telecaller:self"}` and `"telecaller_manager": {"telecaller:team"}`. Coarse bundles; scope is enforced in the query
layer (§5.3). The ADM-012 roles page (`services/portal.py`) lists them automatically.

### 5.2 Schemas — `schemas.py`

- **`TelecallerProfileCreate`** (`extra="forbid"`):
  - `team: Literal["it","overseas"]`
  - `employee_id: str`: trimmed, 1–40 characters, not whitespace-only, no control characters (bdm-001's rule)
  - `reporting_manager_user_id: UUID`
- **`TelecallerProfileUpdate`** (`extra="forbid"`): the same fields, all optional; omitted means unchanged.
  - `team` is accepted only so an equal value is a harmless no-op; a different value → 422 (TL7).
  - `employee_id` or `reporting_manager_user_id` sent as `null` → 422 (both required).
  - `user_id` is not a field, so a profile can never move to another user.
- **`TelecallerSelfUpdate`** (`extra="forbid"`): `phone: str | None`. Trimmed; `""` or `null` clears it; max 40; only digits, spaces and
  `+ - ( )` (bdm-001's `_BDM_PHONE` rule, shared, not copied); no control characters. Any other key → 422 "Unknown field: …" (TL3).
- **Response models:** `TelecallerProfileOut` (`team`, `employee_id`, `reporting_manager: {id, full_name, active}`), `TelecallerMeOut`,
  `TelecallerTeamRow`, `TelecallerAdminRow` (`TeamRow` + `reporting_manager` + `manager_active`), `TelecallerManagerOption`
  (`id`, `full_name`, `email` — email so same-name managers can be told apart, as bdm-001 QA-03). Lists are `{items, total, limit, offset}`.
  Read routes declare `response_model`.
- **Field labels** (`TELECALLER_FIELD_LABELS`): "Team", "Employee ID", "Reporting manager", "Phone", for readable 422s.

### 5.3 Service — new `app/services/telecaller.py`

Functions only; nothing commits. Logs carry ids, route and team, never email, phone or Employee ID.

- **`TEAMS`** = `("it", "overseas")`.
- **`CREATOR_TEAMS`** = `{"super_admin": {"it","overseas"}, "it_admin": {"it"}, "overseas_admin": {"overseas"}}`.
- **`require_creator_may(actor, team, route)`**: 403 "Your role cannot manage {IT|Overseas} telecallers"; WARNING log with `actor_id`,
  `route`, `team`.
- **`parse_profile_create(raw)` / `parse_profile_update(raw)` / `parse_self_update(raw)`**: nested dict → §5.2 model; the first
  `ValidationError` becomes a readable 422 naming the field (bdm-001's `_readable`).
- **`locked_active_manager(db, manager_id)`**: `SELECT users … FOR SHARE`. 422 "Reporting manager must be an active telecaller manager"
  when the user is missing, inactive, or not a `telecaller_manager`.
- **`flush_profile(db)`**: an `IntegrityError` on `uq_telecaller_profiles_employee_id` → rollback and 409 "Employee ID already exists".
- **`profile_snapshot(profile)`** (audit form), **`profile_out(profile, manager)`** (response form).
- **`apply_profile_update(db, profile, raw)`** → `(before, after)` snapshots; TL7 team rule; manager re-checked only when it changes.
- **Scope helpers for later items:**
  - `telecaller_context(db, user)`: role `telecaller` and a profile row, else 403 ("Telecaller role required" /
    "Telecaller profile not set up — contact your administrator").
  - `require_manager(user)`: `telecaller_manager` or `super_admin`, else 403 "Telecaller manager role required".
  - `team_filter(user)`: `[TelecallerProfile.reporting_manager_user_id == user.id]`, or `[]` for `super_admin` (T23).
  - `admin_team_filter(actor, team)`: the teams an admin may see; a named team outside them → 403.

### 5.4 `POST /admin/users` — the new branch (`admin.py:create_user`)

Every role other than `telecaller` and `telecaller_manager` takes exactly the same path as before. The telecaller block sits next to
the BDM block, **before** the cross-division gate, for the same reason (a super_admin's mismatch is a 422, a division admin's wrong team
a 403).

1. `allowed_by_division` gains `"it"`/`"overseas"`: `telecaller`, and `"global"`: `telecaller_manager`.
2. **If `role == "telecaller"`:**
   - 2a. `telecaller_profile` missing or not an object → 422 "Telecaller profile is required".
   - 2b. `parse_profile_create` → 422.
   - 2c. `require_creator_may(user, team)` → **403** (AC2: `it_admin` + `team: "overseas"`).
   - 2d. Division: absent from the payload → `team`. Present and different → **422** "Division must match the telecaller's team".
3. **Else if `"telecaller_profile"` in the payload** → 422 "Only a telecaller has a telecaller profile".
4. **Else if `role == "telecaller_manager"`** and the actor is not `super_admin` → **403** "Only a Super Admin can create telecaller
   managers" (AC2). Division must be `global` (the role-set check enforces it).
5. The existing steps, unchanged: cross-division 403, password ban (422), role-set check, email validation, duplicate email 409, build
   `User`, `_flush_unique_email`.
6. **If telecaller:** `locked_active_manager` → 422; add `TelecallerProfile`; `flush_profile` → 409.
7. The existing steps: `issue_welcome_token`, audit `user.create`; metadata gains `telecaller_profile` (`profile_snapshot`) when present.
8. One commit; `deliver_welcome_link` after the commit.
9. **Response:** existing keys unchanged; adds `"telecaller_profile"` for every role (`profile_out` for a telecaller, `null` otherwise),
   alongside the existing `"bdm_profile"`. Backward-compatible.

The BDM and telecaller branches are mutually exclusive by role; a payload carrying both `bdm_profile` and `telecaller_profile` is refused
by whichever stray-profile check applies to its role.

### 5.5 `PATCH /admin/users/{id}` — the new branch (`admin.py:update_user`)

1. The existing 404 and cross-division 403, unchanged.
2. **If the target's role is `telecaller`:** lock its profile `FOR UPDATE`; `require_creator_may(actor, profile.team)` → 403.
3. **If `"telecaller_profile"` in the payload:** target isn't a telecaller → 422 "Only a telecaller has a telecaller profile"; else
   `apply_profile_update` (422 for team change / invalid fields / bad manager, 409 for duplicate Employee ID).
4. The existing field loop, trainer cascade guard and welcome-link revocation, unchanged.
5. Audit `user.update` gains `telecaller_profile_before` / `telecaller_profile_after` when the profile changed.
6. One commit; response `{"ok": true}`.

**Deactivating a manager** uses the existing `active` path; their telecallers show `manager_active: false`. Reassignment is tel-025.

### 5.6 Shared hard-codes from bdm-001

Both become a check against one constant, `ADMIN_PORTAL_ROLES = {"bdm_manager", "telecaller_manager"}` (in `services/provisioning.py`,
imported by `auth.py`):
- `provisioning._set_password_url`: a telecaller manager's welcome/reset link opens `/admin/reset-password`. Telecallers keep their
  division's page (`/it/…` or `/overseas/…`).
- `auth.reset_password` response: `"login_portal": "admin"` for both manager roles, `null` for everyone else. The shape is unchanged.

Forgot-password needs no change: managers use `/admin/forgot-password` (public, bdm-001 QA-05), telecallers their division's page.

### 5.7 New router — `app/api/telecaller.py`

Two routers (`router` prefix `/telecaller`, `admin_router` prefix `/admin`), registered in `main.py`'s router tuple.

| Route | Who | Returns / errors |
|---|---|---|
| `GET /telecaller/me` | `telecaller` | `{id, full_name, email, phone, active, division, telecaller_profile: {team, employee_id, reporting_manager: {id, full_name, active}}}`. 403 otherwise. |
| `PATCH /telecaller/profile` | `telecaller` | Body `TelecallerSelfUpdate`. Updates `users.phone`; audit `telecaller.profile_update` with `{"fields": ["phone"]}` (no values). Returns the `GET /telecaller/me` shape. 403 for other roles; 422 for other fields or a bad phone. |
| `GET /telecaller/manager/team` | `telecaller_manager` (direct reports), `super_admin` (all) | `{items: [{id, full_name, email, phone, active, team, employee_id}], total, limit, offset}`, inactive telecallers included. 403 otherwise (including a telecaller — backlog negative scenario). |
| `GET /admin/telecallers` | `super_admin`, `it_admin` (it), `overseas_admin` (overseas) | Same page shape; items add `reporting_manager` and `manager_active`. Filters: `team` (`it\|overseas`; other → 422; not the caller's → 403), `active` (bool), `q` (name/email/Employee ID). |
| `GET /admin/telecaller-managers` | the three admin roles | `{items: [{id, full_name, email}], total, limit, offset}`: **active** `telecaller_manager` users only; `q` searches name/email (server-search picker, bdm-001 QA-02). |

- **Pagination:** `limit` (default 50, max 100), `offset` (≥ 0), sorted by `full_name, id`; `total` from the same filters.
- **No N+1:** one join of profile → user → `aliased(User)` manager, plus one `count()`.
- **No IDOR:** `/telecaller/*` routes take no user id; scope always comes from the session. Admin team filtering happens in SQL.
- **GETs are read-only.**

### 5.8 Transactions, races and authorization

As bdm-001 §5.8, with these specifics:

| Concern | Handling |
|---|---|
| Partial create | User, profile, token and audit row in one transaction; the email after commit. |
| Duplicate Employee ID under concurrency | The unique index decides; the loser rolls back with 409. |
| Manager deactivated while being assigned | `FOR SHARE` on the manager row vs the deactivation's `UPDATE`: either 422, or the telecaller is flagged `manager_active: false`. |
| Privilege escalation | Only `super_admin` creates `telecaller_manager`; a division admin can't create a manager, an other-team telecaller, or any `global` account (existing cross-division 403). No route lets a telecaller or manager write their own team, Employee ID or manager. `PATCH /telecaller/profile` forbids every key but `phone`. |
| Admin-known password | Refused by the existing `_reject_supplied_password` (422); accounts start with an unusable hash. |
| Telecaller without a profile | Can't be created (422); `telecaller_context` → 403 if the row goes missing. |

## 6. Frontend

### 6.1 Navigation and sign-in

- **`lib/navigation.ts`:**
  - `ROLE_DASHBOARD_PATH` gains `telecaller: "/telecaller/dashboard"` and `telecaller_manager: "/telecaller/manager/team"` (AC3 landing;
    `LoginForm`, `HeaderAuthActions` and `AccessUnavailable` already read this map).
  - New `TELECALLER_NAV` (Dashboard, Profile) and `TELECALLER_MANAGER_NAV` (Team). Later items add entries.
  - `TELECALLER_SIGN_IN = "/telecaller/sign-in"`.
  - A "Telecallers" entry in `SUPER_ADMIN_NAV` (→ `/admin/telecallers`), `PORTAL_NAV["it/admin"]` (→ `/it/admin/telecallers`) and
    `PORTAL_NAV["overseas/admin"]` (→ `/overseas/admin/telecallers`), written out after "BDMs".
- **`middleware.ts`:**
  - `PUBLIC_PATHS` gains `/telecaller/sign-in`; the protected regex gains `telecaller`; the matcher gains `"/telecaller/:path*"`.
  - Signed out: `/telecaller/manager` and `/telecaller/manager/*` → `/admin/login?next=…`; any other `/telecaller/*` →
    `/telecaller/sign-in?next=…` (AC5, TL1). `next` keeps the query string. `/telecallerx` is not matched.
- **`/telecaller/sign-in`** (new, public, copies `/bdm/sign-in`): h1, one explanatory line, two `.btn` links "IT team" and "Overseas
  team" carrying `next`, and "Telecaller Managers sign in at Administration" linking to `/admin/login`, carrying `next` only when
  it starts with `/telecaller/manager` (final-review fix, 2026-10-05).
- **`/telecaller`** (index): `redirect("/telecaller/dashboard")`.
- **`WorkflowPanel` `ROLES_BY_DIVISION.global`:** gains `telecaller_manager` (no profile, so the generic form creates it). `telecaller`
  is **not** added: it needs a profile and is created on the Telecallers page.
- **Wording only:** `/admin/login` subtitle → "For Super Admins, BDM Managers and Telecaller Managers."; matching comments in
  `admin/forgot-password/page.tsx`, `LoginForm.tsx`, `ResetPasswordForm.tsx`.

### 6.2 Telecaller and manager pages

Server components following `app/bdm/profile` and `app/bdm/manager/team`: `serverApi` → `accessUnavailable(e, signIn)` on failure →
`PortalShell`. Sign-in target: `TELECALLER_SIGN_IN` for telecaller pages, `/admin/login` for manager pages.

| Page | Data | Content and states |
|---|---|---|
| `/telecaller/dashboard` | `GET /telecaller/me` | Greeting, a profile summary card (team, Employee ID, reporting manager), and "Your leads, calls and follow-ups will appear here." A missing profile shows the 403 message. |
| `/telecaller/profile` | `GET /telecaller/me` | `TelecallerProfileCard` (`<dl>`, read-only: name, email, team, Employee ID, reporting manager, status) plus `TelecallerPhoneForm` (client): one `type="tel"` field with label, `maxLength=40`, Save disabled while busy ("Saving…"), server error in an `aria-live` region with focus moved to it, typed value kept on failure, success announced with `role="status"`, then `router.refresh()`. |
| `/telecaller/manager/team` | `GET /telecaller/manager/team` | `TelecallerTeamTable`: name, Employee ID, team, mobile, status (word in a `.badge`), in a labelled focusable `.table-wrap` with a `<caption>`; Previous/Next links via `?offset=`. Empty: "No telecallers report to you yet." Past-the-end offset: message and "Go to the first page". |

Role labels in `PortalShell`: "IT Telecaller" / "Overseas Telecaller" / "Telecaller Manager".

### 6.3 Admin page — `AdminTelecallerPanel`

Copies bdm-001 §6.3 (structure, states, accessibility, mobile, keyboard, XSS rules), with these differences:

- **Files:** `lib/telecaller.ts` (types, `TEAM_LABEL`, display-only `creatableTeams(role)`, URLs, `managerSearch`), `AdminTelecallerPage`
  (server wrapper: role gate, nav), `AdminTelecallerPanel` (list, states, paging), `AdminTelecallerCreateForm`, `AdminTelecallerRow`.
  Reused: `SearchableSelect` (server mode), `lib/apiErrors`, `lib/welcomeLink`, `useFocusAfterRender`, `usersChanged`, `pageOffset`.
- **Mounts:** `/admin/telecallers` (super_admin), `/it/admin/telecallers` (it_admin, super_admin), `/overseas/admin/telecallers`
  (overseas_admin, super_admin).
- **Create:** full name, email, mobile; team — fixed text plus hidden input for a division admin, a two-option `<select>` for
  super_admin; Employee ID (`maxLength=40`); reporting manager via `SearchableSelect` against `/admin/telecaller-managers`. With no
  managers: "No active telecaller manager — a Super Admin must create one first", submit disabled. Success uses
  `welcomeLinkFeedback`. Server 403/409/422 messages inline.
- **Row edit:** name, mobile, Employee ID, manager editable; team shown read-only (TL7); activate/deactivate via `PATCH active` with
  inline confirm. "No active manager" badge when `manager_active` is false.
- **List:** "Loading telecallers…", error with Retry, empty "No telecallers yet. Use Create telecaller above to add the first one."

**Unchanged:** `AdminUserManagementPanel` (telecallers and managers appear in the generic directory under their role names),
`PortalShell`, `ResetPasswordForm` logic, every BDM page.

## 7. Acceptance criteria

From the backlog, with the test that proves each:

| AC | Statement | Proven by |
|---|---|---|
| AC1 | `super_admin` creates a telecaller (team, Employee ID, manager) and a manager. The invitee sets a password from the email link. | `test_tel_001_provisioning.py`; e2e |
| AC2 | An `it_admin` can create only IT telecallers. Creating a manager or an overseas telecaller → 403. | `test_tel_001_provisioning.py` |
| AC3 | A telecaller signs in at its team's portal and lands on `/telecaller/dashboard`. Wrong portal → the existing "use the correct portal" 403. | `test_tel_001_login.py`; `navigation.telecaller.test.ts`; e2e |
| AC4 | A manager sees only their direct reports. | `test_tel_001_reads.py`; e2e |
| AC5 | Signed-out `/telecaller/*` redirects to sign-in with `next`. | `middleware.test.ts`; e2e |

Backlog negative scenarios: reporting manager not a `telecaller_manager` → 422; duplicate Employee ID → 409; a telecaller calls
`/telecaller/manager/team` → 403. Edge cases: an inactive manager can't be chosen (422); the team can't be edited here (422).

## 8. Tests

Executed with real tools (pytest, vitest, Playwright in the CI containers), never judged by reasoning alone.

**Backend (pytest):**

| File | Covers |
|---|---|
| `test_tel_001_migration.py` | Table, check, unique and FK constraints; case-insensitive Employee ID index; downgrade refusal with rows. |
| `test_tel_001_provisioning.py` | AC1 (manager + IT and Overseas telecallers by super_admin; token issued; manager link `/admin/reset-password`, telecaller links on their division; reset response `login_portal` `"admin"` / `null`). AC2 (it_admin: IT telecaller 201, overseas telecaller 403, manager 403; overseas_admin mirrored). Missing profile 422; stray profile 422; team/division mismatch 422; manager not a manager 422; inactive manager 422; duplicate Employee ID 409 incl. different case; supplied password 422; audit metadata snapshot; existing roles and BDM creation unaffected. |
| `test_tel_001_update.py` | PATCH Employee ID and manager; team change 422; creator check on edit (it_admin on an Overseas telecaller 403); audit before/after; a non-telecaller with `telecaller_profile` 422. |
| `test_tel_001_reads.py` | AC4 (M1 sees only M1's reports; super_admin sees all; telecaller → 403 on the team route); `/telecaller/me`; `PATCH /telecaller/profile` phone set/clear, other field 422, bad phone 422, other role 403; `/admin/telecallers` team scoping, filter 403/422, paging; manager picker active-only and searchable. |
| `test_tel_001_login.py` | AC3: telecaller at own portal 200; at the other portal 403 naming its portal; manager at `/it/login` 403 naming `/admin/login`, at `/admin/login` 200. |

**Web (vitest):** `middleware.test.ts` (new cases, matcher list), `navigation.telecaller.test.ts` (landing map, navs, admin entries),
`TelecallerSignIn.test.tsx`, `AdminTelecallerPanel.test.tsx`, `AdminTelecallerCreateForm.test.tsx`, `AdminTelecallerRow.test.tsx`,
`TelecallerPhoneForm.test.tsx`, `TelecallerTeamTable.test.tsx`.

**Browser (Playwright):** `tel-001-telecaller-profile.spec.ts` — super_admin creates a manager (generic form) and an IT telecaller
(Telecallers page); each activates from its welcome link; the telecaller lands on `/telecaller/dashboard`, edits its phone; the manager
signs in at `/admin/login`, lands on `/telecaller/manager/team` and sees the telecaller; signed-out `/telecaller/profile` →
`/telecaller/sign-in?next=…` and `/telecaller/manager/team` → `/admin/login?next=…`; 390px check on the team and admin pages.

## 9. Regression risks

| Risk | Guard (lite regression set for this item) |
|---|---|
| Rule order in `create_user` (403 vs 422) changes for BDM or other roles | `test_adm_001_admin_crud`, `test_bdm_001_profiles`, `test_bdm_001_service`, `test_enh_003_first_time_provisioning`, `WorkflowPanel.create-user.test.tsx` |
| `middleware.ts` regex breaks an existing portal | `middleware.test.ts`, `auth-001-login.spec.ts`, `auth-002-rbac-ui.spec.ts`, `bdm-001-bdm-profile.spec.ts` |
| Reset link / `login_portal` change misroutes BDM managers or others | `test_bdm_001_reset_portal`, `test_bdm_001_admin_portal_links`, `ResetPasswordForm.test.tsx`, `AdminPasswordRecovery.test.tsx`, `enh-003-first-time-provisioning.spec.ts`, `test_enh_006_change_password` |
| Landing map | `LoginForm.next.test.tsx`, `AccessUnavailable.test.tsx`, `navigation*.test.ts` |
| Roles page lists new roles | `test_adm_012_roles_permissions`, `test_rbac`, `adm-012-roles-permissions.spec.ts` |
| Admin login subtitle text | `adm-001-admin-crud.spec.ts`, `adm-014-super-admin-console.spec.ts` (any test asserting the old text is updated) |

Per the owner's cadence, this item runs the lite set above; the owner runs the full backend suite every 4–5 stories.

## 10. Documentation (updated in the same change)

- `docs/decisions/PRODUCT_DECISION_REGISTER.md`: **`DEC-SCOPE-073`** (T1–T29 + TL1–TL7, the supersession note T29 → `DEC-SCOPE-072`
  L2/L7 recorded as pending tel-018).
- `docs/architecture/RBAC_MATRIX.md`: the two roles and their routes.
- `docs/architecture/API_CONTRACT.md`: the five routes, the `/admin/users` `telecaller_profile` branch, `login_portal`.
- `docs/ux/ROLE_NAVIGATION.md`: Telecaller and Telecaller Manager sections.
- `docs/ux/SCREEN_CATALOG.md`: the new screens.
- `docs/delivery/TELECALLER_CRM_BACKLOG.md`: tel-001 status, and the API line amended per §2.

## 11. Completion gates

COMPLETE only when: AC1–AC5 and the negative/edge scenarios pass; security/RBAC 403s pass; `alembic upgrade head` (and the guarded
downgrade) succeed on the test database; the lite regression set passes; `tsc`, eslint and `next build` pass; the 390px responsive and
the accessibility checks in §6 pass; the §10 docs are updated.
