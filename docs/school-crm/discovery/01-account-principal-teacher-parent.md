# School CRM user-guide discovery: Account access + Principal / Teacher / Parent portals

> **Evidence appendix** for `docs/school-crm/documentation-analysis.md` — raw read-only source discovery (master planning session S1, 2026-10-05, code `main` @ `ce1f07c2`). Field-level detail for module sessions. Not browser-verified; where this file and the browser disagree, the browser wins and this file is annotated, not silently trusted.

Source: repo `edusphere` at main ce1f07c2 (branch docs/school-crm-user-guide). Read-only discovery; nothing executed against a running stack.
Path prefixes: `web/` = `apps/web/`, `api/` = `apps/api/app/`. Every browser call goes to `/api/v1/...`; FastAPI mounts all routers under `/api/v1` (`api/main.py:80`).

Legend: **VERIFICATION REQUIRED** = cannot be confirmed from code alone (needs a running stack / screenshot / owner answer).

---

## PART 1 — ACCOUNT ACCESS (all school-side roles)

### 1.1 Roles and how accounts come to exist

| Role (API value) | UI role label (sidebar pill) | How the account is created | First-password mechanism |
|---|---|---|---|
| `school_coordinator` | "School Coordinator" | Overseas Admin creates the School + seed Coordinator (`api/api/admin.py:1377-1435`) | Welcome / set-password link, 72 h (`api/services/provisioning.py:37`, link built at `:66-70` → `/overseas/reset-password?token=…`) |
| `school_principal` | "Principal" | Coordinator invites from Team page (`POST /school/team/invites`, `api/api/schools.py:176-191`) | Invite link → `/school/invite/{token}/accept`, 7 days (`schools.py:108`) |
| `school_teacher` | "Teacher" | Coordinator invite (same) | Invite link, 7 days |
| `school_parent` | "Parent" | Coordinator invite, OR roster `parent_email` auto-invite/link (`schools.py:847-874`) | Invite link, 7 days; an existing parent account is linked immediately, no email |
| `academic_team`, `career_counselor`, `psychometric_team` | (own portals, not in this doc) | Overseas Admin school-staff creation (`admin.py:1661-1707`) | Welcome link, 72 h |

All seven roles are created with `division="overseas"` (`schools.py:299,306`; `admin.py:1403,1414,1694,1702`). Consequence: **every school-side user signs in at the Overseas Education portal `/overseas/login`**. There is no separate "School login" page.

Invitable roles from the coordinator's Team page are only Principal/Teacher/Parent (`INVITABLE_ROLES`, `schools.py:107`).

### 1.2 Sign in — `/overseas/login`

- Page: `web/app/overseas/login/page.tsx:12`. Left brand panel: eyebrow "Overseas Education Portal", heading "Your global education journey, organised.", lead "Dashboards for students, counselors, university representatives, agents, and administrators." (no mention of schools — as-built). Right card: link "← Back to Overseas Education", heading "Overseas Education Portal", text "Sign in with your authorised overseas education account.", form, then "Student or agent? Create an account". Dev-only "Demo accounts" box (hidden when `ENVIRONMENT=production`) lists only overseas demo accounts, not the school ones.
- Form `web/components/LoginForm.tsx:44-62`:
  - **Email** — `type=email`, required (browser validation).
  - **Password** — `type=password`, required.
  - Button **"Sign in securely"** (busy: "Signing in…").
  - Link **"Forgot your password?"** → `/overseas/forgot-password`.
  - Footer text: "Use the portal that matches your account. Role and division access is verified by the API."
- Endpoint: `POST /api/v1/auth/login` body `{email, password, division:"overseas"}` (`api/api/auth.py:97-110`, no auth dependency).
  - Wrong email/password, or account **inactive**: `401 "Invalid credentials"` (`auth.py:99-101` — query filters `User.active`, so a deactivated user gets the same generic message).
  - Right password, wrong portal (e.g. a school user on `/it/login`): `403 "Use the correct EduSphere portal for this account: sign in at /overseas/login"` (`auth.py:102-104`).
  - Schema errors (malformed email pattern): 422 list, shown joined with "; " (`LoginForm.tsx:9-15`).
  - Error box is `role=alert` with the server `detail` text verbatim.
- Success: sets cookies, writes `auth.login` audit row, then redirects to `?next=` if it is a safe same-origin path (`web/lib/safeNext.ts`), else to the role dashboard (`LoginForm.tsx:40`).

### 1.3 Role → landing page

`ROLE_DASHBOARD_PATH`, `web/lib/navigation.ts:17-42`:

| Role | Landing |
|---|---|
| school_coordinator | `/school/coordinator/dashboard` |
| school_principal | `/school/principal/dashboard` |
| school_teacher | `/school/teacher/dashboard` |
| school_parent | `/school/parent/dashboard` |
| academic_team | `/school/academic-team/dashboard` |
| career_counselor | `/school/career-counselor/dashboard` |
| psychometric_team | `/school/psychometric-team/dashboard` |

Same map is used by invite-accept redirect, the public header "Dashboard" button (`HeaderAuthActions.tsx:26`), "← Back to dashboard" on account pages, and "Go to your dashboard" on the Access-unavailable card.

### 1.4 Sidebar navigation (SCHOOL_NAV, `web/lib/navigation.ts:71-81`)

Labels are generated by title-casing the path segment.
- Principal: **Dashboard · Reports · Global Education · Feedback · Entitlements · Notifications** (`:73`)
- Teacher: **Dashboard · Attendance** (`:74`)
- Parent: **Dashboard · Notifications** (`:75`)
- Coordinator (for reference): Dashboard · Students · Promotion · Transfers · Activities · Feedback · Team · Reports · Global Education · Entitlements · Notifications (`:72`)

Shell (`web/components/PortalShell.tsx:17`): sidebar logo (links to `/`), role pill "<Role label> / <full name>", nav, footer buttons **"Change password"** (`/account/password`), **"My profile"** (`/account/profile`), **"Sign out"**. Top bar: "EduSphere Portal" + user name; below 980 px the sidebar collapses into a menu (`PortalMobileNav`) listing Change password, My profile, then nav items. No unread badge on school navs (badge only used by Agent/BDM navs).

### 1.5 Invite acceptance — `/school/invite/[token]/accept`

