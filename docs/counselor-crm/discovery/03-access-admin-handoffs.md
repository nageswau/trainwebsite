# Counselor CRM docs — Discovery 03: Access, admin side, handoffs

Baseline: `main @045d8c40`. Read-only pass over code. This file documents what the code does. The backlogs were used for context only.
Paths are relative to `apps/`. `NEEDS_CONFIRMATION` marks anything not settled in code.

Roles used below: **Counselor** = `counselor` with division `overseas`. **OA** = Overseas Admin (`overseas_admin`). **SA** = Super Admin (`super_admin`, division `global`).

---

## 1. AUTH: account access

### DOC-CNS-AUTH-001 Sign in (Overseas portal)
- **Route:** `/overseas/login`. Reached from public header sign-in or redirect: middleware sends any unauthenticated `/overseas/(student|counselor|university|agent|admin)/*` to `/overseas/login?next=<path>` (`web/middleware.ts:11,20-21`).
- **Screen:** brand panel "Overseas Education Portal" / "Your global education journey, organised."; card heading "Overseas Education Portal", "Sign in with your authorised overseas education account." Fields **Email** (required), **Password** (required); button **Sign in securely** ("Signing in…"); link **Forgot your password?**; footnote "Use the portal that matches your account. Role and division access is verified by the API." Also "Student or agent? Create an account" (not for counselors). In non-production only, a "Demo accounts" box lists `counselor@edusphere.local` / `Demo@123` (`web/app/overseas/login/page.tsx:12`, `web/components/LoginForm.tsx:44-62`).
- **Redirect after login:** a safe relative `next` if present, else `dashboardPathFor(user)`: overseas counselor → `/overseas/counselor/dashboard`, OA → `/overseas/admin/dashboard`, SA → `/admin` (`web/lib/navigation.ts:40-83`, `LoginForm.tsx:40`).
- **Errors (verbatim):** wrong email/password or **deactivated** account → `Invalid credentials` (401; the query filters `active = true`). Right password but wrong portal, for example an IT counselor at `/overseas/login` → `Use the correct EduSphere portal for this account: sign in at /it/login` (403). SA may sign in at any portal (`api/app/api/auth.py:108-118`).
- **Screenshot prereq:** active overseas counselor with a set password, and ENVIRONMENT=production (or crop) to hide the demo box.

### DOC-CNS-AUTH-002 Welcome / set-password link (first access)
- A counselor never chooses a first password. An admin creates the account (ADM-001). The API stores an unusable hash and emails a single-use **72-hour** link `…/overseas/reset-password?token=…` (`api/app/services/provisioning.py:37,71-75,120-133`).
- **Email:** subject `Welcome to EduSphere -- set your password` (`api/app/services/mailer.py:~328`), invited-by name, role, expiry.
- **Set-password page:** `/overseas/reset-password` — heading **Choose a new password**, field **New password** ("Use at least 10 characters."), button **Reset password** ("Resetting…"). On success the user goes to `/overseas/login` (`web/components/ResetPasswordForm.tsx:25-62`). Using a welcome link also marks the email verified (`auth.py:~462`).
- **Errors:** `Password must be at least 10 characters`, `Password must be at most 128 characters` (422). An unknown, used, expired, superseded **or deactivated-account** link gives `Reset token is invalid or expired` (400), followed by a **Request a new reset link** link. If the token is missing: "This reset link is missing its token. Request a new one from the forgot-password page." Network error text: "Network error -- we could not confirm whether your password was saved. Try signing in; if that fails, use this link again or request a new one."

