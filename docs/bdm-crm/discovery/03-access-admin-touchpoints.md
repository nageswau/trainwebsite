# Overseas BDM CRM: account access, admin provisioning and lifecycle, travel approvals, touchpoints (source discovery)

> **Evidence appendix** for `docs/bdm-crm/documentation-analysis.md`. This is raw, read-only source discovery from master planning session S1 (2026-10-17, code `main` @ `6fee294d`), with field-level detail for the module sessions. Nothing here was checked in a browser. Where this file and the browser disagree, the browser wins: annotate this file, do not silently trust it.

Code baseline: `main` @ 6fee294d (worktree `bdm-docs`). Read-only discovery.
Path prefixes: `api/` = `apps/api/app/api/`, `svc/` = `apps/api/app/services/`, `web/` = `apps/web/`. Every API path below is mounted under `/api/v1` (`apps/api/app/main.py:166`).
Legend: **VERIFICATION REQUIRED** means the behaviour was not run in a browser and code alone did not settle it.
Decision IDs (DEC-SCOPE-055 bdm-001, -063 bdm-010, -082 bdm-025, -072 bdm-017, -085 bdm-018, -107 bdm-019, -098 tel-019, -161 upc-030, -019 ENH-003, -021 ENH-006) are labels taken from code comments. The code is the authority.

Scope: only the Overseas BDM types (`agent`, `school`) and the `bdm_manager` are in scope. College BDMs (IT division, `/it/login`, `/it/admin/bdms`) use the same code and appear only where the rules differ.

---

## 0. Shared mechanics

### 0.1 Roles involved

| Role | Division | Signs in at | Landing page (`ROLE_DASHBOARD_PATH`, `web/lib/navigation.ts:45-47`) | Sidebar |
|---|---|---|---|---|
| `bdm`, type `agent` or `school` | `overseas` (forced from the type, `svc/bdm.py:20`) | `/overseas/login` | `/bdm/my-day` | `BDM_NAV` (`navigation.ts:72-80`): My Day, Calendar, Organizations, Pipeline, MoUs, Appointments, Follow-ups, Requests, Activities, Daily report, Travel, Notifications (unread badge), Profile |
| `bdm`, type `college` (out of scope) | `it` | `/it/login` | `/bdm/my-day` | same |
| `bdm_manager` | `global` | `/admin/login` | `/bdm/manager/dashboard` | `BDM_MANAGER_NAV` (`navigation.ts:82-95`): Dashboard, Performance, Master view, Team, Organizations, Pipeline, MoUs, Appointments, Requests, Follow-ups, Calendar, Activities, Daily reports, Targets, Approvals, Notifications |
| `overseas_admin` | `overseas` | `/overseas/login` | `/overseas/admin/dashboard` | Overseas admin nav has **"BDMs"** → `/overseas/admin/bdms` (`navigation.ts:268`). No travel-approval, BDM dashboard or organization entry |
| `super_admin` | `global` | `/admin/login` (login skips the division check) | `/admin` | `SUPER_ADMIN_NAV` (`navigation.ts:297`): **"BDMs"** → `/admin/bdms`, **"BDM Travel Approvals"** → `/admin/bdm-travel-approvals`, **"BDM Dashboard"** → `/bdm/manager/dashboard`, **"BDM Performance"**, **"BDM Master View"**, **"Management BDM figures"** → `/management/bdm` |
| `it_admin` (out of scope) | `it` | `/it/login` | | **"BDMs"** → `/it/admin/bdms`, College BDMs only |

Server gates (`svc/bdm.py`):

| Gate | Rule | Refusal |
|---|---|---|
| `bdm_context` (`:138-145`) | caller role is `bdm` **and** has a `bdm_profiles` row | 403 "BDM role required" / 403 "BDM profile not set up — contact your administrator" |
| `require_manager` (`:148-150`) | role `bdm_manager` or `super_admin` | 403 "BDM manager role required" |
| `team_filter` (`:153-155`) | a manager sees exactly the BDMs whose `reporting_manager_user_id` is them; `super_admin` sees all | |
| `CREATOR_TYPES` (`:21-25`) | `super_admin`: agent, school, college; `it_admin`: college; `overseas_admin`: agent, school | 403 "Your role cannot manage {type} BDMs" (`:35`) |

### 0.2 Common refusal card
BDM pages catch API errors with `accessUnavailable(e, loginHref)` (`web/components/AccessUnavailable.tsx`). Heading **"Access unavailable"**, then the API `detail`. "BDM profile not set up — contact your administrator" is in `BDM_ACCOUNT_STATE_REASONS` (`AccessUnavailable.tsx:19`), so it is shown as an account-state message (no dashboard loop, unlike the telecaller variant).

---

## 1. Account access (AUTH)

### 1.1 Signed-out redirects (middleware)
`web/middleware.ts`:
- Public paths: `/admin/login`, `/admin/forgot-password`, `/admin/reset-password`, `/bdm/sign-in`, `/telecaller/sign-in` (`:2`).
- `/bdm` and everything under it is protected (`:11`). The check is only "is the `edusphere_access` cookie present"; roles are checked per page through the API.

| Requested path (no cookie) | Redirect target | Line |
|---|---|---|
| `/bdm/manager` or `/bdm/manager/...` | `/admin/login?next=<path+query>` | `:17` |
| any other `/bdm...` | `/bdm/sign-in?next=<path+query>` | `:18` |
| `/overseas/admin/...` | `/overseas/login?next=...` | `:20-21` |
| `/admin...` | `/admin/login?next=...` | `:17` |