- Page `web/app/school/invite/[token]/accept/page.tsx:6-17`: public, no shell. Heading **"Set up your EduSphere login"**, text "Choose a password to finish setting up the account your School Coordinator invited you to."
- Form `web/components/SchoolInviteAcceptForm.tsx:41-57`:
  - **Choose a password** — `type=password`, `minLength=10`, required; hint "Use at least 10 characters." (Browser blocks <10 chars client-side.) No confirm-password field, no show-password toggle, no name/email field (name and email come from the invite).
  - Button **"Accept and set up login"** (busy "Setting up your account…").
- Endpoint `POST /api/v1/school/invites/{token}/accept` (`api/api/schools.py:275-327`), public (no auth dependency), 201.
  - Unknown / already used / revoked token: `409 "This invite has already been used, expired, or was revoked"` (`:279-280`).
  - Expired (past 7 days): same 409 text, and the invite is flipped to `expired` (`:281-284`).
  - Password < 10 chars: `422 "Password must be at least 10 characters"` (`:286-287`). No upper bound and no blank-space rule here (unlike reset/change).
  - Email already has an account: `409 "Email already exists"` (`:288-289`).
  - Any non-string error → fallback "Unable to accept this invite." (`SchoolInviteAcceptForm.tsx:7-11`).
- Success effects: creates the User (active, `email_verified=False`), role assignment, marks invite `accepted`; Principal/Teacher get `profile.school_id = invite.school_id`; a Parent gets **no** school_id and is linked (`SchoolParentLink`) to every student at that school whose `pending_parent_email` equals the invite email (`:290-321`); audit `school.invite_accept`; **signs the user in immediately** (sets cookies, `:325`) and the browser goes to the role landing page (`SchoolInviteAcceptForm.tsx:37`). No success message is shown — the dashboard simply loads.
- Invite email (`api/services/mailer.py:77-121`): subject "You're invited to join {school} on EduSphere"; From "{coordinator} via EduSphere", Reply-To the coordinator; body "{coordinator} has invited you to join {school} on EduSphere as a {Principal|Teacher|Parent}. Accept your invite and set your password: {url}. This link is single-use and expires on {dd Mon yyyy}." If SMTP is not configured, status `not_configured` (no email; dev/test responses include `development_invite_token`).

### 1.6 Forgot / reset password