### DOC-CNS-AUTH-003 Forgot / reset password
- **Route:** `/overseas/forgot-password` (from **Forgot your password?**). Heading **Reset your password**, "Enter the email on your Overseas Education account and we'll send reset instructions." Field **Email**, button **Send reset instructions** ("Sending…").
- **Always** shows: "If an account exists for that email, we've sent instructions to reset the password." (anti-enumeration). Inactive accounts get no email (`auth.py:392-419`).
- **Email:** subject `Reset your EduSphere password`. The link expires in 30 minutes. An in-app notice "Password reset requested" / "Use the link we emailed you to reset your password. It expires in 30 minutes." is also created. Sends are rate-limited per window and fail silently with the same response.
- The reset page is the same as AUTH-002.

### DOC-CNS-AUTH-004 Change password
- **Route:** `/account/password`, a shared page in the public site shell. Reached via sidebar footer **Change password**, or the first item of the mobile menu. Has "← Back to dashboard" and "Signed in as {name} ({email})." (`web/app/account/password/page.tsx:53-66`).
- Fields **Current password**, **New password** ("Use at least 10 characters."), button **Change password** ("Changing…"), link **Forgot your current password?** → `/overseas/forgot-password`.
- **Messages:** success "Your password was changed."; `Incorrect current password` (400); `New password must be different from the current password` (422); after 5 wrong attempts in 15 min: `Too many incorrect attempts; try again in {n} seconds` (429). A change cancels any unused reset links (`auth.py:477-509`). Signed out: "Your session has expired. Sign in again to change your password."

### DOC-CNS-AUTH-005 My profile
- **Route:** `/account/profile` (sidebar **My profile**). Heading **Your profile**. Fields **Full name** and **Phone**, button **Save changes** → "Your profile was updated." A **Notifications** section has channel preferences ("Choose where we send updates about results, sessions and applications."). A counselor's name is editable. Only telecaller and partnership-manager names are locked (`web/app/account/profile/page.tsx:70`).

### DOC-CNS-AUTH-006 Sign out / session end / deactivated counselor
- **Sign out:** sidebar footer button **Sign out** → POST `/auth/logout`, then to `/` (`web/components/PortalShell.tsx`).
- **Deactivated while signed in:** every API call loads only `active` users (`api/app/api/deps.py:55-60`). The next request gets 401 and pages show the access-unavailable or sign-in card. Login then fails with `Invalid credentials`, and forgot-password sends nothing.
- **Product finding candidate:** the mobile menu (below 980 px the sidebar is `display:none`, `web/app/globals.css:12`) lists Change password, My profile and the nav items but **no Sign out** (`PortalShell.tsx` PortalMobileNav items, `web/components/PortalMobileNav.tsx`). On a phone or tablet a counselor cannot sign out.

## 2. NAV: shell (high level)

### DOC-CNS-NAV-001 Portal shell, sidebar, top bar, mobile menu
- **Sidebar (≥980 px):** logo, role pill **Counselor** + full name, nav (`PORTAL_NAV["overseas/counselor"]`: Dashboard, Tasks, Students, Leads, Documents, Applications, Universities, School Applications, Visa, Appointments, Calendar, Counselor Chat, Reports, Archived Students, then **Management tasks** → `/account/management-tasks`). Footer: **Change password**, **My profile**, **Sign out** (`web/lib/navigation.ts:292`; another pass details the items).
- **Top bar:** "EduSphere Portal", the user's name (truncated), and an unread badge if any nav item has one. No "Student search" header box for the counselor, because only admin navs carry `/student-search` (`PortalShell.tsx` TopbarStudentSearch).
- **Mobile (<980 px):** hamburger (`portal-mobile-menu`) opening a panel with Change password, My profile and every nav item (see AUTH-006 finding).
- Unknown section under `/overseas/counselor/<x>` → Next 404. A wrong role on a portal page → access card. A null payload for a non-SA → "Workspace not found" card (`web/components/PortalPage.tsx:4,29`).

