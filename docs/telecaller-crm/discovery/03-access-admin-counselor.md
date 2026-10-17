# Telecaller CRM: account access, admin provisioning and lifecycle, counselor handover side, lead intake (source discovery)

> **Evidence appendix** for `docs/telecaller-crm/documentation-analysis.md`. This is raw, read-only source discovery from master planning session S1 (2026-10-17, code `main` @ `6fee294d`), with field-level detail for the module sessions. Nothing here was checked in a browser. Where this file and the browser disagree, the browser wins: annotate this file, do not silently trust it.

Code baseline: `main` @ 6fee294d (worktree `tel-docs`). Read-only discovery.
Path prefixes: `api/` = `apps/api/app/api/`, `svc/` = `apps/api/app/services/`, `web/` = `apps/web/`. Every API path below is mounted under `/api/v1` (`apps/api/app/main.py:166`).
Legend: **VERIFICATION REQUIRED** means the behaviour was not run in a browser and code alone did not settle it.
Decision IDs (DEC-SCOPE-073 tel-001, -088 tel-005, -098 tel-019, -101 tel-018, -104 tel-025, -111 tel-020, -019 ENH-003, -021 ENH-006) are labels taken from code comments. The code is the authority.

Scope: only the Overseas team is in scope. IT-team telecallers (`/it/login`, `/it/admin/telecallers`) use the same code and appear only where the rules differ.

---

## 0. Shared mechanics

### 0.1 Roles involved

| Role | Division | Signs in at | Landing page (`ROLE_DASHBOARD_PATH`, `web/lib/navigation.ts:49-50`) | Sidebar |
|---|---|---|---|---|
| `telecaller` (Overseas team) | `overseas` (equals `telecaller_profiles.team`) | `/overseas/login` | `/telecaller/dashboard` | `TELECALLER_NAV` (`navigation.ts:103-110`): Dashboard, My Leads, Follow-ups, BDM requests, Notifications (unread badge, `web/lib/telecallerNav.ts`), Profile, plus the shared Tasks entry (`MANAGEMENT_TASKS_NAV`) |
| `telecaller_manager` | `global` | `/admin/login` | `/telecaller/manager/team` | `TELECALLER_MANAGER_NAV` (`navigation.ts:112-127`): Team, Leads, Follow-ups, Lead assignment, Distribution rules, Lead import, Targets, Performance, Reports, Alert settings, Products, Campaigns, Scripts, Templates, Brochures, Tasks |
| `overseas_admin` | `overseas` | `/overseas/login` | `/overseas/admin/dashboard` | Overseas admin nav has **"Telecallers"**, **"Telecaller Performance"**, **"Telecaller Reports"** (`navigation.ts:268`) |
| `super_admin` | `global` | `/admin/login` (the login skips the division check) | `/admin` | `SUPER_ADMIN_NAV` has **"Telecallers"** → `/admin/telecallers`, "Telecaller Performance", "Telecaller Reports" (`navigation.ts:297`) |
| `counselor` (Overseas) | `overseas` | `/overseas/login` | `/overseas/counselor/dashboard` | Overseas counselor nav includes **"Leads"** → `/overseas/counselor/leads` (`navigation.ts:266`) |

RBAC bundles: `telecaller: {"telecaller:self"}`, `telecaller_manager: {"telecaller:team"}` (`apps/api/app/core/rbac.py:53-55`). The real gates are inline in the services, listed per feature below.

### 0.2 Common refusal card
Telecaller pages catch API errors with `accessUnavailable(e, loginHref)` (`web/components/AccessUnavailable.tsx:48-59`).
- The card shows the heading **"Access unavailable"** with the API `detail` underneath.
- A signed-in user also gets **"Go to your dashboard"** and **"Sign out"**. A signed-out user gets a return-to-login link.
- Server details a telecaller can hit (`svc/telecaller.py:133-145`):

| Detail string | When |
|---|---|
| "Telecaller role required" | Any non-`telecaller` role opens a `/telecaller/*` (non-manager) page, e.g. a manager opening `/telecaller/profile` |
| "Telecaller profile not set up — contact your administrator" | The account has role `telecaller` but no `telecaller_profiles` row. The string is not in `BDM_ACCOUNT_STATE_REASONS` (`AccessUnavailable.tsx:19`), so the card still offers "Go to your dashboard", which loops back to the same refusal. **VERIFICATION REQUIRED** (cosmetic) |
| "Telecaller manager role required" | Any role other than `telecaller_manager` or `super_admin` calls a manager API |

---

## 1. Account access (AUTH)

### 1.1 Signed-out redirects (middleware)
`web/middleware.ts:2-24`:
- Public paths: `/admin/login`, `/admin/forgot-password`, `/admin/reset-password`, `/bdm/sign-in`, `/telecaller/sign-in` (`:2`).
- Any `/telecaller...` request without the `edusphere_access` cookie is redirected as follows:

| Requested path | Redirect target | Line |
|---|---|---|
| `/telecaller/manager` or `/telecaller/manager/...` | `/admin/login?next=<path+query>` | `:17` |
| any other `/telecaller...` (including `/telecaller` itself) | `/telecaller/sign-in?next=<path+query>` | `:19` |
| `/overseas/admin/...`, `/overseas/counselor/...` | `/overseas/login?next=...` | `:20-21` |
| `/admin...` | `/admin/login?next=...` | `:17` |

- `/telecaller` (`web/app/telecaller/page.tsx:3-5`) always redirects to `/telecaller/dashboard`.
- The middleware checks only that the cookie exists. Role checks happen per page through the API.

### 1.2 `/telecaller/sign-in` (chooser)
`web/app/telecaller/sign-in/page.tsx:8-27`.

| Element | Literal |
|---|---|
| Links at the top | BrandLogoLink; **"← Corporate website"** → `/` |
| H1 | **"Telecaller sign-in"** |
| Text | **"Choose your team's portal. Telecaller Managers sign in at Administration."** ("Administration" links to `/admin/login`) |
| Buttons | **"IT team"** → `/it/login`; **"Overseas team"** → `/overseas/login` |
| `next` handling | `safeNextPath` (same-origin only) is passed to both team buttons. The Administration link keeps `next` only when it starts with `/telecaller/manager` (`:11-12`) |

### 1.3 `/overseas/login` and `/admin/login`