- `/overseas/forgot-password` (`web/app/overseas/forgot-password/page.tsx`): "← Back to sign in", heading **"Reset your password"**, text "Enter the email on your Overseas Education account and we'll send reset instructions." Field **Email** (required), button **"Send reset instructions"** (busy "Sending…").
  - Always shows: "If an account exists for that email, we've sent instructions to reset the password." (`ForgotPasswordForm.tsx:30-32`). In development the page also shows "Development only: reset link".
  - API `POST /auth/forgot-password` (`auth.py:218-238`, public, 202): only for **active** accounts; token valid **30 minutes**; creates an in-app notification "Password reset requested" / "Use the link we emailed you to reset your password. It expires in 30 minutes." (this appears in the user's Notifications list) and calls the email **webhook** with template `password_reset` + raw token.
  - **VERIFICATION REQUIRED**: the reset email is sent only through the generic email webhook (`services/integrations.py:23-29`), not through the SMTP mailer used for invites; the payload carries the token, not a URL. Whether a real user receives a clickable `/overseas/reset-password?token=…` link depends on the webhook consumer's configuration.
- `/overseas/reset-password?token=…` (`web/app/overseas/reset-password/page.tsx`, `ResetPasswordForm.tsx`): heading **"Choose a new password"**. Field **New password** (min 10, max 128, required; hint "Use at least 10 characters."). Button **"Reset password"** (busy "Resetting…").
  - No token in URL: "This reset link is missing its token. Request a new one from the forgot-password page."
  - API `POST /auth/reset-password` (`auth.py:241-291`): `422 "Password must be at least 10 characters"`, `422 "Password must be at most 128 characters"`, `400 "Reset token is invalid or expired"` (unknown/used/expired/superseded/welcome-on-inactive all identical). On 400 the form adds "Request a new reset link or, if this was your first-time invitation, ask your administrator to re-send it."
  - Network loss: "Network error -- we could not confirm whether your password was saved. Try signing in; if that fails, use this link again or request a new one."
  - Success: no message; redirect to `/overseas/login` (`ResetPasswordForm.tsx:54`). A welcome-link use also sets `email_verified=True`.
  - This same page is the **first-time set-password page for Coordinators and the three service roles** (welcome link, 72 h).

### 1.7 Change password — `/account/password`

- Page `web/app/account/password/page.tsx` (inside the public site shell, not the portal shell): "← Back to dashboard", heading **"Change your password"**, "Signed in as {name} ({email})."
- Signed out: "Sign in required" / "You need to be signed in to change your password." with buttons "IT Training sign in" and "Overseas Education sign in". API outage: "Temporarily unavailable … Your password has not been changed."
- Form `web/components/ChangePasswordForm.tsx:113-193`: **Current password** (required), **New password** (min 10, max 128, required; hint "Use at least 10 characters."), checkbox **Show passwords**, button **"Change password"** (busy "Changing…"), footnote "You stay signed in on this device. Other devices stay signed in until their sessions expire."
- API `POST /auth/change-password` (`auth.py:294-327`):
  - `422 "New password must be different from the current password"`; `422 "Password must not consist only of spaces"` (schema, `schemas.py:160-172`); 422 length errors from schema.
  - `400 "Incorrect current password"` → current field cleared + link "Forgot your current password?" (→ `/overseas/forgot-password`).
  - `429 "Too many incorrect attempts; try again in N seconds"` after 5 wrong attempts in 15 min; UI shows "Too many incorrect attempts. Try again in {a minute|N minutes}."
  - 401: "Your session has expired. Sign in again to change your password." + both portal links.
  - Success: **"Your password was changed."**; unused reset links are cancelled. Session is **not** ended elsewhere (session_version not bumped).

### 1.8 My profile — `/account/profile`

- `web/app/account/profile/page.tsx`: "← Back to dashboard", heading **"Your profile"**, "Signed in as …".
- ProfileForm (`web/components/ProfileForm.tsx:102-150`): **Full name** (2-160 chars, required; validated server-side only — `noValidate`), **Phone** (optional, max 40), button **"Save changes"** (busy "Saving…"). Success **"Your profile was updated."** Network: "Network error. Try again." 401: "Your session has expired. Sign in again to update your profile." Email is not editable.
- API `PATCH /auth/me` (`auth.py:193-215`). Changing `school_id` via profile → `403 "school_id cannot be changed here"` (not reachable from the UI form).
- Section **"Notifications"** — "Choose where we send updates about results, sessions and applications." (`NotificationPreferencesForm.tsx`): fieldset "Send me updates by": Email (always on, disabled), In-app (always on, disabled), **WhatsApp**, **SMS** checkboxes (locked until a valid phone exists; hint "Add a mobile number in your profile above to turn on WhatsApp or SMS." or "The mobile number in your profile can't be used for WhatsApp or SMS…"). Consent text "By turning on WhatsApp or SMS you agree to receive these messages from EduSphere…". Button **"Save notification settings"**; success "Notification settings saved."; failure "Couldn't save your settings. Check your connection and try again."; server 422 "Add a valid mobile number to your profile first" (`api/api/account.py:95`). API `GET/PUT /account/notification-preferences` (`account.py:83,88`).
- `/account/privacy` (data export/delete) is reachable only from the public site header "Privacy" button when signed in, not from the portal sidebar.

### 1.9 Sign out

- Portal sidebar "Sign out" → `POST /auth/logout` (deletes both cookies, `auth.py:165-169`) → browser to `/` (home), not to the login page (`PortalShell.tsx:17`).
- "Sign out" on the Access-unavailable card goes to `/overseas/login` (`SignOutButton.tsx`, `AccessUnavailable.tsx:30`).

### 1.10 Session / auth mechanism

- JWT HS256 (`api/core/security.py:19-27`), claims `sub, role, division, type, exp, sv`.
- Two **HttpOnly, SameSite=Lax, path=/** cookies: `edusphere_access` (60 min) and `edusphere_refresh` (14 days) (`auth.py:89-94`; durations `api/core/config.py:11-12`; `cookie_secure` default False, `config.py:16`).
- Every API request: `get_current_user` (`api/api/deps.py:41-58`) — missing cookie `401 "Not authenticated"`, bad token `401 "Invalid session"`, user missing/inactive `401 "User unavailable"`, `sv` mismatch `401 "Your session has ended. Please sign in again."`.
- Server-rendered pages forward the browser cookies to the API (`web/lib/api.ts:18-32`).
- **As-built:** the web app never calls `POST /auth/refresh` (no reference in `web/`), so a session effectively ends 60 minutes after sign-in regardless of activity; the next page shows "Access unavailable / Not authenticated" + "Return to login". **VERIFICATION REQUIRED** in a browser.
- `web/middleware.ts:6,18` protects `/it/*`, `/overseas/(roles)`, `/admin`, `/bdm` only — **`/school/*` and `/account/*` are not in the matcher**, so school pages are reached even signed out and gate themselves by calling the API.
- **VERIFICATION REQUIRED**: how `/api/v1/*` browser calls reach the API (no Next rewrites in `web/next.config.ts`; presumably a reverse proxy in deployment).

### 1.11 Deactivated / inactive accounts

- Coordinator Team page toggles Principal/Teacher/Parent `active` (`PATCH /school/team/accounts/{id}`, `schools.py:235-272`).
- Login → "Invalid credentials" (no hint that the account is deactivated).
- Already-signed-in user → next request `401 "User unavailable"` → page shows card **"Access unavailable" / "User unavailable"** + **"Return to login"** (`AccessUnavailable.tsx:19-35,45-56`).
- Forgot-password silently does nothing for inactive accounts.
- Inactive parents/coordinators/principals receive no new notifications (`schools.py:749`, `admin.py:1479`).
- As-built: a Parent linked at two schools has one global `active` flag — a coordinator at either school can deactivate the whole parent account (`schools.py:254-266`).

### 1.12 Opening another role's URL / signed-out access

Standard "Access unavailable" card (`web/components/AccessUnavailable.tsx`): heading **"Access unavailable"**, the API's message, then **"Go to your dashboard"** + **"Sign out"** (signed-in) or **"Return to login"** (signed out, links to `/overseas/login?next=<current page>`).

Behaviour per page (frontend guard is inconsistent; the API always enforces data scope):

| Page | Frontend role check | What a wrong school role sees |
|---|---|---|
| `/school/principal/dashboard` | none (`page.tsx:16-28`) | Teacher/Parent/Coordinator: page renders with **"Principal" label**; roster = whatever `/school/students` returns for *their* scope (teacher → assigned, parent → own children, coordinator → whole school); "School at a glance" shows "This section couldn't load. Refresh to try again." for teacher/parent. Service roles: "School role required". |
| `/school/principal/reports` | `role === school_principal` (`reports/page.tsx:35`) | "Principal role required" |
| `/school/principal/global-education` | yes (`GlobalEducationPage.tsx:35`) | "Principal role required" |
| `/school/principal/feedback` | yes (`feedback/page.tsx:22`) | non-coordinator/principal: API message "School Coordinator or Principal role required" (API is called first); coordinator: "Principal role required" |
| `/school/principal/entitlements` | none | Coordinator sees the page under "Principal" label; others: "School Coordinator or Principal role required" |
| `/school/principal/notifications` | yes (`notifications/page.tsx:15`) | "School Principal role required" |
| `/school/principal/students/[id]` | none | Bespoke card (no shell) with API message + "Back to dashboard"; a teacher opening an assigned student renders under "Principal" label |
| `/school/teacher/dashboard` | none | Principal/Coordinator see the **whole school** listed as "Your students"; Parent sees own children |
| `/school/teacher/attendance` | API only | "Teacher role required" |
| `/school/teacher/students/[id]` | none | Bespoke card + "Back to your students" |
| `/school/parent/dashboard` | none | Principal/Coordinator: every student in the school rendered as "My children" cards; Teacher: assigned students |
| `/school/parent/children/[id]` | none | Bespoke card + "Back to my children"; principal/coordinator/teacher in scope can render it under "Parent" label |
| `/school/parent/notifications` | none | Any signed-in user sees *their own* notifications under the "Parent" label |
| any `/school/*/students/[id]/360` | none | API scope applies; renders under whichever portal's label |

Non-school roles (e.g. overseas student) on school pages: API returns "School role required" / role-specific 403 → Access-unavailable card.

### 1.13 Parent with children in multiple schools (ENH-008)

- Parent scope is the set of `SchoolParentLink` rows, not a school (`schools.py:877-897`, `1283-1298`). Links can span schools (coordinator of a second school enters an existing parent's email → linked immediately, no email, `schools.py:861-866`).
- **There is no school switcher** (`web/app/school/parent/dashboard/page.tsx:17`: "No switcher control: every child's summary is visible at once"). When children's school names differ, the dashboard groups child cards under a heading per school name (`:58-71`, `SchoolChildOverview.tsx:68-70`); single-school parents see no school headings.
- Parent's 7-day invite comes from whichever school first invited them; later schools only link.

---

## PART 2 — PRINCIPAL PORTAL (`/school/principal/**`)

Backend role sets: dashboard/reports/entitlements `{school_coordinator, school_principal}` inline checks (`schools.py:902-903, 916-917, 1232-1233`); analytics/feedback/global-education/school-summary use `_require_school_reader` (`api/api/school_feedback.py:105-110`, same two roles + must have `profile.school_id` else `403 "This account is not linked to a school"`). Everything is own-school only; school comes from the session profile.

### 2.1 Dashboard — `/school/principal/dashboard` (sidebar "Dashboard")

File `web/app/school/principal/dashboard/page.tsx`. Read-only.
1. **"School at a glance"** KPI board (`SchoolKpiBoard.tsx`), from `GET /school/dashboard` (`schools.py:900-905`). Four groups (definitions from `_school_dashboard_payload`, `schools.py:404-572`):
   - *Students*: Total Students (all roster rows); Grade 8 … Grade 12 (by `grade_level`, else parsed from Grade/Class label "Grade/Class 8-12").
   - *Career & assessment*: Career Guidance Completed (students with a guidance session whose status counts as completed / legacy no-status); Psychometric Tests Completed (students with a `completed` psychometric record); Individual Counselling Completed (students with a completed counselling note).
   - *Skills & languages*: IELTS Training / SAT Preparation (students with any IELTS / SAT test-prep record); Foreign Language Students (any language record); Digital Portfolios Created (students with a started portfolio).
   - *Global pathway*: Students in Global Education Pathway (any linked overseas application); University Shortlisting (application at university_selection or later); Applications in Progress (count of applications not withdrawn/rejected/enrolled — applications, not students); Offers Received (applications with offer-onward status or offer letter); Visa Applications (students with a visa case); Students Admitted (application `enrolled`); Internships (students with an internship portfolio entry).
   - Numbers formatted en-IN. "Not tracked yet" badge exists in code but no KPI is currently untracked (`schools.py:112`).
   - Empty: "No figures to show yet." Load failure: card "School at a glance" + "This section couldn't load. Refresh to try again."
2. **"Your school"** card: "{n} student(s) on the roster." Table columns **Name | Grade/Class | (button "Timeline")**; sorted by name A–Z (API `schools.py:1252`); no search, filter, sort control or pagination. "Timeline" → `/school/principal/students/{id}`. Empty: "No students yet. Ask your School Coordinator to add your first student." Button **"View full reports"** → Reports.
3. **"Results & guidance"** card (`SchoolServiceDeliverySummary.tsx`): "{n} published result(s), {n} career guidance/counselling record(s), {n} psychometric assessment(s)." Hidden entirely when all three are 0 or any call fails. Endpoints `GET /school/results`, `/school/career-records`, `/school/psychometric-records` (`schools.py:2665, 2219, 2311`).
- Whole-page failure on `/auth/me` or `/school/students` → Access-unavailable card.

### 2.2 Reports — `/school/principal/reports` (sidebar "Reports")

File `web/app/school/principal/reports/page.tsx`. Frontend guard principal-only (`:35`). Read-only except URL-driven filters.
1. **"Download reports"** card: "A PDF of your school's summary figures and grade-by-grade table, as of today." Button **"Download school report (PDF)"** (busy "Preparing PDF…"); hint "PDFs are not screen-reader friendly. The same figures are on your dashboard and in the grade-wise comparison on this page." Success "Report downloaded." Errors: 401 "Your session has expired. Sign in again."; 5xx/network "Something went wrong on our side. Please try again."; else server detail (`ReportDownloadButton.tsx`). API `GET /school/reports/school-summary` → `school-report.pdf` (`api/api/school_reports.py:90-101`); 500 "Could not generate the report; please try again". Log line only, no audit row.
2. **SchoolReportsPanel** (`SchoolReportsPanel.tsx`, data `GET /school/reports`, `schools.py:908-919`):
   - Metric tiles: **Students, Teachers, Parents, Pending invites** (pending = school invites in `pending` status).
   - **"Students by grade"** bar chart by Grade/Class label (unspecified → "Unspecified"); footnote "{x} of {n} students have an assigned Teacher." Empty: "No students on the roster yet."
   - **"Service delivery completion"** — "Share of students with at least one record in each area." Rings: **Career guidance** (students with *any* career record), **Psychometric completed**, **Results published** (students with ≥1 published result). Note "{n} more assessment(s) assigned, awaiting completion."
   - **"Activities & attendance"** tiles: Total activities, Upcoming, Completed (past), Attendance rate (% present of activity-attendance marks, "-" if none).
3. **Analytics sections** (`SchoolAnalyticsSections.tsx`, loader `web/lib/schoolAnalytics.ts`):
   - **"Grade-wise comparison"** table (`SchoolGradePerformance.tsx`; API `GET /school/analytics/grade-performance`, `api/api/school_analytics.py:266-272`): rows Students, Career readiness*, Assessment completion, Counselling completion, Skills development*, Global education interest*, Application readiness*, University applications, Admissions; columns Grade 8–12 / "Other grades" / "No grade"; cells "count (pct%)". *Estimates show "Estimate: {definition}" (`school_analytics.py:254-263`). Empty "No students on the roster yet."
   - **"Student development"** (`SchoolStudentDevelopment.tsx`; API `GET /school/analytics/student-development`, `:311-381`): headcount line "{n} students · {n} teachers · {n} parents"; table Activity | Completed | Pending for Career Guidance, Psychometric Test, Foreign Language (certified), English Testing (IELTS completed), University Guidance (shortlisted); "Academic performance" (published results only): By grade / By subject / By term average tables or "No published results yet."; threshold form **At risk below (%)** (0-100, default 40) and **Top performer from (%)** (0-100, default 85), button **"Update thresholds"** (plain GET; values kept in URL). Bad URL values: "Thresholds must be between 0 and 100. Showing the defaults." / "At-risk must be below the top-performer threshold. Showing the defaults." Lists **"At-risk students (n)"** / **"Top performers (n)"** (max 50 shown, "Showing the first 50."); empty "No students below {x}%." / "No students at or above {y}% yet."
   - **"Student progress scorecards"** grid (`SchoolScorecardGrid.tsx`; API `GET /school/analytics/scorecards`, `:448-466`): filter **Grade** (All grades / Grade 8-12) + **Show**; columns Student (link to `/school/principal/students/{id}`) + 12 areas (Career Awareness, Psychometric, Career Counselling, Soft Skills, Foreign Language, Digital Portfolio, IELTS/SAT, University Shortlisting, Scholarship, Application, Visa, Internship); cell states "✅ Completed / 🔄 In progress / ⏳ Not started / — Not in plan / — Not tracked yet" (Scholarship is always "Not tracked yet"). Pagination 25 per page, "← Previous" / "Next →", "{a}–{b} of {n}". Empty "No students on the roster yet." / "No students match this grade." / "This page is past the end of the list."
   - Each section fails independently → SectionUnavailable card.
- No search or column sorting anywhere on this page.

### 2.3 Global Education — `/school/principal/global-education` (sidebar "Global Education")

Shared renderer `web/components/GlobalEducationPage.tsx`; API `GET /school/global-education/pipeline` (`api/api/school_global_education.py:74-120`). Read-only. Heading **"Global education"**.
- **"Pipeline"** card: "{n} students[ in Grade g] · {n} students on the global education pathway"; note "High-level stage only. Application details are handled by EduSphere's application team." Funnel stages: Global education pathway, Profile evaluation, University shortlisted, Offer received, Visa, Admitted (counts; bar is decorative). **"Not tracked yet"** tiles: Applications started, Applications submitted, Deposit, Scholarships, Top 100 universities, Alumni — each with its reason note (`:35-42`).
- **"Students"** card: filter **Grade** + **Show**; table Student | Student ID | Grade | Furthest stage | Visa | Applications (names are plain text, not links); 25 per page, Previous/Next. Empty: "No students from this school are on the global education pathway yet. Students appear here once an EduSphere counselor links their application." / "No students in this grade are on the global education pathway." Visa labels: Checklist, Documentation, Interview preparation, Tracking, Decision, or "In progress".
- Failure (non-401/403) → "Global education pipeline" SectionUnavailable.

### 2.4 Feedback — `/school/principal/feedback` (sidebar "Feedback")

`web/app/school/principal/feedback/page.tsx` + `SchoolActivityFeedbackPanel.tsx` with `canSubmit=false`. API `GET /school/activity-feedback?status=&limit=25&offset=` (`school_feedback.py:113-151`). Read-only.
- Heading **"Activity feedback"**, subtitle "Feedback your coordinator recorded after each Edusphere activity."
- Filter **Show**: All / Awaiting feedback / Submitted (kept in URL `?status=`).
- List rows (only typed Edusphere activities already held; newest first): title; "{type} · {date time IST} · {x of y present | Not marked}"; badge **Submitted** / **Awaiting feedback**; disclosure **"View feedback"** → Overall rating, School satisfaction ("n – Poor/Fair/Good/Very good/Excellent"), Trainer / Counsellor, Feedback, Suggestions, Submitted by {name}, {time}.
- "Showing {n} of {total}", **"Load more"** (25 at a time). No search/sort.
- Empty: "No completed Edusphere activities yet." (+ "Feedback opens after a career seminar, career awareness session, parent orientation or campus visit has taken place."), "Nothing awaiting feedback.", "No feedback submitted yet."
- Errors: "Could not load activity feedback." + "Try again"; 401 "Your session has expired. Sign in again" (link to `/overseas/login`).
- Activity type labels: Career seminar, Student career awareness session, Parent orientation, Monthly campus visit.

### 2.5 Entitlements — `/school/principal/entitlements` (sidebar "Entitlements")

`web/app/school/principal/entitlements/page.tsx`, `SchoolEntitlementsPanel.tsx`; API `GET /school/entitlements` (`schools.py:1224-1245`). Read-only.
- Heading **"Partnership entitlements"**; "Plan: {Tier} Partner — valid until {date}".
- Table Service | Included (always ✓) | Used. Services are cumulative by tier (`schools.py` TIER_SERVICES): Bronze — Career seminar, Student career awareness session, Parent orientation, Psychometric test, Soft skills; +Silver — Individual counselling, Digital skills; +Gold — Application support, Scholarship assistance, IELTS coaching, SAT coaching, Foreign language classes, Digital portfolio creation; +Platinum — Dedicated EduSphere counselor, Monthly campus visits, Internships, Visa support, Loan assistance, Alumni network, Parent help desk.
- Used = real count (activities scheduled by type, student counts, etc., `schools.py:1150-1222`), "Assigned"/"Not assigned" for Dedicated counselor, or "Not tracked" (Alumni network, Parent help desk).
- No tier: "No partnership tier has been set for your school yet. Contact your EduSphere Overseas Admin."
- As-built: an expired tier still lists services with no "expired" warning; only the date shows.

### 2.6 Notifications — `/school/principal/notifications` (sidebar "Notifications")

`notifications/page.tsx`, `SchoolNotificationList.tsx`; API `GET /workflows/notifications` (newest 100, `api/api/workflows.py:2633-2636`), `PATCH /workflows/notifications/{id}/read` (`:2646-2653`).
- Heading "Notifications"; list rows: title + text badge "new" (unread), body, time (IST); **"Open"** button if the notice has a link (marks it read in the background).
- Empty: "No notifications yet. You will be told here when your school's partnership changes."
- Triggers (`admin.py:1453-1490`): Overseas Admin tier change → "Your partnership is now {Tier}" / "{school} has moved from {A} to {B}. Newly available: …" or "Your partnership changed from {A} to {B}" / "These services are no longer available for new work: … Work already started for them can still be completed."; Open → `/school/principal/entitlements`. Also delivered by email (and WhatsApp/SMS if opted in) via the notification worker. Also "Password reset requested" if the principal used forgot-password.
- No "mark all read"; no unread badge in sidebar.

### 2.7 Student page (journey) — `/school/principal/students/[id]`

Reached from Dashboard "Timeline" or scorecard grid name. `web/app/school/principal/students/[id]/page.tsx`. Read-only.
- **Header card** (`SchoolStudentDetailPanel.tsx`): "{name} ({student code})", photo (view only), rows Grade/Class, Date of birth, Gender, Section, Roll number, Student mobile, City, Subjects, Career interests, Interested in studying abroad, Preferred countries, Preferred courses ("Not recorded" when empty). Buttons **"Open 360° view"**, **"Back to dashboard"**.
- **"Journey timeline"** (`GET /school/students/{id}/timeline`, `schools.py:1430`): dated events with category badges Profile, Career, Psychometric, Academic, Activity, Test prep, Foreign language, Global education, Soft skills, Digital skills. Empty "No journey events recorded yet."; failure "Timeline is unavailable right now."
- **"Digital Portfolio"** (read-only for principal, `api/api/portfolio.py:53,78-87`): completion bar "{n}% complete", Profile, Academic achievements, Psychometric report, Career guidance, Languages, entry sections, personal statement.
- **"Progress report"** card: "A PDF of this student's profile and progress to date." Button **"Download progress report (PDF)"** → `progress-report.pdf`; hint "PDFs are not screen-reader friendly. The same information is in this student's 360° view." API `GET /school/students/{id}/progress-report` (`school_reports.py:111-123`), roles parent/coordinator/principal (`403 "Parent, School Coordinator or Principal role required"`); writes audit row `school.progress_report_download`.
- **"Progress scorecard"** (`StudentScorecard.tsx`; `GET /school/students/{id}/scorecard`, `school_analytics.py:469-480`; other school → 404 "Student not found"): "Portfolio {n}% complete", table Area | Status (same 12 areas/states).
- **"Funding support"** (`FundingRecordsCard.tsx`; `GET /school/students/{id}/funding-records`, `api/api/school_funding.py:128-146`): per case Support type, Stage "… since {date}", Provider, Amount, Reason closed, Notes, Updated by. Empty "No funding support cases for this student." Failure "Funding support cases couldn't be loaded. Reload the page to try again."
- Errors: student at another school → bespoke card "Access unavailable" + "This student is at a different institution" + "Back to dashboard" (no sidebar).

### 2.8 Student 360° — `/school/principal/students/[id]/360`

`renderStudent360Route` (`web/components/Student360Route.tsx`), API `GET /school/students/{id}/360-view` (`api/api/student_360.py:141-150`). For all four School roles every one of the 16 tabs is visible, none "Restricted" (`student_360.py:60-138`): Overview, Personal Details, Academic Records, Attendance, Examination Results, Career Guidance, Psychometric Assessment, Skills, Foreign Languages, English Testing, Activities, Certificates, Documents, Teacher Remarks, Parent Communication, Edusphere Programs (`web/lib/student360Links.ts:5-19`). Back link "Back to student". Tab is kept in `?tab=`. Career goal is read-only (only a Career Counselor can edit). (Depth covered by the 360 agent.)

---

## PART 3 — TEACHER PORTAL (`/school/teacher/**`)

Scope: own school AND `assigned_teacher_user_id == teacher` (`schools.py:892-893, 1305-1306`).

### 3.1 Dashboard — `/school/teacher/dashboard` (sidebar "Dashboard")

`web/app/school/teacher/dashboard/page.tsx`. Read-only.
- **"Your students"** table Name | Grade/Class | **"View"** (→ `/school/teacher/students/{id}`); sorted by name; no search/filter/sort/pagination. Empty: "No students assigned to you yet."
- **"Results & guidance"** card (same component as principal; counts limited to the teacher's assigned students — confirmed: `/school/results` etc. use `_readable_students` = same assigned-only / linked-child scope, `schools.py:2052-2059, 2665-2680`).
- API `GET /school/students`.

### 3.2 Attendance — `/school/teacher/attendance` (sidebar "Attendance")

`web/app/school/teacher/attendance/page.tsx`, `web/components/SchoolDailyAttendance.tsx`; API `api/api/school_attendance.py`. Editable.
- Heading **"Attendance"**. Date bar: **Date** (`type=date`, max = school "today" in IST from the server) + **"Show"** (navigates to `?date=YYYY-MM-DD`). Notes under the field: "Choose a date and press Show.", "{date} is in the future; attendance cannot be marked for it.", "Showing {d1}. Press Show to open {d2}." Invalid/impossible `?date=` silently falls back to today.
- Roster (assigned students enrolled at the school on that day; sorted by Grade/Class then name): per student legend "{name} · {grade}" + badge **"Not marked"** if no saved status; radios **Present / Absent / Late / Excused** (none preselected). "{x} of {n} students marked". Button **"Mark all present"** (fills only unmarked). Button **"Save attendance"** (busy "Saving…"); "Unsaved changes" indicator.
- Leave guard: "You have unsaved attendance. Leave without saving it?" (links, Back/Forward, tab close).
- Client messages: "Choose a status for at least one student."; date mismatch "{note} To save {date}, set the date back to it."
- Success: "Attendance saved for {n} student(s) on {date}.[ {k} left unmarked.]" Students left blank are untouched (partial save allowed); re-saving overwrites.
- Server errors (`school_attendance.py:28-33`): `403 "Teacher role required"`; `422 "Attendance cannot be marked for a future date"`; `403 "One or more students are not assigned to you"` → UI replaces with "Your class list changed since this page was opened, so nothing was saved. The list has been updated — check the marks and save again." and refreshes; `409 "This class's attendance is being changed elsewhere. Try again."` (refresh); `422 "One or more students were not enrolled at your school on {dd Mon yyyy}"`; tier gate `403 "This school has no active partnership tier."` or `403 "This school's partnership expired on {date}."` (`schools.py:1075-1091`, service_key None); body limits 1-500 records, unique students, no extra fields (`schemas.py:2677-2680`).
- Empty: today "No students assigned to you yet. Your School Coordinator assigns students to teachers."; past day "None of your current students were enrolled at your school on {date}."
- Endpoints: `GET /school/attendance?date=` (`:92-100`), `PUT /school/attendance` (`:103-187`). Side effects: audit `school.daily_attendance_mark` (with per-student from→to changes) or `school.daily_attendance_denied`. No parent notification is sent for daily attendance; parents see counts on their child page.

### 3.3 Student page — `/school/teacher/students/[id]`

`web/app/school/teacher/students/[id]/page.tsx`. Same header panel (profile rows, photo view-only, **"Open 360° view"**, **"Back to your students"**), **Journey timeline**, **Digital Portfolio**.
- **Digital Portfolio is EDITABLE for the assigned teacher** (`api/api/portfolio.py:53` WRITE_ROLES includes `school_teacher`; `:78-87`): buttons "Add {entry}", "Edit {title}", "Delete {title}" → "Confirm delete {title}", "Add statement"/"Edit statement". Entry form fields (`PortfolioEntryForm.tsx:140-196`): Title (Role for internships), Organization (optional) / Company / Issuing body (optional), Start date (optional), End date (optional), Description (optional), certification Status / Certificate number / Issue date, Skill India checkbox; Cancel. Confirmations e.g. "Certification added." / "Personal statement saved." Internship tracking locked unless school tier includes Internships. (Full form/error detail: cross-reference the portfolio discovery; **VERIFICATION REQUIRED** for exact section list and server messages.)
- Not shown to teachers: progress report PDF, scorecard, funding support (funding API refuses teachers: "Funding support cases are not visible to teachers.", `school_funding.py:38,132-133`).
- Not-assigned student → bespoke card "Access unavailable" / "This student is not assigned to you" + "Back to your students".

### 3.4 Student 360° — `/school/teacher/students/[id]/360`

All 16 tabs visible (teacher is a School role), back link "Back to student". Assigned students only (API).

---

## PART 4 — PARENT PORTAL (`/school/parent/**`)

Scope: students linked via `SchoolParentLink` only, any school (`schools.py:888-890, 1291-1298`).

### 4.1 Dashboard — `/school/parent/dashboard` (sidebar "Dashboard")

`web/app/school/parent/dashboard/page.tsx`. Read-only. Heading **"My children"**.
- One card per linked child (grouped under school-name headings only when children are at different schools): "{name} ({code})", **Grade/Class**, **Date of birth**, **Class teacher** ("Not assigned yet"), status row (`ChildStatusRow`, `SchoolChildOverview.tsx:83-104`): Career guidance, Counselling, Psychometric (status chips: Not started / In progress / Assigned / Completed …), Published results (count), Attendance "(last N marked days)" "x present · x late · x absent · x excused" or "Not marked yet", Soft skills, Digital skills; **Recommended careers** badges if any. Button **"View full profile & progress"**. Overview failure: "Progress details are unavailable right now."
- No child: "No child linked to your account yet. Contact your school to get set up."
- **"Upcoming sessions"**: de-duplicated upcoming school activities (next 10 per child's school, all school-wide activities, not child-specific), "{date time IST} — {title}"; empty "Nothing scheduled yet."
- **"Important notifications"** + "{n} unread" badge: latest 5 (title, time, body, "Open" link); empty "No notifications yet. You will be notified here when an assessment, counselling session, workshop, or result is recorded for your child."; button **"All notifications"**.
- Endpoints: `GET /school/students`, `GET /school/students/{id}/overview` per child (`schools.py:1316-1329`), `GET /workflows/notifications`.

### 4.2 Child page — `/school/parent/children/[id]`

`web/app/school/parent/children/[id]/page.tsx`. Read-only.
- Action row: **"Open 360° view"**, **"Download progress report (PDF)"** (hint "PDFs are not screen-reader friendly. The same information is on this page."), **"Back to my children"**.
- Overview (`SchoolChildOverview.tsx:139-263`): header (photo, School, Grade/Class, Section / Roll number, Date of birth, Class teacher); status row; cards **Career guidance** ("No career guidance session recorded yet."), **Counselling** ("No counselling notes yet."), **Recommended careers** ("No career recommendation yet — this appears once the Career Counselor records one."; sub-heading "From counselling sessions"), **Psychometric assessment** table Assessment | Status | Assigned on + results ("No psychometric assessment assigned yet."), **Academic results** table Year | Term | Subject | Marks | % | Grade | Remarks — published only ("No published results yet. A result appears here only once the school has published it."), **Activities** table Activity | Date | Attendance (Present/Absent) ("No activity attendance recorded yet."), **Skills** (Soft skills / Digital skills batches, attendance, scores), **Upcoming sessions**.
- **Funding support** (parent sees all the child's cases), **Grade history** ("No promotions recorded yet."; Promoted / Held back entries), **Transfer history** (hidden if none; "Moved from A to B"), **Journey timeline**, **Digital Portfolio** (read-only).
- As-built: the overview API also returns Test prep, Foreign language and Global education data, but this page does not render them (they appear in the 360° view).
- Not-linked child → bespoke card "Access unavailable" / "This student is not linked to your account" + "Back to my children".
- Endpoints: overview, timeline, grade-history (`schools.py:1503`), transfer-history (`api/api/school_transfers.py:228`), portfolio (`portfolio.py:121`), funding-records, progress-report, photo (`api/api/school_student_profile.py:94`).

### 4.3 Child 360° — `/school/parent/children/[id]/360`

All 16 tabs visible (parent is a School role), back link "Back to my child". Linked children only.

### 4.4 Notifications — `/school/parent/notifications` (sidebar "Notifications")

`web/app/school/parent/notifications/page.tsx`. Table **When | Notification | (Open)**; "new" badge for unread; newest 100; no pagination/filter. Empty text as on dashboard.
- **As-built:** neither parent page ever marks a notification read (the "Open" links are plain links; no `PATCH …/read` call), so "new" badges and the dashboard "{n} unread" count never clear. **VERIFICATION REQUIRED** in browser.
- Notification triggers for parents (in-app + email; WhatsApp/SMS if opted in) — all link to `/school/parent/children/{id}` unless noted:
  - "Upcoming session: {title}" — coordinator schedules an activity; to every parent at the school; link `/school/parent/dashboard` (`schools.py:1803-1806`; time in body formatted from the stored UTC value — **VERIFICATION REQUIRED** whether it shows UTC rather than IST).
  - Career Counselor record added (`schools.py:2128`, `2194`), psychometric assigned / report ready (`:2258-2292`), IELTS/SAT started / result recorded (`:2347, 2374`), language classes started / certification (`:2424, 2454`), result published (`:2604`), overseas application started (`admin.py:1805`), funding case changes (`school_funding.py:101`), skills batch events (`school_skills.py:294`), bulk academic results (`school_bulk.py:441`), transfer approved "{child} has moved to {school}" (`school_transfers.py:456-462`).

---

## Endpoint inventory (this area)

Auth/account (11): POST /auth/login · POST /auth/logout · GET /auth/me · PATCH /auth/me · POST /auth/forgot-password · POST /auth/reset-password · POST /auth/change-password · POST /auth/refresh (unused by web) · POST /school/invites/{token}/accept · GET /account/notification-preferences · PUT /account/notification-preferences.
Principal-read (18): GET /school/dashboard · /school/reports · /school/reports/school-summary · /school/analytics/grade-performance · /school/analytics/student-development · /school/analytics/scorecards · /school/global-education/pipeline · /school/activity-feedback · /school/entitlements · /school/students · /school/results · /school/career-records · /school/psychometric-records · /workflows/notifications · PATCH /workflows/notifications/{id}/read · GET /school/students/{id}/scorecard · /funding-records · /progress-report.
Shared student reads (8): GET /school/students/{id} · /overview · /timeline · /grade-history · /transfer-history · /portfolio · /photo · /360-view.
Teacher writes (2 + portfolio): GET/PUT /school/attendance; portfolio entry POST/PATCH/DELETE + PUT personal-statement.
Total ≈ 39 distinct endpoints (+ portfolio writes).

## Routes covered (19)
/overseas/login, /overseas/forgot-password, /overseas/reset-password, /school/invite/[token]/accept, /account/password, /account/profile, (/account/privacy); principal: dashboard, reports, global-education, feedback, entitlements, notifications, students/[id], students/[id]/360; teacher: dashboard, attendance, students/[id], students/[id]/360; parent: dashboard, children/[id], children/[id]/360, notifications.

## As-built oddities (do not fix; document)
1. Login page copy is overseas-only; no school login entry, school demo accounts not listed.
2. `/school/*` is outside middleware; several pages have no frontend role check, so other school roles can render them under the wrong role label (table in 1.12).
3. No refresh-token use → ~60 min hard session.
4. Parent notifications never marked read on parent pages.
5. Principal dashboard has no "students" sidebar entry; student list only via Dashboard "Timeline" button or Reports scorecard grid.
6. `school_reports` endpoint returns the dashboard payload; old code after `return` is dead (`schools.py:920-1010`).
7. Report "Career guidance" ring counts any career record, while the KPI "Career Guidance Completed" counts completed guidance sessions — different numbers for similar labels.
8. "Applications in Progress" KPI counts applications, other pathway KPIs count students.
9. Invite accept has no max length / blank check, and its token-in-path page has no no-referrer header (unlike reset-password).
10. Sign out from the sidebar goes to the site home, not the login page.
11. Deactivating a multi-school parent from one school blocks them everywhere.
12. Expired partnership not flagged on Entitlements page.
13. Activity-notification time string built from UTC.
14. Parent "Upcoming sessions" lists all school-wide activities, not ones the child is enrolled in.

## Required test data (per feature)
- School "Sunrise Public School" (seed, platinum, valid 365 d) with demo accounts `school.principal@ / school.teacher@ / school.parent@ / school.coordinator@edusphere.local`, password = seed `PASSWORD` constant in `apps/api/app/seed.py` (not reproduced in docs) (`api/seed.py:615-690`). Seed students are Grades 3, 4, 5, 8 → Grade 8 KPI = 1; add Grade 9-12 students for meaningful KPIs/scorecards.
- Pending invite for each of Principal/Teacher/Parent (dev response exposes `development_invite_token`); one expired invite (set `expires_at` in past) and one used invite for error screenshots.
- Inactive teacher account (deactivate from Team page) for the deactivated-login screenshot.
- Second school with the same parent linked to a child there (ENH-008 grouping).
- At least one past typed activity with feedback submitted and one awaiting (Feedback page); activity attendance marks.
- Published academic results across 2 subjects/terms with some < 40% and some ≥ 85% (Student development lists).
- Linked overseas application(s) + a visa case for one student (Global Education funnel/table).
- Tier change by Overseas Admin (upgrade then downgrade) for principal notifications.
- Funding case for one student (principal/parent Funding support).
- Teacher with ≥3 assigned students, one created today (past-date "not enrolled" case).
- Parent notifications from psychometric assign, result publish, activity schedule.

## Suggested screenshots (sequence-feature-step)
01-access-login-empty · 01-access-login-invalid-credentials · 01-access-login-wrong-portal (sign in at /it/login) · 01-access-login-deactivated
02-access-invite-accept-form · 02-access-invite-accept-error-used · 02-access-invite-accept-short-password
03-access-forgot-password-form · 03-access-forgot-password-confirmation · 03-access-reset-password-form · 03-access-reset-password-invalid-link
04-access-change-password-form · 04-access-change-password-success · 04-access-change-password-wrong-current
05-access-profile-page · 05-access-profile-notifications-section
06-access-unavailable-wrong-role (teacher → /school/principal/reports) · 06-access-unavailable-signed-out (/school/parent/dashboard signed out)
10-principal-dashboard-kpis · 10-principal-dashboard-roster · 11-principal-reports-download · 11-principal-reports-panel · 11-principal-reports-grade-comparison · 11-principal-reports-student-development · 11-principal-reports-scorecards-grade-filter
12-principal-global-education-funnel · 12-principal-global-education-students
13-principal-feedback-list · 13-principal-feedback-view-details · 13-principal-feedback-filter-awaiting
14-principal-entitlements · 15-principal-notifications
16-principal-student-header · 16-principal-student-timeline · 16-principal-student-scorecard-funding · 17-principal-student-360-tabs
20-teacher-dashboard · 21-teacher-attendance-unmarked · 21-teacher-attendance-mark-all-present · 21-teacher-attendance-saved · 21-teacher-attendance-future-date-note · 21-teacher-attendance-unsaved-leave-prompt
22-teacher-student-page · 22-teacher-student-portfolio-edit · 23-teacher-student-360
30-parent-dashboard-children · 30-parent-dashboard-multi-school-grouping · 30-parent-dashboard-notifications-card
31-parent-child-overview · 31-parent-child-results-activities · 31-parent-child-funding-grade-transfer · 31-parent-child-progress-report-download
32-parent-child-360 · 33-parent-notifications-table
90-shell-sidebar-footer (Change password / My profile / Sign out) · 91-shell-mobile-menu (≤640 px)

## Top VERIFICATION REQUIRED items
1. Reset-password email delivery (webhook-only, token not URL).
2. Session expiry at 60 min without refresh; exact user experience.
3. Parent notification "new" badges never clearing.
4. (Resolved) `/school/results` etc. use the roster scope (`schools.py:2052-2059`).
5. Reverse-proxy routing of `/api/v1` in deployed environments.
6. Activity notification time zone (UTC vs IST).
7. Teacher portfolio edit form: full section list and server error texts (cross-reference portfolio discovery).