### DOC-CNS-NAV-002 IT counselor separation (out of scope, noted)
- Same role key `counselor` with division `it`: lands on `/it/counselor/dashboard` (`navigation.ts:80-83`). Its nav is Dashboard/Leads/Appointments only. The Overseas action forms return `[]` (`WorkflowPanel.tsx` `specsFor`). Walk-in students and leads, the performance report, and the reminder first-contact tasks are overseas-only (API 403 `Only an overseas counselor can …`; `first_contact` skips non-overseas leads). Login at the wrong portal gives the AUTH-001 403 message.

## 3. ADM: user provisioning, walk-ins, reassignment

### DOC-CNS-ADM-001 Create a counselor account (admin)
- **OA:** `/overseas/admin/users` (sidebar **Users**) or `/overseas/admin/counselors` (**Counselors**). **SA:** `/admin/users` (or `/admin/staff`).
- **Form "Create user"** (`web/components/WorkflowPanel.tsx:389`): **Full name***, **Email***, **Phone**, **Division*** (select), **Role*** (select). OA: Division is locked to `overseas`, and Role offers `overseas_student, counselor, university_rep, agent, overseas_admin`. SA: Division `it | overseas | global`, **default `it`**, and Role is the de-duplicated union (`counselor` appears once, so the division decides IT vs Overseas) (`WorkflowPanel.tsx:358-385`).
- **Success:** "User created. A set-password link was emailed and is valid for 72 hours." If mail fails or is not configured: "User created. The email was not delivered (email is not configured on this server | the email could not be sent). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page." (`web/lib/welcomeLink.ts:11-20`).
- **Errors:** `Email already exists` (409); `Cannot create users in another division` (403, OA sending another division); `Role is not valid for the selected division` (422) (`api/app/api/admin.py:644-~780`).
- **Product finding candidate:** for SA the Division defaults to **IT**. An SA who picks Role = counselor and leaves the default creates an **IT** counselor who cannot sign in at `/overseas/login`.

### DOC-CNS-ADM-002 Manage users: setup status, re-send link, edit, deactivate/reactivate
- **Panel "Manage users"** (`web/components/AdminUserManagementPanel.tsx`): search box "Search by name, email, role, or Student ID", **Account setup** filter (**All accounts / Awaiting setup / Link expired**), and a table **Name · Email · Role · Status · Action**. Status shows Active/Inactive plus "Awaiting setup" or "Link expired". Actions: **Edit details** (Full name, Phone, Education, Skills (comma separated) → **Save details**, "Details updated."), **Deactivate** → **Confirm deactivate** / **Reactivate**, **Re-send link** ("Sending…").
- **Who sees it:** SA on `/admin/users|students|trainers|counselors|staff`. **OA only on `/overseas/admin/users`**. On `/overseas/admin/counselors` the OA gets the read-only portal table (reference, Name, Email, Role, Active, Setup = Password set / Awaiting setup / Link expired) plus the Create form, but **no** deactivate or re-send (`WorkflowPanel.tsx:463`, `api/app/services/portal.py:100,1583-1615`).
- **Re-send errors:** `This account has no pending invitation (its password is already set)` (409), `Reactivate this account before re-sending its link` (409), `A link was just sent; wait {n} seconds before re-sending` (429), `Cannot manage another division` (403) (`admin.py:879-903`). Success: "New link created for {name}. A set-password link was emailed and is valid for 72 hours."
- **Deactivate:** success "{name} deactivated." / "{name} reactivated." Any change to active/inactive revokes open welcome links. `Cannot edit another division` (403).
- **Product finding candidate:** deactivating a **counselor** has **no guard or handover**. BDMs, telecallers, partnership managers and recruiters are refused while they hold open work (`admin.py:839-850`), and trainers prompt for a cascade. A counselor's leads, csc-001 students, applications and tasks stay on an inactive owner. Only ccrm-031 escalation flags the overdue part (`counselor_reminders.py:242` "escalates a deactivated counselor's work too").