| Page | File | Visible text |
|---|---|---|
| `/overseas/login` | `web/app/overseas/login/page.tsx:12` | Brand panel: eyebrow "Overseas Education Portal", H1 "Your global education journey, organised.", lead "Dashboards for students, counselors, university representatives, agents, and administrators." Card: "← Back to Overseas Education", H2 **"Overseas Education Portal"**, "Sign in with your authorised overseas education account.", LoginForm (division `overseas`), "Student or agent? **Create an account**". A dev-only "Demo accounts" box appears when `ENVIRONMENT!=="production"`. It lists no telecaller demo account |
| `/admin/login` | `web/app/admin/login/page.tsx:13` | Brand: eyebrow "Central Administration", H1 "One governance layer. Independent operations." Card: "← Corporate website", H2 **"Administration sign-in"**, **"For Super Admins, Partners, Accountants, Partnership Heads and BDM, Telecaller and Placement Managers."**, LoginForm (division `global`), dev-only "Demo super admin" box |

**LoginForm** (`web/components/LoginForm.tsx:17-63`):
- Fields **"Email"** and **"Password"**. Button **"Sign in securely"** (shows **"Signing in…"** while busy).
- Link **"Forgot your password?"** → `/overseas/forgot-password`. A `global` form links to `/admin/forgot-password` (`:57`).
- Footnote: "Use the portal that matches your account. Role and division access is verified by the API."
- On success it follows `safeNextPath(next)`, otherwise `dashboardPathFor(user)` (`:40`).
- On failure it shows the API `detail` in a `form-error` alert.

**`POST /auth/login`** (`api/auth.py:106-121`):

| Case | Status | Exact detail |
|---|---|---|
| Unknown email, wrong password, or **inactive account** (the query filters `active=true`, `:108`) | 401 | **"Invalid credentials"** |
| Right password, wrong portal (not super_admin, `payload.division != user.division`) | 403 | **"Use the correct EduSphere portal for this account: sign in at {PORTAL_SIGN_IN[division]}"**, with `PORTAL_SIGN_IN = {"it": "/it/login", "overseas": "/overseas/login", "global": "/admin/login"}` (`:36`). An Overseas telecaller at `/it/login` sees "...sign in at /overseas/login". A telecaller manager at `/overseas/login` sees "...sign in at /admin/login" |
| Success | 200 | Sets the `edusphere_access` and `edusphere_refresh` cookies (`:98-103`). Writes an `auth.login` audit row |

### 1.4 Sessions

| Rule | Source |
|---|---|
| Access token lasts 60 min, refresh token 14 days (config defaults; the deployed env may override) | `apps/api/app/core/config.py:11-12`. **VERIFICATION REQUIRED**: prod values, and whether the web client refreshes silently |
| Every request re-loads the user with `active=true`. A missing or inactive user gets 401 **"User unavailable"** | `api/deps.py:15, 53-58` |
| The token's `sv` must equal `users.session_version`, otherwise 401 **"Your session has ended. Please sign in again."** | `api/deps.py:17, 36-37` |
| These events bump `session_version` and so end the session at once: tel-025 deactivation, team move, plain deactivation through Users, manager deactivation | `svc/telecaller_lifecycle.py:239-252, 300-312` |

### 1.5 Sign out
- **PortalShell** sidebar footer (`web/components/PortalShell.tsx:17`) has three buttons: **"Change password"** → `/account/password`, **"My profile"** → `/account/profile`, **"Sign out"**.
- Sign out calls `POST /auth/logout` (`api/auth.py:307-311`, which deletes both cookies) and then goes to **`/`** (the corporate home), not to a sign-in page.
- The "Access unavailable" card's **"Sign out"** button (`web/components/SignOutButton.tsx`) instead goes to the page's `loginHref`.

### 1.6 Welcome / set-password link (first sign-in)
Source: `svc/provisioning.py`.

| Rule | Detail | Line |
|---|---|---|
| Account creation | The account is created with an unusable random password hash. The admin never sets a password: sending a `password` field gets 422 **"A password cannot be supplied; the user sets their own via the emailed set-password link"** (`api/admin.py:122`) | `:51-53` |
| Token | Single-use, hashed at rest, `purpose="welcome"`, valid for **72 hours** (`WELCOME_EXPIRY_HOURS`) | `:37, 102-114` |
| URL path | `{FRONTEND_URL}/{segment}/reset-password?token=...`, where segment = **`admin`** for `ADMIN_PORTAL_ROLES` (includes `telecaller_manager`, `:68`), else **`overseas`** when division is overseas, else `it`. So an Overseas telecaller gets `/overseas/reset-password?token=…` and a telecaller manager gets `/admin/reset-password?token=…` | `:71-75` |
| Email | Subject **"Welcome to EduSphere -- set your password"**, H1 "Welcome to EduSphere", "{inviter} has created your EduSphere account as **{role label}**. Set your password to get started.", button **"Set your password"**, "This link is single-use and expires in …". The role label falls back to the title-cased role, i.e. **"Telecaller"** / **"Telecaller Manager"** (`svc/mailer.py:77`) | `svc/mailer.py:228-325` |
| Delivery | Runs after the commit, through SMTP plus the generic webhook. A failure never rolls back the account. The response carries `email_status` and `expires_at`, plus `development_welcome_token` in dev/test only | `:117-173` |
| Admin feedback | On sent: **"Telecaller created. A set-password link was emailed and is valid for 72 hours."** Otherwise (amber warning): **"Telecaller created. The email was not delivered (email is not configured on this server \| the email could not be sent). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page."** | `web/lib/welcomeLink.ts:11-20` |
| Re-send | `POST /admin/users/{id}/welcome-links` (`api/admin.py:756-781`). Same division unless super_admin (403 "Cannot manage another division"). 409 **"This account has no pending invitation (its password is already set)"**. 409 **"Reactivate this account before re-sending its link"**. 429 **"A link was just sent; wait {n} seconds before re-sending"** (60 s cooldown after the first re-send, `provisioning.py:39, 228-238`). The UI is the **"Re-send link"** button on the Users page "Manage users" panel, filter **"Awaiting setup"** / **"Link expired"** (`web/components/AdminUserManagementPanel.tsx:201-268`). The Telecallers page has **no** re-send button | |
| Changing `active` | Any real change of `active` revokes open welcome links (`api/admin.py:734-738`). After a reactivation the admin must Re-send | |

