# rec-001 — Recruiter scope for `placement_team` + new `placement_manager` (design)

Date: 2026-10-08 · Branch: `feature/rec-001` from `origin/main@99ec1c38` · Decision: `DEC-SCOPE-116` · Migration `0100` ·
API §12AI · RBAC §2.42 (all re-checked on `origin/main` at start; none taken by a parallel branch). **Status: MERGED** as PR #143 @
`9e957bee` (2026-10-08).

## 1. Authority
- `docs/delivery/RECRUITER_CRM_BACKLOG.md` §4 rec-001 (requirements, AC1–AC6, negatives, edge cases) and §3.1 R1–R15
  (`EXPLICIT_APPROVAL`, 2026-10-07; registered now as `DEC-SCOPE-116`).
- Owner answers 2026-10-08 (`EXPLICIT_APPROVAL`):
  - **Q-29:** a new `/recruiter/*` web workspace, like `/telecaller`. Signed-out recruiters go to `/it/login`. `/recruiter/manager/*`
    goes to `/admin/login`. The legacy `/it/placement/*` screens stay linked from the recruiter sidebar. A manager owns no companies.
  - **Q-28:** `hr_team` is unchanged in rec-001. Every `/recruiter/*` route returns 403 for `hr_team`.
  - **Admin page:** `/admin/recruiter-staff` and `/it/admin/recruiter-staff`, labelled "Recruiter Staff". The existing
    `/admin/recruiters` page (companies) is untouched until rec-003.
- Design choices that follow the tel-001 precedent (`DEC-SCOPE-073`) and were not asked separately:
  - `users.active` is the only active flag, so the profile has no `active` column.
  - A recruiter edits only their own phone.
  - A manager has no profile.

## 2. Approach
Three options were considered:
- **(A, chosen) Mirror tel-001.** A profile table, a nested `recruiter_profile` on `POST/PATCH /admin/users`, `services/recruiter.py`,
  `api/recruiter.py`, and a dedicated admin page.
- **(B) Generic profile table for all staff roles.** Rejected: it would redesign unrelated modules.
- **(C) Use the `UserRoleAssignment`/`require_*` dependencies.** Rejected by the 2026-09-28 inline-RBAC convention.

A is the smallest change and follows every existing pattern.

## 3. Data — `recruiter_profiles` (migration `0100_recruiter_profiles`)
| Column | Type | Rule |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK users, unique (`uq_recruiter_profiles_user`) | 1:1 with a `placement_team` user |
| employee_id | varchar(40) **nullable** | Unique case-insensitive (`uq_recruiter_profiles_employee_id` on `lower(employee_id)`) |
| reporting_manager_user_id | uuid FK users **nullable**, indexed | Must be an active `placement_manager` when set |
| created_at / updated_at | timestamptz | |

- Both fields are nullable because legacy rows have neither value: the backfill (AC5) and the generic Users form (an edge case).
  The Recruiter Staff page requires both.
- **Backfill:** `INSERT … SELECT` one empty profile for every `placement_team` user that has no profile. It runs on every upgrade and
  is idempotent, so it also runs when 0001 built the table from the models.
- **Downgrade:** refuses while any profile carries an Employee ID or a manager. Otherwise it drops the table, because backfilled rows
  hold no information.
- Only the new table is written. No existing row changes.

## 4. Backend
- `core/rbac.py`: `"placement_manager": {"placement:team"}`.
- `services/provisioning.ADMIN_PORTAL_ROLES` + `placement_manager`. This makes the welcome and reset links point to `/admin`, and
  `auth.reset_password` returns `login_portal: "admin"`.
- `services/recruiter.py` (no commits; the route owns the transaction):
  - `parse_profile_create`/`parse_profile_update` reuse `telecaller._parse` and return readable 422s.
  - `locked_active_manager` takes `FOR SHARE` and raises 422 "Reporting manager must be an active placement manager".
  - `flush_profile` raises 409 "Employee ID already exists".
  - `profile_snapshot`, `profile_out` (the manager may be null), `apply_profile_update` and `ensure_profile`.
  - `recruiter_context` raises 403 unless the role is `placement_team` and a profile exists.
  - `require_manager` allows `placement_manager` and `super_admin`. `team_filter` returns direct reports, or everyone for
    `super_admin`.
  - `require_recruiter_admin` allows `super_admin` and `it_admin`. `overseas_admin` gets 403.
- `admin.create_user`:
  - Role `placement_team`:
    - Allowed only for `super_admin`/`it_admin`, through the existing IT-division rule.
    - With `recruiter_profile`, both fields are validated and the manager is locked.
    - Without it (the generic form), an empty profile is created.
    - Either way, the profile is written in the same transaction as the user, the token and the audit row.
  - Role `placement_manager`: anyone but `super_admin` gets 403 "Only a Super Admin can create placement managers". Division
    `global`.
  - A `recruiter_profile` on any other role is 422 "Only a recruiter has a recruiter profile".
  - The response gains a `recruiter_profile` key, which is null for other roles.