Index redirects: `/bdm` → `/bdm/my-day` (`web/app/bdm/page.tsx:4-6`); `/bdm/manager` → `/bdm/manager/dashboard` (`web/app/bdm/manager/page.tsx`).

### 1.2 `/bdm/sign-in` (chooser)
`web/app/bdm/sign-in/page.tsx:8-25`. A static chooser, no form.

| Element | Literal |
|---|---|
| Back link | "← Corporate website" → `/` |
| Heading | "BDM sign-in" |
| Intro | "Choose the portal for your module. BDM Managers sign in at **Administration**." (link → `/admin/login`) |
| Button 1 | "College BDM" → `/it/login` |
| Button 2 | "Agent / School BDM" → `/overseas/login` |

`next` is forwarded to all three links only when it is a same-origin path (`safeNextPath`, `:9-10`).

### 1.3 Login pages and the login API
| Page | Heading / intro literals | Form |
|---|---|---|
| `/overseas/login` (`web/app/overseas/login/page.tsx:12`) | eyebrow "Overseas Education Portal"; h2 "Overseas Education Portal"; "Sign in with your authorised overseas education account." The page copy names "students, counselors, university representatives, agents, and administrators" — **not BDMs** (cosmetic) | `LoginForm division="overseas"` |
| `/admin/login` (`web/app/admin/login/page.tsx:13`) | eyebrow "Central Administration"; h2 "Administration sign-in"; "For Super Admins, Partners, Accountants, Partnership Heads and BDM, Telecaller and Placement Managers." | `LoginForm division="global"` |

`LoginForm` (`web/components/LoginForm.tsx`): labels **"Email"**, **"Password"**; button **"Sign in securely"** / "Signing in…"; link **"Forgot your password?"** → `/{overseas|admin}/forgot-password` (`:57`). After success it follows a same-origin `next`, otherwise `dashboardPathFor(user)` (`:39-40`).