### DOC-CNS-ADM-003 Counselor adds a walk-in student login (csc-001/002)
- **Route:** `/overseas/counselor/students`, section **My students** ("Your walk-in students, converted leads and the students of the applications assigned to you."). Form **Add a walk-in student**: **Full name**, **Email**, **Phone (optional)** → **Create account** ("Creating…") (`web/components/CounselorWalkInStudents.tsx:60-150`, shown only to overseas counselors, `WorkflowPanel.tsx:458`).
- Creates an `overseas_student` with a Student ID, links it to the counselor (`OverseasStudentCounselor`, csc-001), and emails the 72 h welcome link (`api/app/services/counselor_students.py:122-142`).
- **Success:** "Account created for {name}. A set-password link was emailed to {email}." / "Account created for {name}, but the set-password email was not delivered."
- **Errors:** `Email already exists` (409, audited); mail budget `You have sent 20 account emails in the last 24 hours. Try again later.` (429, counts creates, resends and email changes); IT/other role `Only an overseas counselor can add walk-in students` (403).
- List filters: Search ("Name, email or phone"), **Source** (All sources / Walk-in / Lead conversion / Self-registered / Agency). Empty: "No students yet. Add a walk-in student below."

### DOC-CNS-ADM-004 Resend / fix a pending walk-in (csc-003)
- Row badges "Set-up pending" / "Link expired". Actions **Resend link** ("Sending…"), **Edit** (Full name, Email, Phone (optional); hint "Changing the email sends a new link to the new address; the old link stops working."), plus **Open**, **Notes**, **Profile** (`web/components/CounselorWalkInStudentRow.tsx`).
- **Errors:** `This student has already set a password` (409), `This account is deactivated` (409), `A link was just sent; wait {n} seconds before re-sending` (429). If mail fails: "A new set-password link was created, but the email was not delivered. Try Resend link in a minute."

### DOC-CNS-ADM-005 Counselor records a walk-in lead (csc-004)
- `/overseas/counselor/leads` → button **New walk-in lead** → `/overseas/counselor/leads/new`. Intro "Leads telecallers handed to you and walk-ins you recorded." Uses tel-005 intake with a duplicate check. The lead's owner is the counselor (`web/components/CounselorLeadsPanel.tsx:107-112`, `api/app/api/counselor_walk_in_leads.py`). Error `Only an overseas counselor can record walk-in leads` (403). The form itself is covered by the leads pass.

### DOC-CNS-ADM-006 OA assigns / changes a student's counselor (csc-005 + ccrm-033)
- **Route:** `/overseas/admin/users`. Overseas-student rows get the column **EduSphere counsellor** (name or "Not assigned") and a button **Assign counsellor** / **Change counsellor**, plus links to the 360 view (Open), Notes and Profile (`portal.py:1592-1614`, `web/components/DataTable.tsx:31-34`).
- **Dialog:** type-ahead **EduSphere counsellor** (active overseas counselors), **Reason for the change** (required when replacing) or **Reason (optional)** (first assignment). Success "{counselor} assigned." (`web/components/AssignCounselorButton.tsx`).
- **Errors:** `Give a reason for the reassignment` (422), `Choose an active overseas counselor` (422), `Student not found` (404), `Only the Overseas Admin can assign a counselor` (403, **SA included**) (`counselor_students.py:45-61,219-246`).
- **Notices:** new counselor "Student assigned to you" / "{student} is now one of your students. Reason: …". Previous counselor "Student reassigned" / "A student has moved to another counselor. Reason: …". The reason goes to the audit log and the student 360 History.