### 1.7 Reset-password pages (welcome and forgot)
`/overseas/reset-password` (`web/app/overseas/reset-password/page.tsx`) and `/admin/reset-password` (`web/app/admin/reset-password/page.tsx`) share this layout: "← Back to sign in", H2 **"Choose a new password"**, then `ResetPasswordForm` (`web/components/ResetPasswordForm.tsx`).
- Field **"New password"**, hint "Use at least 10 characters." Button **"Reset password"** (shows **"Resetting…"** while busy).
- With no token: **"This reset link is missing its token. Request a new one from the forgot-password page."**
- `POST /auth/reset-password` (`api/auth.py:392-444`):
  - 422 "Password must be at least 10 characters" / "Password must be at most 128 characters".
  - 400 **"Reset token is invalid or expired"** for an unknown, used, expired or superseded token, and also for a welcome token on an inactive account.
  - On a 400 the form adds **"Request a new reset link"** (→ `/{division}/forgot-password`) and "or, if this was your first-time invitation, ask your administrator to re-send it."
- A welcome token also sets `email_verified=true`.
- After success the response has `login_portal: "admin"` for `ADMIN_PORTAL_ROLES`. The form then redirects to **`/admin/login`** for a telecaller manager, otherwise to `/{division}/login`, so **`/overseas/login`** for a telecaller who used the overseas page (`ResetPasswordForm.tsx:107`).

### 1.8 Forgot password
| Page | Text |
|---|---|
| `/overseas/forgot-password` | "← Back to sign in", H2 **"Reset your password"**, "Enter the email on your Overseas Education account and we'll send reset instructions." |
| `/admin/forgot-password` | Same heading. "Enter the email on your administration, BDM Manager, Telecaller Manager, Placement Manager, Partnership Head, Partner or Accountant account and we'll send reset instructions." |

- `ForgotPasswordForm` has field **"Email"** and button **"Send reset instructions"** ("Sending…" while busy). Afterwards it always says **"If an account exists for that email, we've sent instructions to reset the password."**
- In development it also shows "Development only: reset link", a relative `reset-password?token=…` link that resolves to the same portal.
- `POST /auth/forgot-password` (`api/auth.py:369-389`): only for an active account. 30-minute token. Adds an in-app notification "Password reset requested". Always answers 202 `{accepted:true}`.
- **Finding:** the reset email goes only to the generic email **webhook** (`send_notification`, `svc/integrations.py:23-29`) with the raw token and **no URL**. There is no SMTP send for reset emails, unlike the welcome link. Which portal page the emailed reset points to is therefore defined outside this code. This is a known open item: `docs/decisions/PRODUCT_DECISION_REGISTER.md:2135`. **VERIFICATION REQUIRED** before documenting "check your inbox" for telecallers.

### 1.9 Change password (`/account/password`)
- Shared page inside PublicShell, reached from the sidebar's **"Change password"**. Page title "Change your password".
- `ChangePasswordForm` fields: **"Current password"**, **"New password"** (hint "Use at least 10 characters."), checkbox **"Show passwords"**. Button **"Change password"** ("Changing…" while busy).
- Footnote: "You stay signed in on this device. Other devices stay signed in until their sessions expire."
- Success: **"Your password was changed."**

`POST /auth/change-password` (`api/auth.py:447-480`):

| Case | Status | Message |
|---|---|---|
| New password equals current | 422 | "New password must be different from the current password" |
| Wrong current password | 400 | "Incorrect current password". The form adds "Forgot your current password?" only when the user has an `it`/`overseas` division, so **a telecaller manager (global) gets no forgot link** (`web/app/account/password/page.tsx:62`) |
| 5 failures in 15 min | 429 | UI: "Too many incorrect attempts. Try again in …" |
| 401 | — | "Your session has expired. Sign in again to change your password." with IT and Overseas sign-in links only, no admin link for managers. **VERIFICATION REQUIRED** (cosmetic gap for managers) |

### 1.10 Profile restrictions
| Surface | Rule | Source |
|---|---|---|
| `/telecaller/profile` (sidebar "Profile") | Eyebrow "Profile", H2 **"My profile"**, "You can update your mobile number. Contact your administrator to change anything else." Read-only card rows: **Name, Employee ID, Team, Mobile, Email, Reporting manager** (with " (inactive)" when the manager is inactive), **Status** (Active/Inactive). Form field **"Mobile"** (tel, max 40), button **"Save mobile"** ("Saving…"). Success **"Mobile saved."**. Role label in the sidebar pill: **"Overseas Telecaller"** (`teamRoleLabel`) | `web/app/telecaller/profile/page.tsx`, `web/components/TelecallerProfileCard.tsx:8-16`, `TelecallerPhoneForm.tsx:61-75`, `web/lib/telecaller.ts:13` |
| `GET /telecaller/me` | Telecaller only (`telecaller_context`) | `api/telecaller.py:74-77` |
| `PATCH /telecaller/profile` | Body is `{phone}` only. Any other key gives 422 "Unknown field: {key}". The phone is trimmed, max 40, digits/spaces/+-() only, and null/"" clears it. Audit `telecaller.profile_update` records the field name only | `api/telecaller.py:80-89`, `apps/api/app/schemas.py:4970-4976` |
| `/account/profile` (sidebar "My profile") | For `telecaller`, **"Full name"** is read-only with the hint **"Your administrator manages your name."**. Field "Phone", button "Save changes" | `web/app/account/profile/page.tsx:70`, `web/components/ProfileForm.tsx:32-60` |
| `PATCH /auth/me` | For `PHONE_ONLY_ROLES` (`telecaller`), a changed name or profile gives 403 **"Telecallers can change only their phone number — contact your administrator"**. The phone goes through the same parser | `api/auth.py:35, 335-366` |
| Telecaller manager | Has no telecaller profile. `/account/profile` edits name and phone freely (not in `PHONE_ONLY_ROLES`). **VERIFICATION REQUIRED** that this is intended |

---

## 2. Admin provisioning (ADM, tel-001)

### 2.1 Who creates what
`svc/telecaller.py:21-25`, `api/admin.py:523-661`.

| Actor | Telecaller (team) | Telecaller manager | Where |
|---|---|---|---|
| `super_admin` | IT and Overseas | **Yes, Super Admin only** | Telecaller: `/admin/telecallers`, or typed `/overseas/admin/telecallers`. Manager: `/admin/users` generic **"Create user"** form, Division `global`, Role `telecaller_manager` (`web/components/WorkflowPanel.tsx:374, 383, 393`) |
| `overseas_admin` | Overseas only (403 **"Your role cannot manage IT telecallers"**) | No: 403 **"Only a Super Admin can create telecaller managers"** (`api/admin.py:556-557`) | `/overseas/admin/telecallers` |
| `it_admin` | IT only | No | `/it/admin/telecallers` (out of scope) |