`POST /auth/login` (`api/auth.py:106-121`):
| Case | Response |
|---|---|
| wrong email/password or inactive account | 401 "Invalid credentials" |
| password correct, wrong portal (division ≠ user's) | 403 "Use the correct EduSphere portal for this account: sign in at /overseas/login" (or `/it/login`, `/admin/login`; `PORTAL_SIGN_IN`, `:36`, `:113`). So an Agent BDM on `/admin/login` is told `/overseas/login`; a BDM manager on `/overseas/login` is told `/admin/login` |
| success | sets `edusphere_access` + `edusphere_refresh` httpOnly cookies, audit `auth.login` |

### 1.4 Welcome / set-password link (first sign-in)
`svc/provisioning.py`. An admin never sets a password (a supplied `password` is 422 "A password cannot be supplied; the user sets their own via the emailed set-password link", `api/admin.py:116-122`).

| Item | Value | Source |
|---|---|---|
| Lifetime | 72 hours, single-use, hashed at rest | `provisioning.py:37`, `:102-114` |
| URL for an Agent/School BDM | `{FRONTEND_URL}/overseas/reset-password?token=…` (division overseas) | `:71-75` |
| URL for a `bdm_manager` | `{FRONTEND_URL}/admin/reset-password?token=…` (`ADMIN_PORTAL_ROLES`, `:68`) | `:74` |
| Email subject | "Welcome to EduSphere -- set your password" | `svc/mailer.py:309` |
| Role wording in the email | "{inviter} has created your EduSphere account as {role_label}." with `role_label = role.replace("_"," ").title()` → **"Bdm"** / **"Bdm Manager"** (no entry in `ROLE_LABELS`, `mailer.py:26`, `:304`). Product finding P1 | `mailer.py:283`, `:304` |
| Admin feedback after create | sent: "BDM created. A set-password link was emailed and is valid for 72 hours." / not sent: "BDM created. The email was not delivered (email is not configured on this server \| the email could not be sent). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page." | `web/lib/welcomeLink.ts:11-20` |
| Re-send | No Re-send on the BDMs page. Re-send lives on the Users page (`AdminUserManagementPanel`, "Re-send link", `web/components/AdminUserManagementPanel.tsx:265-268`) and the dashboard expired-links panel (`AdminExpiredLinksPanel.tsx:93-96`). Overseas Admin gets the Users panel on `/overseas/admin/users` (`WorkflowPanel.tsx:458`) | |
| Re-send API | `POST /admin/users/{id}/welcome-links` (`api/admin.py:756-780`): 409 "This account has no pending invitation (its password is already set)"; 409 "Reactivate this account before re-sending its link"; 429 "A link was just sent; wait {n} seconds before re-sending" (60 s cooldown after the second link, `provisioning.py:39`, `:228-238`); 403 "Cannot manage another division" (an Overseas Admin cannot re-send to a `global` BDM manager) | |
| Reset page | `/overseas/reset-password` and `/admin/reset-password`: h2 "Choose a new password", hint "Use at least 10 characters." (`ResetPasswordForm.tsx:69-70`) | |
| After reset | API returns `login_portal: "admin"` for a BDM manager, `null` otherwise (`api/auth.py:444`); the form redirects to `/admin/login` or the page's own `/{division}/login` (`ResetPasswordForm.tsx:54`) | |
| Reset refusals | 422 "Password must be at least 10 characters" / "Password must be at most 128 characters"; 400 "Reset token is invalid or expired" (unknown, used, expired, superseded, or welcome link for an inactive account) (`auth.py:392-431`) | |
| Side effect | welcome link use sets `email_verified = true` (`auth.py:435-437`) | |
| Revocation | any change of `active` revokes open welcome links (`api/admin.py:734-739`; `svc/bdm_lifecycle.py:122-125`) | |

### 1.5 Forgot password, change password, sign out, sessions
| Feature | Route / API | Literals and rules |
|---|---|---|
| Forgot (BDM) | `/overseas/forgot-password` → `POST /auth/forgot-password` (`auth.py:369-389`) | h2 "Reset your password"; "Enter the email on your Overseas Education account and we'll send reset instructions." Always 202 `{accepted: true}` (no enumeration). Link lifetime 30 minutes; also an in-app notification "Password reset requested" / "Use the link we emailed you to reset your password. It expires in 30 minutes." |
| Forgot (BDM manager) | `/admin/forgot-password` | "Enter the email on your administration, BDM Manager, Telecaller Manager, Placement Manager, Partnership Head, Partner or Accountant account and we'll send reset instructions." |
| Forgot delivery | `send_notification("email", template "password_reset")` only — not the SMTP mailer the welcome link uses. Whether a reset email reaches an SMTP-only deployment, and which portal URL it carries, is **VERIFICATION REQUIRED** (`auth.py:383`) |
| Change password | `/account/password` (header button **"Change password"**, `PortalShell.tsx:17`) → `POST /auth/change-password` (`auth.py:447-470`) | 422 "New password must be different from the current password"; 400 "Incorrect current password"; 429 "Too many incorrect attempts; try again in {n} seconds" (5 failures / 15 min, DEC-SCOPE-021) |
| Sign out | header button **"Sign out"** → `POST /auth/logout` (`auth.py:307-311`) clears both cookies; the shell then goes to `/` (`PortalShell.tsx:17`, not the BDM chooser) |
| Session after deactivation | `get_current_user` only loads active users (`api/deps.py:54`), so a deactivated BDM's next request is refused. The BDM deactivation path does **not** bump `session_version` (contrast telecaller/recruiter lifecycle). Effect is the same for API calls; exact browser behaviour on the next page load is **VERIFICATION REQUIRED** |

### 1.6 Profile: `/bdm/profile` versus the generic `/account/profile`
| Page | What it shows | Edit? |
|---|---|---|
| `/bdm/profile` (`web/app/bdm/profile/page.tsx`) — sidebar "Profile" | eyebrow "Profile", h2 "My profile", "Your details as recorded by your administrator. Contact them to change anything." Card (`BdmProfileCard.tsx:7-18`): Name, Employee ID, Module, Designation, Department, Territory, Mobile, Email, Reporting manager (suffix " (inactive)"), Status (Active / Inactive). API `GET /bdm/me` (`api/bdm.py:62-69`) | read-only |
| `/account/profile` — header button **"My profile"** (`PortalShell.tsx:17`) | generic `ProfileForm`: "Full name", "Phone" | **editable**. `PATCH /auth/me` (`auth.py:335-366`) restricts only `PHONE_ONLY_ROLES = {telecaller, partnership_manager}` (`auth.py:35`); `bdm` and `bdm_manager` are not in it, and the form's `nameLocked` is only for those two roles (`web/app/account/profile/page.tsx:70`) |

**Product finding P2 (name-edit gap):** a BDM (and a BDM manager) can rename themselves and change their phone on `/account/profile`, while `/bdm/profile` says "Contact them to change anything" and the admin row editor owns those same fields. The change is audited as `profile.update` but not as a BDM profile snapshot. Decide whether BDMs join `PHONE_ONLY_ROLES`.

---

## 2. Admin provisioning and lifecycle (ADM)

### 2.1 Pages
All three routes render one component, `web/components/AdminBdmPage.tsx`:

| Route | Allowed (page check) | Types it can manage (API) | Login on 401 |
|---|---|---|---|
| `/overseas/admin/bdms` (`web/app/overseas/admin/bdms/page.tsx`) | `overseas_admin`, `super_admin` | agent, school | `/overseas/login` |
| `/admin/bdms` (`web/app/admin/bdms/page.tsx`) | `super_admin` | agent, school, college | `/admin/login` |
| `/it/admin/bdms` (out of scope) | `it_admin`, `super_admin` | college | `/it/login` |

Other roles get the denied card "{Overseas Administrator \| Super Administrator \| IT Administrator} role required" (`AdminBdmPage.tsx:20`). A Super Admin keeps the Super Admin nav and label on any of the three (`:21-24`).

Header literals (`AdminBdmPage.tsx:28-30`): eyebrow "Workspace", h2 "BDMs", "Create Business Development Managers, set their reporting manager and keep their profiles current. Each new BDM gets an emailed set-password link."

### 2.2 Create BDM form (`web/components/AdminBdmCreateForm.tsx`)
Card heading **"Create BDM"**. Posts `POST /admin/users` (`api/admin.py:523-661`) with `role: "bdm"` and a nested `bdm_profile`.

| Label (literal) | Field | Rules (client / server) |
|---|---|---|
| Full name (required) | `full_name` | max 160 |
| Email (required) | `email` | type email, max 255; 409 "Email already exists" |
| Mobile | `phone` | max 40, optional, no server format check |
| Module (required) — a select for Super Admin; for Overseas Admin a select with Agent / School | `bdm_profile.bdm_type` | `agent` / `school` / `college`; 403 "Your role cannot manage {type} BDMs"; if `division` sent and mismatched: 422 "Division must be {overseas} for a {agent} BDM" |
| Employee ID (required) | `bdm_profile.employee_id` | max 40, trimmed, no control chars; unique case-insensitive → 409 "Employee ID already exists" (`svc/bdm.py:92-101`) |
| Designation / Department / Territory | `bdm_profile.*` | each optional, max 120, blank clears |
| Reporting manager (required) | `bdm_profile.reporting_manager_user_id` | server-searched picker (`GET /admin/bdm-managers`, options show the manager's email); 422 "Reporting manager must be an active BDM manager" (`svc/bdm.py:82-89`); bad UUID → "Reporting manager: choose a manager from the list" |
| Button | | "Create BDM" / "Creating…"; disabled until an active manager exists |
| No-manager hint | | "No active BDM manager — a Super Admin must create one first." |
| Managers check failed | | "Unable to load BDM managers." + "Retry loading managers" (`AdminBdmPanel.tsx:90-95`) |

Server-side validation errors become one sentence naming the field (`svc/bdm.py:47-60`), e.g. "Employee ID is required", "Unknown field: x". A non-BDM payload with `bdm_profile` is 422 "Only a BDM has a BDM profile". On success the list filters to the new Employee ID (`AdminBdmPanel.tsx:96`). Audit `user.create` carries the `bdm_profile` snapshot (`api/admin.py:642-643`).

### 2.3 BDM list (`web/components/AdminBdmPanel.tsx`, `AdminBdmRow.tsx`)
`GET /admin/bdms?bdm_type=&active=&q=&limit=&offset=` (`api/bdm.py:91-106`, `ensure_admin` + type scope in SQL). Page size 50 (`web/lib/bdm.ts:29`); search and page live in the URL (`?q=&offset=`).

| Element | Literal |
|---|---|
| Card heading | "BDMs"; jump link "Create BDM" |
| Search | placeholder "Name, email or Employee ID"; buttons "Search", "Clear search" |
| Columns | Name (with email under it), Employee ID, Module, Territory, Manager (badge "No active manager" when the manager is inactive), Status (Active / Inactive), Actions |
| States | "Loading BDMs…"; "Unable to load BDMs." + "Retry"; empty "No BDMs yet. Use the Create BDM form to add the first one." / "No BDMs match “{q}”."; "This page is past the end of the list." + "Go to the first page"; pager "Showing {a}–{b} of {n}", "Previous", "Next" |
| Row actions | "Edit"; "Deactivate" (active rows); "Reactivate" and "Hand over" (inactive rows) |

### 2.4 Edit (row editor, `AdminBdmRow.tsx:152-174`)
`PATCH /admin/users/{id}` (`api/admin.py:663-754`) with `full_name`, `phone` and `bdm_profile`.
- Fields: Full name (required), Mobile, Module shown as "{Agent} (cannot be changed)", Employee ID (required), Designation, Department, Territory, Reporting manager (required, starts on the current manager, labelled " (inactive)" if so). Buttons "Save" / "Saving…", "Cancel"; Escape cancels. Success notice "Saved {name}."
- Rules: type is fixed → 422 "BDM type cannot be changed"; the manager is re-checked only if it changes (so a BDM under an inactive manager stays editable); profile row locked; 403 "Cannot edit another division" when an Overseas Admin targets another division; type scope 403 as on create.
- **Snapshot rule (bdm-001 AC07):** the audit `user.update` gets `bdm_profile_before` / `bdm_profile_after` only when the payload carries `bdm_profile` (`api/admin.py:681-685`, `:744-745`). The BDMs page always sends it; a Users-page edit of name/phone/active only does not snapshot.

### 2.5 Deactivate, hand over, reactivate (bdm-025)
UI: `web/components/AdminBdmHandover.tsx`. API: `api/bdm_lifecycle.py`, rules `svc/bdm_lifecycle.py`.

| Step | API | Literals / rules |
|---|---|---|
| Preview | `GET /admin/bdms/{id}/portfolio` (`bdm_lifecycle.py:28-32`) | "Loading open work…"; "Open work: {n} organizations, {n} appointments and {n} follow-ups/tasks." or "{name} has no open work to hand over."; "{n} trips not yet started will be cancelled."; failure "Unable to load {name}'s open work." + "Retry" |
| Choice | | legend "Who takes over their open work?"; radios "Hand over to another BDM" / "Keep with {name} for now (hand over later)"; picker "Hand over to" (active BDMs of the same module, shown "{Employee ID} · {email}"); note "Their history stays with them; they can no longer sign in." |
| Confirm | `POST /admin/bdms/{id}/deactivate` `{mode: "reassign", reassign_to}` or `{mode: "leave"}` (`:35-57`) | buttons "Confirm deactivate" / "Deactivating…", "Keep active". Notice "Deactivated {name}. {counts} handed over to {target}." / "… Their open work stays with them until you hand it over." + " {n} not-started trips were cancelled." |
| Later handover | `POST /admin/bdms/{id}/handover` `{reassign_to}` (`:60-76`) | button "Hand over" / "Handing over…"; notice "Handed over {counts} from {name} to {target}." |
| Reactivate | `PATCH /admin/users/{id}` `{active: true}` | notice "Reactivated {name}."; restores sign-in only, never the old portfolio; revokes old welcome links |

What moves (`svc/bdm_lifecycle.py:38-44`): non-archived organizations, open future appointments (their trip link is cleared), open tasks. Not-started trips (`travel_status = planned`, any approval state) are cancelled with reason "BDM deactivated" (`:46-49`, `:99-105`). Each moved item gets a `bdm_assignment_history` row. Target notice (in-app + email): "Work handed over to you" / "{counts} from {name} are now yours." → `/bdm/organizations` (`:112-119`).

Refusals: 404 "BDM not found"; 409 "This BDM is already inactive"; 409 "Deactivate this BDM first"; 409 "No open work to hand over"; 422 "Choose an active BDM of the same module". A plain `PATCH /admin/users {active:false}` on a BDM (e.g. from the Users page) is 422 "Deactivate a BDM from the BDMs page, choosing who takes over their open work" (`:133-139`).

### 2.6 BDM managers (Super Admin only)
- **Create:** only on the generic Users page (`/admin/users`, "Create user", role `bdm_manager` in the `global` list, `WorkflowPanel.tsx:365-374`). Server: 403 "Only a Super Admin can create BDM managers" (`api/admin.py:542-543`). No profile; set-password link opens `/admin/reset-password`.
- **Card "BDM managers"** on `/admin/bdms` (and on the division pages when the viewer is Super Admin) (`AdminBdmManagersCard.tsx`, `AdminBdmPanel.tsx:148`): intro "A manager who still has BDMs is deactivated together with the manager who takes them over." Columns Manager, BDMs ("{n} BDMs"), Actions "Deactivate". With BDMs: "Move their {n} BDMs to another manager first. Pending travel approvals move with them." + picker "Replacement manager". Without: "They have no BDMs; they can no longer sign in." Buttons "Confirm deactivate" / "Keep active". Empty "No active BDM managers."
- **API:** `POST /admin/bdm-managers/{id}/deactivate` `{reassign_to?}` (`api/bdm_lifecycle.py:79-101`): 403 "Only a Super Administrator can deactivate a BDM manager"; 404 "BDM manager not found"; 409 "This manager is already inactive"; 422 "Choose another active BDM manager". Every BDM reporting to them (active or not) moves; new manager notified "{n} BDMs now report to you" / "Their pending travel approvals are now yours to decide." → `/bdm/manager/team`. A plain Users-page deactivation of a manager with BDMs is 422 "This manager has {n} BDMs. Move them to another manager first (BDMs page → BDM managers)".
- **Reactivating a manager / editing their name:** only through the Users page (no BDM-specific UI). **VERIFICATION REQUIRED** that the Users panel offers reactivate for `bdm_manager`.
- The manager's own team view: `/bdm/manager/team`, h2 "BDMs who report to you" (`GET /bdm/manager/team`, `api/bdm.py:72-88`).

---

## 3. Travel approvals (TAPPR, bdm-010)

| Who decides | Where | Rule (`svc/bdm_travel.py:112-117`, `decider_may`) |
|---|---|---|
| the BDM's **current** reporting manager (resolved at decision time, never stored) | `/bdm/manager/approvals` (h2 "Travel waiting for your approval"; "Every trip needs your approval before it starts. A rejection needs a reason, which the BDM sees.") | `user.id == manager.id` |
| any `super_admin`, **only while that manager is inactive** | `/admin/bdm-travel-approvals` (`web/app/admin/bdm-travel-approvals/page.tsx`) | `role == super_admin and not manager.active` |
| `overseas_admin` | none | no role in travel |

`/admin/bdm-travel-approvals` literals: eyebrow "BDM travel"; h2 "Approvals waiting on an inactive manager"; "When a BDM's reporting manager is inactive, a Super Administrator approves or rejects their trips."; empty "No trips are waiting on an inactive manager."; past-end "This page is past the end of the queue. Go to the first page". Non-super-admin: "Super Administrator role required". Table (`TripTable`, `showBdm`): Trip, Status, BDM, Dates, Route, Estimated, Actual, Mode. Rows open `/bdm/manager/trips/{id}` (Super Admin keeps admin nav there).

| API | Handler | Notes |
|---|---|---|
| `GET /bdm/manager/approvals` | `api/bdm_travel.py:101-104`; filter `svc/bdm_travel.py:324-330` | submitted + still planned; manager: own team; super_admin: only trips whose manager is inactive |
| `POST /bdm/manager/trips/{id}/approve` | `api/bdm_travel.py:140-142` → `_decision` `:130-137` → `svc decide` `:300-321` | |
| `POST /bdm/manager/trips/{id}/reject` `{reason}` | `:145-147` | reason required, multi-line, max 1000 (`schemas.py:3680`, `:3719-3721`) |

States: `approval_status` draft → submitted → approved / rejected (rejected is editable again); `travel_status` planned → in_progress → completed, or cancelled (`svc/bdm_travel.py:37-60`). Decide is allowed only for `submitted` + `planned`.

Decision UI (`web/components/TripDecision.tsx`): buttons "Approve", "Reject"; reject form label "Reason for rejecting", error "Reason is required", buttons "Confirm reject" / "Cancel"; success "Trip approved; the BDM has been told." / "Trip not approved; the BDM has been told why."

Refusals: manager outside scope → 404 "Trip not found"; super_admin while manager active → 403 "The reporting manager is active and decides this trip"; own trip → 403 "You can't decide your own trip"; wrong state → 409 "This trip {is still a draft \| is already approved \| …} and can't be decided".

Notifications (in-app only, `channels=[]`): on submit "Travel approval needed" to the active manager (link `/bdm/manager/approvals`) or to every active super_admin when the manager is inactive (link `/admin/bdm-travel-approvals`) (`api/bdm_travel.py:67-76`, `svc:226-232`); on decision "Trip approved" / "Trip not approved" to the BDM (link `/bdm/travel/{id}`).

---

## 4. Touchpoints (TOUCH)

### 4.1 Telecaller → BDM meeting requests (tel-019)
API `api/bdm_meeting_requests.py`, rules `svc/bdm_meeting_requests.py`.

| Actor | Route | What they can do |
|---|---|---|
| Telecaller | `/telecaller/meeting-requests` (sidebar "BDM requests") | file a request: type College / Agent / School / Corporate meeting (`TYPE_LABEL`, `svc:33`); Agent → agent BDMs, School → school BDMs, Corporate → college BDMs (`models.py:3320`); optional named BDM; organization name, person name, contact phone, optional email, proposed time (future, within a year), mode, optional location, purpose, optional remarks (`schemas.py:6555-6570`) |
| Agent/School BDM | `/bdm/meeting-requests` (sidebar "Requests"): h2 "Meeting requests", "Telecallers ask for {agent} meetings here. Open a request to accept it into an appointment or decline it." | sees the pool of their type plus requests named for them (`svc:88-99`); detail `/bdm/meeting-requests/{id}`: **"Accept and book"** ("Choose one of your organizations and a contact; the appointment is booked when you accept." + " The proposed time has passed — choose a new time." when past) or **"Decline"** (label "Reason for declining", note "The telecaller sees your reason. A declined request can't be reopened.", button "Decline request"; error "Enter the reason for declining.") |
| BDM manager | `/bdm/manager/meeting-requests`: "Read-only: requests for your team's BDMs and the open requests any BDM of the module can take. Times are India time (IST)." | read-only |
| super_admin | API reads all | no UI found beyond the manager pages. **VERIFICATION REQUIRED** |

APIs: `GET /bdm/meeting-requests?status=` (`:68-74`), `GET /bdm/meeting-requests/{id}` (`:77-79`), `POST …/{id}/accept` with a bdm-006 appointment body (`:90-104`, books through `book_appointment`; the BDM must pick one of **their own existing organizations** — accept never creates an organization), `POST …/{id}/decline` `{reason}` (`:107-115`). Statuses pending / accepted / declined. Refusals: 403 "BDM role required"; 404 "Meeting request not found"; 409 "This request is already {accepted}". List columns: Request, Proposed (IST), Organization, Status, Requested by. Status filter empty: "No meeting requests yet." / "No {pending} requests."
No notification is sent to BDMs when a request is filed (no `_notify_user` in the module). Product finding P4.

### 4.2 BDM → Agent CRM (bdm-019 agent onboarding)
- BDM side: on an Agent organization at stage **"Agreement Signed"** (`bdm_stages.py`, `svc/bdm_onboarding.py:56-61`) the assigned BDM (or super_admin) sees card "Agent onboarding" with **"Request onboarding"** / "Request again"; form "Note for Overseas Admin (optional)", buttons "Send request" / "Cancel" (`web/components/BdmOrganizationOnboarding.tsx`). Status lines: "Requested on {date}. Waiting for Overseas Admin to link the agent organization." / "Not approved on {date}. Reason: {reason}" / "Linked to {agency} (code {prefix}). Status: {status}." / "Available once the agreement is signed."
- API: `POST /bdm/organizations/{org_id}/onboarding-request` (`api/bdm_onboarding.py:35-48`); notifies every Overseas Admin "Agent onboarding requested" / "{code} · {name} is ready for onboarding." → `/overseas/admin/agents`.
- Admin side: `/overseas/admin/agents` (Super Admin nav "Agent Approvals") shows **"Agent onboarding requests"** (`AdminSchoolOnboardingRequests.tsx:17`): "Link agent organization" (field "Agent code", button "Link agent") or "Reject request" (field "Reason (sent to the BDM)"). APIs `GET /overseas-admin/bdm-onboarding-requests?kind=agent`, `POST …/{id}/link-agent` (`:99-109`), `POST …/{id}/reject` (`:75-84`). Overseas Admin / super_admin only (403 "Overseas Admin role required").
- **The BDM does not create the Agent organization.** The admin links an existing `AgentOrg` by code; approving that agency remains AGN-001. Outcome notice to the BDM: "Agent onboarded" / "{code} · {name} is now linked to the agent organization {agency} ({prefix})." or "Agent onboarding not approved". After linking, stages Agent Onboarding → Active Agent read live from the agency (`bdm_stages.py` LIVE steps).
- Refusals: "The agreement must be signed to request onboarding", "This organization already has an onboarding request waiting", "This organization is already linked to an agent organization", "No agent organization has that code", "This agent organization is already linked to another organization", "This request was already resolved".

### 4.3 BDM → School CRM (bdm-018 school onboarding)
- BDM side: same card "School onboarding", available once the current MoU reads **Signed or Active** ("Available once the MoU is Signed or Active."); pending line "Waiting for Overseas Admin to create or link the School."; done "Onboarded as {school} (School ID {code})."
- Admin side: `/overseas/admin/schools` **"School onboarding requests"**: "Use for new school" (prefills the School create form; `POST /overseas-admin/schools` with `bdm_onboarding_request_id`, `api/admin.py:1639-1665`), "Link existing school" (field "School ID", button "Link school", `POST …/{id}/link`), or reject. Notice to the BDM "School onboarded" / "{code} · {name} is now onboarded (School ID {code})."
- School record then shows **"Linked BDM"**: "{name} · {org code}" or "Not linked to a BDM organization"; legacy `edusphere_bdm` text read-only (`AdminSchoolEditPanel.tsx:17-23`, `:219`; `api/admin.py:207-213`).
- BDM-side read of the linked school's student development counts: bdm-020 (`api/bdm_school_activity.py:30`), aggregates only.

### 4.4 BDM leads → admin leads (bdm-017)
`POST /bdm/organizations/{org_id}/leads` (`api/bdm_leads.py:34`) by the assigned BDM creates an `enquiries` row queued for the CRM like a website enquiry. Overseas Admin manages them on `/overseas/admin/leads` (`WorkflowPanel.tsx:460-462`); each lead shows "{org code} · {org name}" or "Website" and is filterable by organization (`AdminLeadManagementPanel.tsx:94`, `:189`; `GET /admin/leads?bdm_organization_id=`, `api/admin.py:423-436`).

### 4.5 Other readers of BDM data
| Reader | Route | Who | Source |
|---|---|---|---|
| Management BDM dashboards | `/management/bdm` (h2 "BDM dashboards", tabs per BDM type) → `GET /management/bdm?type=&from=&to=` | `partner`, `super_admin` (`OPERATIONAL_ROLES`, `svc/management_access.py:10`); accountants and Overseas Admin refused | `api/management.py:187-199`, `web/app/management/bdm/page.tsx` |
| BDM manager dashboards | `/bdm/manager/dashboard`, `/performance`, `/hierarchy` | `bdm_manager` (team), `super_admin` (all) | covered by module discovery |
| University link | `/bdm/universities/{id}` | a BDM whose university organization links to University Master (upc-030) | `web/app/bdm/universities/[id]/page.tsx:11-12` |
| Overseas Admin | none for organizations | the onboarding docstring states the admin "never reads a BDM organization except through a request" (`api/bdm_onboarding.py:3-4`) | |

---

## 5. Reference data (REF)

No admin-configurable BDM settings or catalogue pages were found. All lists are code constants:

| List | Values (labels) | Source |
|---|---|---|
| Organization types `BDM_ORG_TYPES` | College, University, Agent, School, Corporate, Training Institute, Other | `models.py:2935`, `web/lib/bdmOrganizations.ts:22` |
| Contact roles `BDM_CONTACT_ROLES` | Principal, Dean, HOD, Placement Officer, Counselor, Management, Owner, Other (suggested: agent → Owner; school → Principal, Management, Counselor) | `models.py:2936`, `bdmOrganizations.ts:24-27`, `:136` |
| Sources | referral, website, event, cold_call, walk_in, other | `models.py:2939` |
| School boards / types | CBSE, ICSE, State, IB, Other / private, government, aided, international, other | `models.py:2940-2941` |
| Agent pipeline | Agent Prospect, Contacted, Meeting Scheduled, Meeting Completed, Interested, Proposal / Agreement, Agreement Signed (manual); Agent Onboarding, Master Login Created, Staff Logins Created, Active Agent (live); Students, Applications, Enrollments (volume) | `apps/api/app/bdm_stages.py` |
| School pipeline | School Prospect, Contacted, Meeting, Presentation, Proposal, Negotiation, MoU, Signed (manual); School Onboarding, Teachers / Parents / Students Created, Career Guidance, Psychometric, Student Profile Building, University Planning (live) | `bdm_stages.py` |
| Appointment statuses | scheduled, confirmed, rescheduled, completed, cancelled, no_show | `models.py:3218` |
| Meeting request types | College / Agent / School / Corporate meeting | `svc/bdm_meeting_requests.py:33` |

Which organization types an Agent or School BDM may create is not settled here (see organizations discovery). **VERIFICATION REQUIRED**

---

## (a) Proposed feature rows

| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-BDM-AUTH-001 | Choose your BDM portal and sign in | `/bdm/sign-in`, `/overseas/login` | bdm | `POST /auth/login` |
| DOC-BDM-AUTH-002 | BDM Manager sign-in | `/admin/login` | bdm_manager | `POST /auth/login` |
| DOC-BDM-AUTH-003 | Set your password from the welcome email | `/overseas/reset-password`, `/admin/reset-password` | bdm, bdm_manager | `POST /auth/reset-password` |
| DOC-BDM-AUTH-004 | Forgot / reset password | `/overseas/forgot-password`, `/admin/forgot-password` | bdm, bdm_manager | `POST /auth/forgot-password`, `POST /auth/reset-password` |
| DOC-BDM-AUTH-005 | Change password and sign out | `/account/password`, header | bdm, bdm_manager | `POST /auth/change-password`, `POST /auth/logout` |
| DOC-BDM-AUTH-006 | View my BDM profile | `/bdm/profile` | bdm | `GET /bdm/me` |
| DOC-BDM-AUTH-007 | Generic account profile (name/phone) — document with P2 caveat | `/account/profile` | bdm, bdm_manager | `PATCH /auth/me` |
| DOC-BDM-ADM-001 | Create an Agent or School BDM | `/overseas/admin/bdms`, `/admin/bdms` | overseas_admin, super_admin | `POST /admin/users`, `GET /admin/bdm-managers` |
| DOC-BDM-ADM-002 | Find and edit a BDM | same | overseas_admin, super_admin | `GET /admin/bdms`, `PATCH /admin/users/{id}` |
| DOC-BDM-ADM-003 | Deactivate a BDM with handover | same | overseas_admin, super_admin | `GET /admin/bdms/{id}/portfolio`, `POST /admin/bdms/{id}/deactivate` |
| DOC-BDM-ADM-004 | Hand over an inactive BDM's work / reactivate | same | overseas_admin, super_admin | `POST /admin/bdms/{id}/handover`, `PATCH /admin/users/{id}` |
| DOC-BDM-ADM-005 | Re-send a BDM's set-password link | `/overseas/admin/users`, dashboard | overseas_admin, super_admin | `POST /admin/users/{id}/welcome-links` |
| DOC-BDM-ADM-006 | Create a BDM Manager | `/admin/users` | super_admin | `POST /admin/users` |
| DOC-BDM-ADM-007 | Deactivate a BDM Manager and move the team | `/admin/bdms` (BDM managers card) | super_admin | `POST /admin/bdm-managers/{id}/deactivate` |
| DOC-BDM-TAPPR-001 | Approve or reject travel (manager) | `/bdm/manager/approvals`, `/bdm/manager/trips/{id}` | bdm_manager | `GET /bdm/manager/approvals`, `POST …/approve`, `POST …/reject` |
| DOC-BDM-TAPPR-002 | Fallback approvals when the manager is inactive | `/admin/bdm-travel-approvals` | super_admin | same |
| DOC-BDM-TOUCH-001 | Handle telecaller meeting requests | `/bdm/meeting-requests[/{id}]` | bdm | `GET /bdm/meeting-requests`, `POST …/accept`, `POST …/decline` |
| DOC-BDM-TOUCH-002 | Monitor team meeting requests | `/bdm/manager/meeting-requests` | bdm_manager | `GET /bdm/meeting-requests` |
| DOC-BDM-TOUCH-003 | Request agent onboarding / admin links agency | org detail; `/overseas/admin/agents` | bdm; overseas_admin | `POST /bdm/organizations/{id}/onboarding-request`, `POST /overseas-admin/bdm-onboarding-requests/{id}/link-agent` |
| DOC-BDM-TOUCH-004 | Request school onboarding / admin creates or links school | org detail; `/overseas/admin/schools` | bdm; overseas_admin | `…/onboarding-request`, `POST /overseas-admin/schools`, `…/{id}/link`, `…/{id}/reject` |
| DOC-BDM-TOUCH-005 | BDM leads in the admin lead list | `/overseas/admin/leads` | overseas_admin | `GET /admin/leads?bdm_organization_id=` |
| DOC-BDM-TOUCH-006 | Management BDM figures (pointer only) | `/management/bdm` | partner, super_admin | `GET /management/bdm` |
| DOC-BDM-REF-001 | Reference lists (types, roles, stages) | n/a | all | none (code constants) |

## (b) Test data needed before screenshots

| # | Data | Why |
|---|---|---|
| 1 | Super Admin, Overseas Admin, 2 active BDM managers (one with BDMs, one empty) | create/deactivate manager flows, picker |
| 2 | 1 Agent BDM + 1 School BDM with password set, 1 Agent BDM with a pending welcome link, 1 with an expired link | sign-in, Re-send, pending/expired states |
| 3 | A BDM with open work (≥1 organization, future appointment, open task, a not-started trip) and a second same-type BDM | deactivate-with-handover preview and counts |
| 4 | An inactive BDM still holding work (mode "leave") | Hand over flow |
| 5 | Submitted trips: one under an active manager, one under an inactive manager | both approval queues; reject reason |
| 6 | Telecaller with pending requests: one pooled Agent request, one named for the School BDM, one accepted, one declined | inbox states, accept-and-book |
| 7 | Agent organization at Agreement Signed + an existing AgentOrg code; School organization with a Signed MoU + an existing School ID | both onboarding queues |
| 8 | BDM-entered leads on an organization | admin lead list org column/filter |
| 9 | Mailpit/SMTP configured (welcome-link "sent" message) and a run without SMTP (warning message) | both create feedbacks |
| 10 | A partner account | `/management/bdm` screenshot |

## (c) Open questions / product findings

| # | Finding | Evidence |
|---|---|---|
| P1 | Welcome email calls the role "Bdm" / "Bdm Manager" (no label mapping) | `svc/mailer.py:26`, `:304` |
| P2 | BDMs and BDM managers can edit their own full name on `/account/profile` although `/bdm/profile` says to contact the administrator; telecallers are locked | `api/auth.py:35`, `:349-354`; `web/app/account/profile/page.tsx:70` |
| P3 | `/overseas/login` copy does not mention BDMs; Agent/School BDMs arriving directly may doubt the portal | `web/app/overseas/login/page.tsx:12` |
| P4 | No notification to BDMs when a telecaller files a meeting request (named or pooled) | `api/bdm_meeting_requests.py`, `svc/bdm_meeting_requests.py` |
| P5 | No Re-send link action on the BDMs page; admins must use the Users page | `AdminBdmRow.tsx` |
| P6 | Sign out lands on `/` rather than the BDM chooser | `PortalShell.tsx:17` |
| P7 | BDM deactivation does not bump `session_version`; relies on the active check | `svc/bdm_lifecycle.py:122-125`, `api/deps.py:54` |
| Q1 | Forgot-password email goes only through the generic `send_notification` webhook; confirm SMTP delivery and URL portal for BDMs | `api/auth.py:383` — **VERIFICATION REQUIRED** |
| Q2 | Can a Super Admin reactivate or rename a BDM manager from the Users page? | **VERIFICATION REQUIRED** |
| Q3 | Should Overseas Admin see any BDM travel or organization data? Currently none | §0.1, §3 |
| Q4 | Super Admin UI for meeting requests beyond the manager page | **VERIFICATION REQUIRED** |