- `admin.update_user`:
  - For a `placement_team` target, the profile is locked FOR UPDATE, or created if missing.
  - `recruiter_profile` uses PATCH semantics: an omitted key is unchanged and an explicit null is a 422. The manager is re-checked
    only when it changes.
  - Before and after values go into the audit row.
- `api/recruiter.py`:
  - `router` `/recruiter`: `GET /me`, `PATCH /profile` (phone only, reusing `telecaller.parse_self_update`, audit
    `recruiter.profile_update`), `GET /manager/team`.
  - `admin_router` `/admin`: `GET /recruiters` (filters `active` and `q` over name, email and Employee ID; `{items,total,limit,offset}`,
    one query, no N+1) and `GET /placement-managers` (the picker: active managers, with `recruiter_count`).
- `seed.py`: a demo `placement_manager`. The demo `placement_team` user gets a profile that reports to it.

## 5. Frontend
- `lib/navigation.ts`:
  - Landings: `placement_team` → `/recruiter/dashboard`, `placement_manager` → `/recruiter/manager/team`.
  - `RECRUITER_NAV`: Dashboard, Profile, then the legacy Candidates, Company Requirements, Interviews, Offers and Reports at
    `/it/placement/*`.
  - `RECRUITER_MANAGER_NAV`: Team.
  - `PORTAL_NAV["it/placement"]` gains "Recruiter workspace", so a recruiter can return from the legacy screens.
  - `SUPER_ADMIN_NAV` and `"it/admin"` gain "Recruiter Staff".
- `middleware.ts`:
  - `/recruiter` is protected.
  - `/recruiter/manager/*` redirects to `/admin/login`. Any other `/recruiter/*` redirects to `/it/login`.
  - The matcher gains `/recruiter/:path*`.
- Pages:
  - `/recruiter` redirects to the dashboard. `/recruiter/dashboard` is a shell with a welcome and the profile card. `/recruiter/profile`
    shows the card plus the phone form.
  - `/recruiter/manager` redirects to the team page. `/recruiter/manager/team` is a server-paged table of direct reports.
  - `/admin/recruiter-staff` and `/it/admin/recruiter-staff` are the admin pages.
- Components:
  - `AdminRecruiterPage`/`Panel`/`CreateForm`/`Row`. These follow the `AdminTelecaller*` states: loading, error with Retry, empty,
    search, pager, the in-flight guard, focus management, Esc to cancel and labelled mobile cards.
  - Rows with no manager show a "No manager" badge (AC5).
  - `RecruiterProfileCard`, `RecruiterTeamTable` and `lib/recruiter.ts`.
  - `TelecallerPhoneForm` gains `url`/`idPrefix` props so it is reused, not copied.
- `WorkflowPanel ROLES_BY_DIVISION.global` + `placement_manager`. The `it` list keeps `placement_team`, which is the legacy path and
  gets an empty profile.
- The admin sign-in and forgot-password copy mention Placement Managers.

## 6. Security
- Every scope comes from the session. No `/recruiter` route takes a user id, so there is no IDOR surface.
- The admin list is limited to `super_admin`/`it_admin`.
- `it_admin` cannot create a `global` manager: the existing division gate plus an explicit 403.
- Passwords are never set by an admin (the existing `_reject_supplied_password`).
- Logs carry ids only. Audit rows carry Employee ID and manager id, but no phone or email.

## 7. Tests (TDD)
- **Backend `tests/test_rec_001_*.py`:**
  - migration: chain, model parity, backfill, idempotency, round trip, downgrade refusal
  - provisioning: AC1, AC2, 422/409/inactive manager, legacy empty profile, stray profile, overseas_admin
  - update: set manager on a backfilled row, null refused, duplicate 409
  - reads: `/me`, phone PATCH, team scope AC4, `hr_team`/recruiter 403s, admin list scope, picker
  - login landing: the reset `login_portal`
- **Web (vitest):** middleware, navigation, `AdminRecruiterCreateForm`, `AdminRecruiterRow`, `RecruiterTeamTable`.
- **E2E:**
  - New `rec-001-recruiter-roles.spec.ts`.
  - `adm-007` and `rpt-001` now expect the `/recruiter/dashboard` landing, which is the intended AC3 change.

## 8. Regression risks
- `admin.create_user`/`update_user` for every role.
- Login landing for `placement_team`.
- Middleware for `/it`, `/admin`, `/bdm`, `/telecaller`.
- ADM-007/008 and RPT-001 e2e.
- tel-026 route inventory: the new prefixes are outside its PREFIXES.