- The generic "Create user" role list for an Overseas Admin does **not** include `telecaller` (`WorkflowPanel.tsx:367`). A telecaller can only be created on the Telecallers page, because the profile is required.
- The API still accepts `role:"telecaller"` in division `overseas` (`api/admin.py:591`).

### 2.2 Telecallers page
- Routes: `/overseas/admin/telecallers` (`web/app/overseas/admin/telecallers/page.tsx`, roles `overseas_admin` and `super_admin`, login `/overseas/login`) and `/admin/telecallers` (super_admin only).
- Both render `web/components/AdminTelecallerPage.tsx:26-54`.
- A role mismatch shows the access card with **"Overseas Administrator role required"** / **"Super Administrator role required"**.
- Header: eyebrow "Workspace", H2 **"Telecallers"**, and the text: "Create telecallers, set their reporting manager and keep their profiles current. Each new telecaller gets an emailed set-password link. Deactivating or moving a telecaller hands their open leads to a teammate or the team queue. Telecaller Managers are created from Users."

**Create telecaller** card (`web/components/AdminTelecallerCreateForm.tsx`):

| Field (label literal) | Rules |
|---|---|
| **Full name (required)** | Max 160 (422 "Full name must be at most 160 characters") |
| **Email (required)** | Valid email (422 "A valid email address is required"). Duplicate gives 409 **"Email already exists"** |
| **Mobile** | Optional, max 40 |
| **Team** | Display only. An Overseas Admin sees "Team **Overseas**". A super admin gets the select **"Team (required)"** with IT / Overseas |
| **Employee ID (required)** | Trimmed, max 40, no control characters. **Unique case-insensitively** (409 **"Employee ID already exists"**, index `uq_telecaller_profiles_employee_id`) |
| **Reporting manager (required)** | Server-search picker over **active telecaller managers** (`GET /admin/telecaller-managers?q=&limit=20`). It is disabled while no manager exists, with the hint **"No active telecaller manager — a Super Admin must create one first."** Server: 422 **"Reporting manager must be an active telecaller manager"**. An invalid id gives "Reporting manager: choose a manager from the list" |
| Button | **"Create telecaller"** ("Creating…" while busy) |

- Request: `POST /admin/users` with body `{role:"telecaller", full_name, email, phone, telecaller_profile:{team, employee_id, reporting_manager_user_id}}`.
- Server order (`api/admin.py:546-557`): profile parse (422), creator team (403), division must equal the team (422 **"Division must match the telecaller's team"**). A missing profile gives 422 "Telecaller profile is required".
- The user, profile, welcome token and audit (`user.create` with the profile snapshot) are written in one transaction (`:626-650`).
- After creation the list filters to the new Employee ID.

**Telecallers list** (`web/components/AdminTelecallerPanel.tsx`):
- `GET /admin/telecallers?limit=50&offset=&q=` (`api/telecaller.py:235-250`, `ensure_admin`).
- Scoped in SQL to the actor's teams. A `team` outside them gives 403.
- Search placeholder **"Name, email or Employee ID"**, buttons **"Search"** / **"Clear search"**.
- Columns: **Name** (with email), **Employee ID**, **Team**, **Manager** (badge **"No active manager"** when the manager is inactive), **Status** (Active/Inactive badge), Actions.
- States: "Loading telecallers…" / "Unable to load telecallers." + **Retry** / **"No telecallers yet. Use the Create telecaller form to add the first one."** / "No telecallers match “…”." / "This page is past the end of the list." + "Go to the first page".
- Pager: "Showing a–b of N", **Previous** / **Next**.
- If the manager check fails: "Unable to load telecaller managers." + "Retry loading managers".

**Row actions** (`web/components/AdminTelecallerRow.tsx`):

| Button | Shown when | Effect |
|---|---|---|
| **Edit** | Always | Inline form. **Full name (required)**, **Mobile**, "Team **Overseas (cannot be changed here)**", **Employee ID (required)**, **Reporting manager (required)** (starts on the current manager). **Save** / **Cancel** (Esc also cancels). Sends `PATCH /admin/users/{id}` with `{full_name, phone, telecaller_profile:{employee_id, reporting_manager_user_id}}`. A changed team gives 422 **"Team cannot be changed here"** (`svc/telecaller.py:121-122`). The manager is re-checked only when it changed. Notice **"Saved {name}."** |
| **Deactivate** | Active row | tel-025 group (§3) |
| **Move team** | Active row and the actor manages both teams (**super_admin only** in practice, `canMoveTeams`) | tel-025 group (§3) |
| **Reactivate** | Inactive row | `PATCH /admin/users/{id}` `{active:true}`. Notice **"Reactivated {name}."**. Welcome links are revoked on the change (§1.6). The leads that were moved away do not come back |
| **Reassign open work** | Inactive row | tel-025 handover (§3) |

**Telecaller managers card**: super_admin only. See §3.4.