### DOC-CNS-ADM-007 OA assigns / changes an application's counselor (AGN-023 + ccrm-033)
- **Route:** `/overseas/admin/applications` and `/overseas/admin/students` (application lists), plus `/overseas/admin/school-applications`. Columns **EduSphere counsellor** + assign control. Closed (withdrawn/enrolled) rows have no control. The list filter accepts `counselor=<id>|none` for unassigned (`portal.py:1170-1180,1420-1434`, `api/app/services/application_filters.py:36,101`).
- Same dialog as ADM-006. Endpoint PUT `/workflows/overseas/applications/{id}/counselor`. Errors `This application is closed` (409), `Application not found` (404), `Choose an active overseas counselor` (422), `Only the Overseas Admin can assign a counselor` (403) (`api/app/api/workflows.py:2626-2660`).
- **Notices:** "Application assigned to you" / "{owner} — {university}" (+ Reason), link `/overseas/counselor/applications`. Previous: "Application reassigned".

### DOC-CNS-ADM-008 Lead owner (counselor) change by admin (ccrm-003 A7 / ccrm-033)
- **API only:** PATCH `/admin/leads/{id}` with `owner_id` + `owner_reason`. Notices "Lead assigned to you" / "{code} is now yours." and "Lead reassigned" (`admin.py:566-590`, `api/app/services/lead_handover.py:73-94`). Error `Give a reason for the reassignment`.
- **Product finding candidate:** **no UI sends `owner_id`/`owner_reason`**. The admin Leads table (`web/components/AdminLeadManagementPanel.tsx:176-215`) has no counselor column or control, and `owner_id` appears only as a **Counselor** filter (`AdminLeadFilters.tsx:83`). An admin cannot move a lead between counselors from the UI.

## 4. ESC: escalation and admin task oversight

### DOC-CNS-ESC-001 Counselor tasks — admin view (ccrm-029)
- **Route:** `/overseas/admin/counselor-tasks` (sidebar **Counselor tasks**). Heading **Counselor tasks**, "Every overseas counselor's tasks: {n} overdue · {n} due today · {n} upcoming. The counselor is notified of a task you add or change." (`web/app/overseas/admin/counselor-tasks/page.tsx:35-75`).
- **Add a task** (`CounselorTaskForm` admin mode): **Title** ("Give the title (2-200 characters)"), **Counselor** ("Choose a counselor" → "Choose the counselor"), **Due date** ("Choose the due date", "The due date can't be in the past"), **Priority**, **About (optional)** (lead/student/application of that counselor; "Choose the counselor first" / "Nothing in particular"). Button **Add task** → "Task added."
- **Filter:** **Counselor** (All counselors), **Show** (Open and recently done / Overdue / Today / Upcoming / Done (last 7 days) / Cancelled), **Apply**, **Clear**. Row actions **Mark done / Reopen / Edit / Cancel task** ("Cancel this task? It can't be reopened." → **Yes, cancel it** / **Keep it**). Empty: "No counselor has an open task." / "No tasks match these filters." Capped list: "Showing the first {n} of {total} tasks. Filter by counselor to see the rest."
- Roles: OA and SA (page and API). Others get the card "Overseas Administrator role required".

### DOC-CNS-ESC-002 Overdue by counselor + escalation notice (ccrm-031)
- Same page, section **Overdue by counselor** (`#overdue`): "{n} counselors behind"; "Work overdue by more than {N} days is escalated to every Overseas Admin once." (or "Escalation is switched off.") "Change it in Reminder rules." Table **Counselor · Overdue tasks · Overdue follow-ups · Oldest due · Actions (View tasks)**. Empty: "No counselor has overdue work." (`web/components/OverdueByCounselor.tsx`).
- **Notice** (daily job): title `Overdue work escalated`, body "{counselor}: {n tasks and n follow-ups} overdue by more than {N} days.", link `/overseas/admin/counselor-tasks#overdue`. Sent once per item to **every active OA, never SA** (`api/app/services/counselor_reminders.py:450-520`). Default threshold 2 days (range 2–30). Includes deactivated counselors' work.

## 5. PERF: counselor performance (admin)

### DOC-CNS-PERF-001 Team performance
- **Route:** `/overseas/admin/counselor-performance` (sidebar **Counselor performance**). Heading **Counselor performance**, "Each overseas counselor's leads (Overseas and IT), conversions, students, applications, visas and enrolments. Open a counselor for their full report." Period (**From**/to, **Show** "This month"), **Lead division** (All divisions), intake filters. Table "Overseas counselors' performance" with **Counselor**, team figures (Leads, Overseas leads, IT leads, …, Students, Offers, Visas pending/approved/refused, Enrolments) and a **Total** row. Export **CSV/XLSX** ("Export counselor performance"). Empty: "No overseas counselors yet." (`web/app/overseas/admin/counselor-performance/page.tsx`, `api/app/services/counselor_performance.py:32-56,162-165`).
- Roles: OA, SA (`api/app/api/counselor_performance.py:32,53-56`; refusal "Overseas Administrator role required").

### DOC-CNS-PERF-002 One counselor's report
- **Route:** `/overseas/admin/counselor-performance/[id]`. Eyebrow "Counselor performance", heading "{name}" (+ " (inactive)"), link **Back to all counselors**. Body is the counselor's own report, including **Applications by stage and sub-status** (Stage · Sub-status · Applications · Students). Empty: "No applications are assigned to {name} yet." A non-counselor ID shows the not-found error. The counselor's self-view is `/overseas/counselor/reports` (other pass).

## 6. CFG: templates and configuration

### DOC-CNS-CFG-001 Document checklist templates (ccrm-018)
- **Route:** `/overseas/admin/checklists` (**Document checklists**). Intro: "The documents an application needs, by country and optionally university, course level and intake. Counselors work from the most specific matching template." Filter **Checklist for** (Admission and visa / Admission / Visa) and a status filter; list columns Documents · Gate · Version.
- **Editor** "New checklist template": **Name**, **Checklist for**, **Country**, **University (optional)**, **Course level (optional)** (Any level / UG / PG / PhD / Diploma / Foundation), **Intake (optional)**, **When documents are missing at Ready for Submission** (Block until complete / Warn (override with a reason)), **Notes (optional)**. Items: **Document type** (Passport, Academic certificates, Transcripts, English test, CV, SOP, LOR, Financial documents, Offer letter, Other), Document name / Label (optional), **Sensitivity**, **Allowed statuses (none ticked = the standard nine)**, **Item notes (optional)**. Buttons **Create template** / **Save changes** → "Created" / "Saved" (`web/components/ChecklistTemplateEditor.tsx`, `web/lib/documentChecklists.ts:10-13`).
- **Errors:** `Checklist template not found`; concurrent edit `Someone else saved this template since you opened it; reload to see their changes`; duplicate scope (409). Writers: OA (+SA via `_require` bypass). Counselors read only (`api/app/api/document_checklists.py:28-30`).

### DOC-CNS-CFG-002 Reminder rules (ccrm-030)
- **Route:** `/overseas/admin/reminder-rules` (**Reminder rules**). Intro "Turn lead and application dates into counselor tasks and reminders. Agency partners keep their own deadline reminders; students are reminded only on direct applications, through the channels they opted in to."
- One card per rule (badge "Task + notice" or "Notice"): New lead assigned; No response after contact; Document request overdue; Application deadline approaching; University decision overdue; Offer deadline approaching; Deposit due; Offer condition due; Visa appointment approaching; On-hold review date; Overdue work escalation. Fields: days offset (min–max hint), **Rule is on**, and on some rules **Also remind the student (direct students only)**. Button **Save** → "Saved."; field error "Choose from {min} to {max} days" (`api/app/services/counselor_reminders.py:78-91`, `web/components/ReminderRules.tsx`).
- **Run reminders now:** "The job runs every day at 08:15 IST. Running it now never sends a reminder twice — use it to test the rules with sample records." Plus **Recent reminders** (When · Rule · About · Task · Told). Scheduled by Celery beat `crontab(2:45 UTC)` (`api/app/worker.py:261`).