### 2.3 `telecaller_profiles` model
`apps/api/app/models.py:2661-2677`:
- Columns: `id`, `user_id` (unique), `team` (CHECK `it`/`overseas`, equal to the user's division), `employee_id` (String 40, unique on `lower()`), `reporting_manager_user_id` (FK users, indexed), plus timestamps.
- Name, email, mobile and active live on `users`.

### 2.4 Manager side of provisioning
- `/telecaller/manager/team` (`web/app/telecaller/manager/team/page.tsx`): eyebrow "Team", H2 **"Telecallers who report to you"**, empty state **"No telecallers report to you yet."**
- `GET /telecaller/manager/team` (`api/telecaller.py:92-97`) returns direct reports, inactive ones included. Super admin sees everyone.
- Managers cannot create, edit, deactivate or move telecallers: every `/admin/telecallers*` route requires `ensure_admin`, which gives 403 **"Admin role required"** (`api/admin.py:110-113`).

---

## 3. Lifecycle (ADM, tel-025)

All routes: `api/telecaller_lifecycle.py`, `ensure_admin`, then `load_telecaller`:
- 404 **"Telecaller not found"** if the user is not a telecaller with a profile.
- 403 **"Your role cannot manage {Team} telecallers"** if the actor does not manage that team (`svc/telecaller_lifecycle.py:180-187`).
- Every refusal happens before any write, and each route is one transaction.

### 3.1 What counts as "open work"
`svc/telecaller_lifecycle.py:156-177`:
- Open leads: `telecaller_user_id = X` and status not in `converted` or CLOSED. Closed and converted leads keep their telecaller, for history and credit.
- Open follow-ups (`status="open"`) and open appointments of those leads **ride with the lead**. They keep their records and simply follow the lead (`:134`).
- Preview: `GET /admin/telecallers/{id}/open-work` → `{leads, follow_ups, appointments}` (`api/telecaller_lifecycle.py:34-38`).

### 3.2 UI group (`web/components/AdminTelecallerLifecycle.tsx`)
| Element | Literal |
|---|---|
| Loading / error | "Loading open work…" / "Unable to load {name}'s open work." + Retry |
| Summary | **"Open work: {n} open lead(s), with {n} open follow-up(s) and {n} appointment(s)."**, or **"{name} has no open leads."** |
| Choice (only if leads > 0) | Legend **"Who takes over their open leads?"**, radios **"Another Overseas telecaller"** / **"Overseas unassigned queue"**. The picker **"Hand the leads to"** searches active same-team telecallers, excluding the leaver |
| Deactivate note | "Their call history stays with them; they are signed out and can no longer sign in." Buttons **"Confirm deactivate"** ("Deactivating…") / **"Keep active"** |
| Move note | "Move {name} from the {team} team to the {other} team. Their open leads stay on the {team} team." Optional picker **"Reporting manager"**, then "They are signed out and sign in again at the {other} portal." Buttons **"Move team"** ("Moving…") / **"Cancel"** |
| Handover | Buttons **"Reassign"** ("Reassigning…") / **"Cancel"**, or **"Close"** when there are no open leads |
| Success notices | "Deactivated {name}. {n} open lead(s) now with {picked}." or "...moved to the Overseas unassigned queue." / "Moved {name} to the {Team} team; they sign in again there. …" / "{n} open lead(s) from {name} now with … ." |
| 5xx | "We couldn't deactivate {name}. Please try again." (and the move / reassign variants) |

### 3.3 Server rules
| Endpoint | Handler | Rules and messages |
|---|---|---|
| `POST /admin/telecallers/{id}/deactivate` body `{target?: "telecaller"\|"queue", reassign_to?}` | `api/telecaller_lifecycle.py:41-60` | 409 **"This telecaller is already inactive"**. With open leads and no target: 422 **"Choose who takes over this telecaller's open leads"**. A bad target (self, inactive, other team, not a telecaller): 422 **"Choose an active telecaller of the same team"** (one message for every case). Schema: 422 "Choose the telecaller who takes over" / "Only a telecaller target takes reassign_to" (`schemas.py:6598-6612`). Effects: each lead is reassigned through tel-007 `assign` (method `deactivation`) or loses its telecaller (queue). The stage is unchanged. One `lead.assign` audit row per lead. **Distribution rules naming the telecaller are deleted** (audit `telecaller.rule_delete`). `active=false`, `session_version+1`, welcome links revoked. Audit `telecaller.deactivate`. The target gets one in-app notification plus email **"Leads handed over to you"** / "{n} lead(s) from {name} are now yours." → `/telecaller/leads` (`svc/telecaller_lifecycle.py:261-265`) |
| `POST /admin/telecallers/{id}/handover` | `:63-79` | For an inactive telecaller who still holds open leads. 409 **"Deactivate this telecaller first"**. 409 **"No open leads to hand over"**. Same target rules. Method `handover` |
| `POST /admin/telecallers/{id}/move-team` body `+ team, reporting_manager_user_id?` | `:82-103` | The actor must manage **both** teams. Same team gives 422 **"This telecaller is already on the {Team} team"**. Open leads stay in the **old** team (a same-old-team telecaller or the old queue). Team and division change together. Optional new manager (must be active, else 422 "Reporting manager must be an active telecaller manager"). Rules are removed and the session ends. The account stays active |
| Plain `PATCH /admin/users/{id}` `{active:false}` (Users page "Deactivate") | `api/admin.py:716-719`, `svc/telecaller_lifecycle.py:300-312` | A telecaller with open leads gets 422 **"This telecaller has {n} open lead(s). Deactivate them from the Telecallers page, choosing who takes over"**. With no open leads it is allowed: rules are removed and the session ends |

### 3.4 Telecaller manager deactivation (super_admin only)
**Telecaller managers** card (`web/components/AdminTelecallerManagersCard.tsx`):
- Shown only when `role === "super_admin"` (`AdminTelecallerPanel.tsx:197`).
- H3 **"Telecaller managers"**, with the text "A manager who still has telecallers is deactivated together with the manager who takes them over."
- Columns: **Manager**, **Telecallers** (count, active and inactive). Button **Deactivate**.
- If the manager has telecallers: "Move their {n} telecaller(s) to another manager." with the picker **"Replacement manager"** (required). Otherwise: "They have no telecallers; they can no longer sign in."
- Buttons **"Confirm deactivate"** / **"Keep active"**. Success notice: "Deactivated {name}. {n} telecaller(s) now report(s) to {picked}."
- Empty state: "No active telecaller managers."

`POST /admin/telecaller-managers/{id}/deactivate` `{reassign_to?}` (`api/telecaller_lifecycle.py:111-129`):
- Non-super gets 403 **"Only a Super Administrator can deactivate a telecaller manager"**.
- 404 "Telecaller manager not found". 409 "This manager is already inactive".
- Bad replacement gives 422 **"Choose another active telecaller manager"**.
- All reports move in one UPDATE.
- The plain Users-page path for a manager with reports gives 422 **"This manager has {n} telecaller(s). Deactivate them from the Telecallers page (Telecaller managers), choosing who takes over"**.
- There is **no reactivate control** for managers on this card. Reactivation goes through Users. **VERIFICATION REQUIRED**.

---

## 4. Counselor side of handover and conversion (CNS, tel-018) and tel-019 BDM touchpoints

### 4.1 The handover itself (telecaller or manager action, for context)
- UI: `web/components/LeadHandoverForm.tsx`. Button **"Assign to counselor"** (or "Change counselor"), select **"Counselor"**, note "The counselor takes over the lead. You keep read access and its open follow-ups are cancelled.", button **"Hand over"** ("Handing over…"). Empty case: "No other active counselor in this division."
- `POST /telecaller/leads/{id}/handover` `{counselor_id}` (`api/lead_handover.py:28-36`, `svc/lead_handover.py:40-54`):

| Status | Message / effect |
|---|---|
| 404 | Lead outside scope |
| 403 | Telecaller on an already handed-over lead: **"This lead is with the counselor; you can view it but not change it"** (`svc/telecaller_leads.py:21`) |
| 409 | Closed lead: **"This lead is closed; reopen it before handing it over"** |
| 409 | At or past Application/Enrollment: **"This lead is already past the counselor handover"** |
| 422 | Bad counselor: **"Choose an active counselor of the lead's division"** (`svc/lead_appointments.py:85-90`) |
| 409 | Same counselor: **"This lead is already with this counselor"** |
| Effect | `owner_id = counselor`. The stage is unchanged. Open follow-ups are cancelled with reason **"Handed over to counselor"**. Audit `lead.handover` |

- **The counselor gets no notification** on a handover: `handover()` sends none. The lead just appears in their list. **VERIFICATION REQUIRED / open question.**
- After a handover the telecaller is read-only (`read_only = role=="telecaller" and owner_id is not None`, `svc/telecaller_leads.py:27-35`). Every telecaller write gives 403 with the string above. A manager can still act.

### 4.2 Counselor "My leads" (`/overseas/counselor/leads`)
- Rendered by `PortalPage` → `CounselorLeadsPanel` (`web/components/PortalPage.tsx:43`, `web/components/CounselorLeadsPanel.tsx`). The portal payload `GET /portal/overseas/counselor/leads` still gates the page.
- Eyebrow "Leads", H2 **"My leads"**, "Leads telecallers handed to you. Open one to link the student account or return it to the telecaller."
- Table **"Leads handed to you"**, 20 per page. Columns: **Lead ID** (link), **Name**, **Interest**, **Stage**, **Telecaller** ("Unassigned" when none), **Lead date**.
- Empty state: **"No leads have been handed to you yet."** Error: "Unable to load your leads." + **Try again**.
- `GET /counselor/leads` (`api/lead_handover.py:39-41`). Scope: `role=="counselor"` (else 403 **"Counselor role required"**), `owner_id == me` and `division == my division` (`svc/lead_handover.py:59-63`).
- **VERIFICATION REQUIRED**: whether a generic WorkflowPanel also renders below the panel on this section.

### 4.3 Counselor lead detail (`/overseas/counselor/leads/[id]`)
- `web/app/overseas/counselor/leads/[id]/page.tsx` → `CounselorLeadPage` (404 becomes notFound, other errors the access card) → `CounselorLeadDetail`.

| Area | Literals |
|---|---|
| Header | "Back to my leads", H2 = lead name, "Stage: **{stage}**" |
| Student account section | H3 **"Student account"**. If linked: "Linked to **{name}** ({email})" plus **"Unlink student"** (confirm "Unlink {name}? The lead goes back to Follow-up." **"Yes, unlink"** / **"Keep it"**). If converted: "The student has enrolled, so the lead is converted. Only an admin can unlink it." If not linked: the suggestion list ("Suggested match", "Matching students"), search **"Search students"** (placeholder "Name, email or mobile", min 3 characters, "Enter at least 3 characters."), button **Link**, confirm "Link {name} to this lead? The lead moves to Application/Enrollment." **"Yes, link"** / **"Keep looking"**. "Already linked to another lead" marks taken accounts. Empty: "No student account has this lead's email or mobile. Search for one below." / "No active student account matches that search." Notices: "Student linked." / "Student unlinked." |
| Return | Button **"Return to telecaller"**, field **"Reason for returning"** (required: "Add a reason for returning the lead."), buttons **"Return lead"** ("Returning…") / Cancel. Success **"Lead returned to the telecaller."** |
| Milestones | H3 **"Student and milestones"**: "No student account is linked yet." / "No enrolment or application yet." Items are labelled "IT enrolment" / "Overseas application" / "Visa case" with status, reference and time (`web/lib/leadHandover.ts:21`) |
| Lead details | Lead ID, Mobile number, Email, City, Qualification, Lead source, Product interest, Telecaller, Lead date |
| Activity | H3 **"Activity"**: the merged timeline (`GET /counselor/leads/{id}/timeline`) |

| Endpoint | Handler | Rules |
|---|---|---|
| `GET /counselor/leads/{id}` | `api/lead_handover.py:44-46` | Runs `observe_conversion` first. Returns `permissions {return, link, unlink}` (`svc/lead_handover.py:66-68`) |
| `POST /counselor/leads/{id}/return` `{reason}` | `:57-63` | Linked lead: 409 **"Unlink the student before returning the lead"**. Effects: stage goes back to Follow-up (`returned` event, reason in the stage history), `owner_id=None`, open appointments cancelled with reason **"Returned to telecaller"**, the telecaller is alerted (`telecaller_alerts.notify_returned`) |
| `GET /counselor/leads/{id}/link-suggestions?q=` | `:66-72` | Active `overseas_student` accounts. Without q: email or last 10 mobile digits equal the lead's. Max 10 |
| `POST /counselor/leads/{id}/student-link` `{student_id}` | `:75-82` | Already linked: 409. Student must be active and in the lead's division (422). Student linked to another lead: 409 (unique index backstop). Stage moves to **Application/Enrollment**, or straight to Converted if evidence already exists |
| `DELETE /counselor/leads/{id}/student-link` | `:85-92` | Converted lead: 409 **"Only an admin can unlink a converted lead"**. Otherwise back to Follow-up |

**Conversion** (`svc/lead_handover.py:128-169`):
- A lead at `application_enrollment` with a linked student becomes **Converted**, set by the system, when the student has an **`OverseasApplication.status == "enrolled"`** (or an active IT enrolment).
- This is checked on each detail read and by a 15-minute beat sweep.
- The telecaller stays read-only throughout.
- Admin equivalents:
  - `POST /admin/leads/{id}/conversion` `{student_email}` (link by exact email, `api/admin.py:446-454`).
  - `DELETE /admin/leads/{id}/conversion` (the only way to unlink a converted lead, `:457-464`).
  - UI: the Overseas Admin **Leads** section (`/overseas/admin/leads`, `WorkflowPanel.tsx:461`). **VERIFICATION REQUIRED**: field labels on the admin conversion panel (not read here).

### 4.4 tel-019 BDM meeting requests: BDM touchpoints only
- Telecaller side (in scope elsewhere): sidebar **"BDM requests"** → `/telecaller/meeting-requests`. API `/telecaller/meeting-requests` (`api/bdm_meeting_requests.py:28, 33-66`): `GET /options`, `POST ""`, `GET ""`.
- BDM side touchpoints:

| Who | Where | API |
|---|---|---|
| BDM | Sidebar **"Requests"** → `/bdm/meeting-requests`, detail `/bdm/meeting-requests/[id]`. Card on `/bdm/my-day` | `GET /bdm/meeting-requests`, `GET /{id}`, `POST /{id}/accept` (books a bdm-006 appointment, all bdm-006 rules apply), `POST /{id}/decline` (reason required, final) (`:68-120`) |
| BDM manager / super_admin | Sidebar **"Requests"** → `/bdm/manager/meeting-requests` (read only). Only a BDM accepts or declines | same GETs |

---

## 5. Settings and lead intake sources (ADM / INTAKE)

### 5.1 Telecaller settings (`api/telecaller_settings.py`, tel-020)
- These are **alert thresholds only**: `not_contacted_hours` (**"Lead not contacted after (hours)"**) and `hot_pending_hours` (**"Hot lead pending after (hours)"**), one row per team, seeded by migration 0099 (`schemas.py:5810-5817`).
- `GET /telecaller/settings` and `PUT /telecaller/settings/{team}` (`:27-50`) are open to `telecaller_manager` or `super_admin` (`require_manager`). **Any manager edits both teams.** An unknown team gives 404 "Team not found". Audit `tel.settings.update`.
- UI: manager sidebar **"Alert settings"** → `/telecaller/manager/alerts` (`TelecallerAlertSettingsPanel`).
- **Overseas Admin has no access** (403 "Telecaller manager role required"). Super Admin has no sidebar link: it reaches the page only by typed URL. **VERIFICATION REQUIRED**.
- There is no other Super Admin / Overseas Admin "telecaller settings" page in code.

### 5.2 Lead intake sources (`svc/lead_intake.py`, tel-005)
| Source path | Entry point | Who configures / owns it | Distribution |
|---|---|---|---|
| Public website enquiry | `POST /public/enquiries` (`api/public.py:300-313`, public, no auth) from `EnquiryForm` on **`/overseas/contact`** (heading "Profile enquiry"; fields **"Full name \*"**, **"Email \*"**, **"Phone"**, **"Destination / study interest \*"**, **"How can we help? \*"**; button **"Book counseling callback"**; success **"Thank you. Your enquiry has been received and the relevant EduSphere team will follow up."**; failure "We could not submit your enquiry. Please review the fields and try again.") and on `/it/contact` and `/it/corporate-hiring` | Hard-coded `source:"website"` (`web/components/EnquiryForm.tsx:5`). There is no admin configuration screen | Known person (same normalised mobile or email on **any** lead, closed ones too): the enquiry **attaches** to their newest lead as a `LeadEnquiry`, and no new lead or CRM sync is created. Otherwise a new lead is created and passed through `lead_distribution.on_intake` (rules, else the unassigned queue) (`svc/lead_intake.py:159-175`). The reply is always `{status:"new", crm_sync_status:"pending", lead_code}`, so it never reveals a match |
| Manual lead | `POST /telecaller/leads` (telecaller or manager, `api/telecaller.py:138-148`) | Product, campaign and source chosen per lead. Campaign source and product must match (422 "This campaign belongs to another lead source" / "This campaign is for another product") | A duplicate gives 409 with the §18 panel. A manager's lead is distributed (I6) |
| CSV import | tel-006 `/telecaller/manager/imports` | Manager (campaign gives the source) | `import_row` → `on_intake` (`svc/lead_intake.py:178-197`) |
| BDM lead | `api/bdm_leads.py:45-52` | BDM | `on_intake` |
| Sources list | 13 fixed values `TEL_SOURCES` (`apps/api/app/tel_sources.py:4`): Instagram, Facebook, Google, Website, WhatsApp, Walk-in, College, School, Agent, Referral, Exhibition/Event, BDM, Other (`web/lib/telecallerCatalogue.ts:22-25`) | Code constant. Not admin-configurable | — |

- Who configures where intake lands: managers, through **Distribution rules**, **Products** and **Campaigns**, covered in the manager discovery file.
- Super Admin and Overseas Admin have **no** intake configuration UI.

---

## (a) Proposed feature rows

| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-TEL-AUTH-001 | Choose your portal (Telecaller sign-in chooser) | `/telecaller/sign-in` | telecaller, telecaller_manager | none (links) |
| DOC-TEL-AUTH-002 | Sign in as an Overseas telecaller | `/overseas/login` | telecaller | `POST /auth/login` |
| DOC-TEL-AUTH-003 | Sign in as a Telecaller Manager | `/admin/login` | telecaller_manager | `POST /auth/login` |
| DOC-TEL-AUTH-004 | Set your password from the welcome email | `/overseas/reset-password`, `/admin/reset-password` | telecaller, telecaller_manager | `POST /auth/reset-password` |
| DOC-TEL-AUTH-005 | Forgot / reset your password | `/overseas/forgot-password`, `/admin/forgot-password` | telecaller, telecaller_manager | `POST /auth/forgot-password`, `POST /auth/reset-password` |
| DOC-TEL-AUTH-006 | Change your password | `/account/password` | telecaller, telecaller_manager | `POST /auth/change-password` |
| DOC-TEL-AUTH-007 | View your profile and update your mobile | `/telecaller/profile`, `/account/profile` | telecaller | `GET /telecaller/me`, `PATCH /telecaller/profile`, `PATCH /auth/me` |
| DOC-TEL-AUTH-008 | Sign out and session rules (ended sessions, wrong portal) | sidebar | telecaller, telecaller_manager | `POST /auth/logout` |
| DOC-TEL-ADM-001 | Create a Telecaller Manager | `/admin/users` | super_admin | `POST /admin/users` |
| DOC-TEL-ADM-002 | Create an Overseas telecaller | `/overseas/admin/telecallers`, `/admin/telecallers` | overseas_admin, super_admin | `POST /admin/users`, `GET /admin/telecaller-managers` |
| DOC-TEL-ADM-003 | Find and edit a telecaller (Employee ID, manager, mobile) | same | overseas_admin, super_admin | `GET /admin/telecallers`, `PATCH /admin/users/{id}` |
| DOC-TEL-ADM-004 | Re-send a set-password link | `/admin/users`, `/overseas/admin/users` | overseas_admin, super_admin | `POST /admin/users/{id}/welcome-links` |
| DOC-TEL-ADM-005 | Deactivate a telecaller and hand over open leads | Telecallers page | overseas_admin, super_admin | `GET …/open-work`, `POST /admin/telecallers/{id}/deactivate` |
| DOC-TEL-ADM-006 | Reassign open work of an inactive telecaller | Telecallers page | overseas_admin, super_admin | `POST /admin/telecallers/{id}/handover` |
| DOC-TEL-ADM-007 | Move a telecaller to the other team | Telecallers page | super_admin | `POST /admin/telecallers/{id}/move-team` |
| DOC-TEL-ADM-008 | Reactivate a telecaller | Telecallers page / Users | overseas_admin, super_admin | `PATCH /admin/users/{id}` `{active:true}` |
| DOC-TEL-ADM-009 | Deactivate a Telecaller Manager (with replacement) | `/admin/telecallers` | super_admin | `POST /admin/telecaller-managers/{id}/deactivate` |
| DOC-TEL-ADM-010 | Set team alert thresholds | `/telecaller/manager/alerts` | telecaller_manager (super_admin by URL) | `GET /telecaller/settings`, `PUT /telecaller/settings/{team}` |
| DOC-TEL-CNS-001 | See leads handed to you | `/overseas/counselor/leads` | counselor | `GET /counselor/leads` |
| DOC-TEL-CNS-002 | Open a handed-over lead (details, milestones, activity) | `/overseas/counselor/leads/[id]` | counselor | `GET /counselor/leads/{id}`, `GET …/timeline` |
| DOC-TEL-CNS-003 | Link / unlink the student account | same | counselor | `GET …/link-suggestions`, `POST`/`DELETE …/student-link` |
| DOC-TEL-CNS-004 | Return a lead to the telecaller | same | counselor | `POST /counselor/leads/{id}/return` |
| DOC-TEL-CNS-005 | Conversion when the student enrols (and admin unlink) | counselor detail, `/overseas/admin/leads` | counselor, overseas_admin | `POST`/`DELETE /admin/leads/{id}/conversion` |
| DOC-TEL-CNS-006 | BDM side of meeting requests (touchpoint note) | `/bdm/meeting-requests` | bdm, bdm_manager | `/bdm/meeting-requests*` |
| DOC-TEL-INTAKE-001 | Website enquiry becomes (or joins) a lead | `/overseas/contact` | public visitor | `POST /public/enquiries` |
| DOC-TEL-INTAKE-002 | Lead sources reference (13 sources, where each comes from) | reference page | all | n/a |

## (b) Test data needed before screenshots

| # | Data | Why |
|---|---|---|
| 1 | Super Admin account (existing demo `superadmin@edusphere.local`) and an Overseas Admin (`overseasadmin@edusphere.local`) | Provisioning and lifecycle screens |
| 2 | At least **two active telecaller managers** (A with reports, B empty) | Create form picker, manager-deactivation with replacement |
| 3 | At least **three Overseas telecallers** (T1, T2 active under A; T3 inactive) plus one IT telecaller | List (Team column, Inactive badge), same-team picker, Move team, Reassign open work |
| 4 | One telecaller still **pending setup** and one with **link expired** | Users page "Awaiting setup" / "Link expired" + Re-send |
| 5 | T1 owning open leads with an open follow-up and an open appointment, plus a closed and a converted lead | The "Open work: …" sentence, and evidence that finished leads stay |
| 6 | A distribution rule naming T1 | Shows rule removal (`rules_removed`) |
| 7 | Two active Overseas counselors and one active `overseas_student` whose email or mobile matches a lead | Handover select, suggested match, link |
| 8 | A lead handed to counselor C1 at Follow-up, and one linked at Application/Enrollment whose student has an application to be set to `enrolled` | Return, link/unlink, the conversion flip |
| 9 | Working SMTP (Mailpit), or accept the amber "email was not delivered" warning | Welcome-link feedback text |
| 10 | Email webhook capture for forgot-password, or document only the confirmation text | §1.8 finding |
| 11 | A BDM with a pending meeting request from a telecaller | BDM touchpoint screenshot |

## (c) Open questions

| # | Question | Evidence |
|---|---|---|
| Q1 | The forgot-password email is webhook-only, with no URL and no SMTP. Which page does a telecaller's reset email open, and does it arrive at all in prod? | `api/auth.py:369-389`; `PRODUCT_DECISION_REGISTER.md:2135` |
| Q2 | A counselor gets no notification when a lead is handed over. Is that intended, or should the guide tell telecallers to tell the counselor? | `svc/lead_handover.py:40-54` |
| Q3 | Should the Telecallers page offer "Re-send link"? Today the admin must go to Users. | `AdminTelecallerRow.tsx` (none), `AdminUserManagementPanel.tsx:257-268` |
| Q4 | Can an Overseas Admin intentionally not move teams? `canMoveTeams` requires both teams, so only Super Admin can. | `web/lib/telecaller.ts:56`, `svc/telecaller_lifecycle.py:255-258` |
| Q5 | Telecaller manager reactivation has no control on the managers card. Is reactivating from Users the intended path? | `AdminTelecallerManagersCard.tsx` |
| Q6 | A telecaller manager on `/account/password` gets no "Forgot your current password?" link and no admin sign-in link when the session expires. Accept or fix? | `web/app/account/password/page.tsx:62`, `ChangePasswordForm.tsx:174-178` |
| Q7 | A telecaller manager can edit their own name on `/account/profile` (not phone-only). Intended? | `api/auth.py:35` |
| Q8 | Alert settings are editable by any manager for both teams, and Super Admin has no sidebar link. Document as is? | `api/telecaller_settings.py:1-5` |
| Q9 | "Telecaller profile not set up" card shows a "Go to your dashboard" button that loops. Cosmetic fix or document? | `AccessUnavailable.tsx:19, 32` |
| Q10 | Sign out from the sidebar lands on `/` (corporate home), not `/telecaller/sign-in`. Confirm the wording for the guide. | `PortalShell.tsx:17` |
| Q11 | Prod access/refresh token lifetimes, and whether the web silently refreshes (affects "how long you stay signed in"). | `core/config.py:11-12` |