### DOC-CNS-CFG-003 Counselor message templates (ccrm-037)
- **Route:** `/overseas/admin/message-templates`. "WhatsApp and email messages counselors start from when they write to a student … Deactivate a template to hide it — it is never deleted." Reuses `RecruiterTemplatesPanel`. OA and SA.

### DOC-CNS-CFG-004 Archived students — admin restore (ccrm-040)
- **Route:** `/overseas/admin/archived-students`. "Every archived overseas student. Restore one to put them and their applications back in the working lists." Restore is OA-only. The counselor's page says "Your archived students. The Overseas Admin can restore them." Consents are student-only: nobody consents on a student's behalf, and admins and counselors see them on the 360 Overview (RBAC §2.190).
- **Page gate is `overseas_admin` only.** SA gets "Overseas Administrator role required" (`web/components/ArchivedStudentsPage.tsx:13-27`).

### DOC-CNS-CFG-005 Not configurable (record for docs)
- Application sub-statuses and outcomes are fixed in code (`api/app/application_sub_status.py:4`). No admin screen for them.
- Commission (dtu-001 university-level, ccrm-051 per-course `agent_commission_percent`) is set by SA/OA only. **Counselors never see commission**: the University 360 slices have no commission data (`api/app/services/university_view.py:4-9`).
- Lead lost-reason catalogue owner: `NEEDS_CONFIRMATION` (likely the telecaller manager catalogue, tel-002).

## 7. HO: handoffs into the counselor

### DOC-CNS-HO-001 Telecaller hands a lead to a counselor (tel-018)
- **Who:** the lead's telecaller (until handed over), their manager, or SA. POST `/telecaller/leads/{id}/handover` (`api/app/api/lead_handover.py:57`).
- **Telecaller UI** (`web/components/LeadHandoverForm.tsx`): **Assign to counselor** / **Change counselor** → **Counselor** ("Choose a counselor"), hint "The counselor takes over the lead. You keep read access and its open follow-ups are cancelled." → **Hand over** ("Handing over…"). Empty: "No other active counselor in this division."
- **Rules and errors:** `This lead is closed; reopen it before handing it over`, `This lead is already past the counselor handover`, `This lead is already with this counselor` (409). Open follow-ups are cancelled with reason "Handed over to counselor" (`api/app/services/lead_handover.py:24-63`).
- **Counselor side:** the lead appears in **Leads** (`/overseas/counselor/leads`). The counselor can **return** it to the telecaller (reason required; `Unlink the student before returning the lead`), link a student, or convert (ccrm-008). Detail is in the leads pass.
- **Product finding candidate:** the handover itself sends the counselor **no notice**. The only signal is the `first_contact` reminder ("New lead assigned" / "{code}: a new lead was assigned to you. First contact is due {date}." + task). If an admin turns that rule off, a handed-over lead arrives silently (`counselor_reminders.py:581-606`). The admin owner change (ADM-008) does notify.

### DOC-CNS-HO-002 Public enquiry → lead → counselor
- Website, telecaller-intake and BDM enquiries become leads in the telecaller pipeline (tel-005/007 distribution). The only automatic owner is the creator of a counselor walk-in (`api/app/services/lead_intake.py:151`). A public enquiry reaches a counselor only through HO-001 (or ADM-008 via API). Distribution rules are in the telecaller docs.

### DOC-CNS-HO-003 Agency (agent) students and applications (CC4, AGN-023)
- Agency applications are created without a counselor (`counselor_id` set only when a counselor or admin creates one, `workflows.py:2464-2472`, `admin.py:2193`). The OA assigns via ADM-007, and the counselor is notified "Application assigned to you". The counselor's lists then show an **Agency** column. Per CC4 the counselor records offers, visa and enrolment on agency applications too. Agency students show Source "Agency" in **My students**.
- Agents see the counselor change but not the reason (RBAC §2.185).
- **Product finding candidate:** there is no alert to the OA that a new agency application is unassigned. Monitoring depends on filtering `counselor=none` (`NEEDS_CONFIRMATION`: whether any notice exists elsewhere, since none was found in `services/agent_applications.py`).

### DOC-CNS-HO-004 Self-registered students
- `/overseas/register` students have no csc-001 counselor link until the OA assigns one (ADM-006), or until an application is assigned (ADM-007, application scope only).

---

## 8. Super Admin vs Overseas Admin

| Capability | OA | SA | Evidence |
|---|---|---|---|
| Create counselor | `/overseas/admin/users` or `/counselors`, division locked | `/admin/users`, division default **IT** | `WorkflowPanel.tsx:375-389` |
| Manage users panel (deactivate/re-send) | `/overseas/admin/users` only (not `/counselors`) | all `/admin/*` user sections | `WorkflowPanel.tsx:463` |
| Student counselor column + assign | ✅ | ❌ column absent, API 403 | `portal.py:1592`; `counselor_students.py:223` |
| Application counselor assign | ✅ | ❌ 403 | `workflows.py:2632` |
| Counselor tasks / overdue list | ✅ | ✅ (URL only, not in SA nav) | `counselor-tasks/page.tsx:17` |
| Escalation notice | ✅ receives | ❌ never | `counselor_reminders.py:473-476` |
| Performance, checklists, reminder rules, message templates | ✅ | ✅ by URL; page shows OA nav and role pill "Overseas Administrator" | each `page.tsx` hard-codes `PORTAL_NAV["overseas/admin"]` |
| Archived students / restore | ✅ | ❌ "Overseas Administrator role required" | `ArchivedStudentsPage.tsx:27` |
| `/overseas/admin/<section>` portal pages | ✅ | payload served (`api/portal.py:43`); null payload → blank main, no "Workspace not found" card (that card is non-SA only) | `PortalPage.tsx:29` |

None of the counselor-admin pages (Counselor tasks, Counselor performance, Document checklists, Reminder rules, Archived students, Message templates) is in `SUPER_ADMIN_NAV` (`navigation.ts:323`).

## 9. Product finding candidates (ranked)
1. **No Sign out on mobile/tablet** (<980 px): `PortalMobileNav` omits it and the sidebar is hidden (`globals.css:12`, `PortalShell.tsx`). Affects every portal.
2. **Counselor deactivation has no handover or guard.** Leads, students, applications and tasks stay on an inactive counselor (`admin.py:839-850`, unlike BDM/telecaller/recruiter).
3. **Lead owner reassignment (ccrm-003 A7 / ccrm-033) is API-only.** No admin UI sends `owner_id`/`owner_reason` (`AdminLeadManagementPanel.tsx`).
4. **SA create-user defaults Division to IT**, so a counselor created there is an IT counselor locked out of `/overseas/login` (`WorkflowPanel.tsx:389`).
5. **Telecaller handover sends no direct notice.** It depends on the `first_contact` rule being on (`lead_handover.py:46-63`).
- Also: OA's `/overseas/admin/counselors` lacks the deactivate/re-send panel; SA sees counselor-admin pages with the OA nav and pill but cannot restore archives or reassign; SA is never escalated to; the login error for a deactivated account is the generic `Invalid credentials`.

## 10. Undetermined (NEEDS_CONFIRMATION)
- Whether the OA is told when an agency application arrives unassigned.
- Owner of the lead lost-reason catalogue.
- Exact SA rendering of `/overseas/admin/users` (payload served without the counselor columns; not browser-verified).
- Screenshot data needed: 1 OA, 1 SA, 2 active overseas counselors (one with overdue tasks older than 2 days and overdue follow-ups), 1 deactivated counselor, 1 walk-in with "Set-up pending", 1 with "Link expired", 1 self-registered student without a counselor, 1 agency application unassigned, 1 telecaller lead at a pre-application stage, 1 checklist template, and a reminder log with entries.
