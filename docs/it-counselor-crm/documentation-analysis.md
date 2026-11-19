# EduSphere IT Counselor CRM — Documentation Analysis (Phase 1)

> Code baseline: `main` @ `6b61546c` (2026-11-18). Source of behaviour: the code, then confirmed in the browser before a page is written.
> Backlog context: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` (itc-001..033, UNVERIFIED source; items marked `NEEDS_CONFIRMATION` there stay provisional here).

## 1. Application Overview

### 1.1 What the IT Counselor CRM is
The IT Counselor is the EduSphere staff member who takes IT-division enquiries from the telecaller, counsels the lead,
converts them into an IT student enrolled on a batch, and then follows that student through fees, training progress,
risk and the HR resume review. In the code it is role `counselor` with division `it` (tel-017). Overseas counselors share
the role but use a different portal (documented in `docs/counselor-crm/`).

### 1.2 Technology (from code)
Next.js 15 web (`apps/web`), FastAPI api (`apps/api`), PostgreSQL, Celery worker + beat, Docker Compose.

### 1.3 Authentication and landing
- Sign in at `/it/login`. `dashboardPathFor()` (`apps/web/lib/navigation.ts`) sends `counselor` + division `it` to `/it/counselor/dashboard`.
- Account pages outside the sidebar: `/account/profile` (contact preferences, itc-033 "No phone calls") and `/account/password`.
- New accounts get a welcome email with a set-password link (IT Admin can **Re-send link**).

### 1.4 Cross-cutting rules to explain in every manual
- **Scope.** An IT counselor sees only *their* leads (`Enquiry.owner_id`) and *their linked* IT students (itc-003). Anything else returns "not found".
- **No permission keys.** Access comes from role + division checks, not from RBAC keys (`core/rbac.py` lists overseas keys only).
- **Configurable stage names.** Lead and lifecycle stage labels come from IT Admin **Status Labels** (itc-005); screenshots show the default labels.
- **Derived overdue.** Fee "overdue" is calculated from due dates, not stored (itc-016).
- **Read-only lifecycle.** Only the IT Admin can set a student's lifecycle stage by hand (itc-031).
- **Email off = still recorded.** In-app notices are created even when email is not configured; conversion then says the set-password email was not delivered.

## 2. Module Inventory
| Module | Folder | Who |
|---|---|---|
| Account access | `account-access` | IT Counselor |
| Navigation | `navigation` | IT Counselor |
| Dashboard | `dashboard` | IT Counselor |
| Leads | `leads` | IT Counselor |
| Appointments | `appointments` | IT Counselor |
| Conversion and enrolment | `conversion` | IT Counselor |
| Students | `students` | IT Counselor |
| Fees | `fees` | IT Counselor |
| Resume and HR review | `resume-hr` | IT Counselor |
| Notes | `notes` | IT Counselor |
| Timetable, notifications, management tasks | `timetable`, `notifications`, `tasks` | IT Counselor |
| Counselor administration | `admin` | IT Admin, Super Admin |
| Handoffs | `handoffs` | Telecaller, Telecaller Manager, HR, Student |

## 3. Feature Inventory (62 Doc IDs)
Doc IDs: `DOC-ITC-<MOD>-NNN`. User-manual pages go to `user-manual/<module>/`, admin pages to `admin-manual/<module>/`.

| Doc ID | Feature | Route / component | itc |
|---|---|---|---|
| DOC-ITC-AUTH-001 | Sign in to the IT portal | `/it/login` | – |
| DOC-ITC-AUTH-002 | Set your first password from the welcome email | welcome link | – |
| DOC-ITC-AUTH-003 | Forgot / reset your password | `/it/login` | – |
| DOC-ITC-AUTH-004 | Change your password | `/account/password` | – |
| DOC-ITC-AUTH-005 | My profile and contact preferences | `/account/profile` | 033 |
| DOC-ITC-AUTH-006 | Sign out, ended sessions, deactivated account | – | – |
| DOC-ITC-NAV-001 | Portal tour: 8-item sidebar, top bar, mobile menu | `navigation.ts` `it/counselor` | – |
| DOC-ITC-DASH-001 | Counselor dashboard widgets and recent leads | `/it/counselor/dashboard` | 030, 023, 027 |
| DOC-ITC-DASH-002 | Filter the dashboard (course, batch, status, dates) | `ItCounselorDashboardFilters` | 030 |
| DOC-ITC-LEAD-001 | My leads list and filters | `/it/counselor/leads` | tel-018, 005 |
| DOC-ITC-LEAD-002 | Lead detail page layout | `CounselorLeadDetail.tsx` | – |
| DOC-ITC-LEAD-003 | View and edit lead details | Lead details → **Edit details** | 004 |
| DOC-ITC-LEAD-004 | Set the next action | "Set the next action" | – |
| DOC-ITC-LEAD-005 | Change a lead's stage | stage control | 005 |
| DOC-ITC-LEAD-006 | Lead qualification form | qualification form | – |
| DOC-ITC-LEAD-007 | Add and complete follow-ups | **Add follow-up** | 009 |
| DOC-ITC-LEAD-008 | Log, edit and delete calls | **Log call** | – |
| DOC-ITC-LEAD-009 | Send a WhatsApp message | **Send WhatsApp** | – |
| DOC-ITC-LEAD-010 | Send an email to a lead | **Send email** | – |
| DOC-ITC-LEAD-011 | Record a meeting | **Record meeting** | – |
| DOC-ITC-LEAD-012 | Record a counseling session | **Record counseling** | 010 |
| DOC-ITC-LEAD-013 | Return a lead to the telecaller | **Return to telecaller** | – |
| DOC-ITC-LEAD-014 | Lead notes and activity timeline | Notes, Activity | – |
| DOC-ITC-LEAD-015 | Milestones panel | Milestones | – |
| DOC-ITC-APPT-001 | Lead appointments | `/it/counselor/appointments` | tel-016 |
| DOC-ITC-CONV-001 | Convert a lead to a new IT student | **Convert to IT student** → **Convert and enrol** | 011 |
| DOC-ITC-CONV-002 | Convert a lead into an existing student account | "Enrol existing student" option | 011 |
| DOC-ITC-CONV-003 | Onboarding checklist after conversion | checklist | 011 |
| DOC-ITC-CONV-004 | Link or unlink a student on a lead | Link / **Unlink student** | tel-018 |
| DOC-ITC-CONV-005 | Enrol an existing Overseas student in IT | `/it/counselor/enrol-existing` | ENH-033 |
| DOC-ITC-STU-001 | My students list | `/it/counselor/students` | 003, 013 |
| DOC-ITC-STU-002 | Student 360 | `/it/counselor/students/[id]` | 029, 022 |
| DOC-ITC-STU-003 | Student record: personal, emergency contact, enrolments | `.../profile` | 012, 014 |
| DOC-ITC-STU-004 | Risk and lifecycle cards | `.../profile` | 023, 031 |
| DOC-ITC-FEE-001 | Fee summary and installments | Fees and reminders | 013 |
| DOC-ITC-FEE-002 | Request a discount | **Request discount** | 015 |
| DOC-ITC-FEE-003 | Overdue fees and reminders sent | Fees and reminders | 016 |
| DOC-ITC-RES-001 | Upload a resume and new versions | **Upload resume** | 026 |
| DOC-ITC-RES-002 | HR review status card | HR review | 027 |
| DOC-ITC-NOTE-001 | Student notes: add, share with student, stop sharing | `.../notes` | 028 |
| DOC-ITC-TT-001 | Timetable | `/it/counselor/timetable` | 020 |
| DOC-ITC-NOTIF-001 | Notifications | `/it/counselor/notifications` | 002, 025 |
| DOC-ITC-TASK-001 | Management tasks | `/account/management-tasks` | – |
| DOC-ITC-ADM-001 | Create an IT counselor account | `/it/admin/counselors`, `/it/admin/users` | – |
| DOC-ITC-ADM-002 | Edit, deactivate, reactivate, re-send link | `/it/admin/users` | – |
| DOC-ITC-ADM-003 | Assign or change a student's counselor | `/it/admin/students` | 003 |
| DOC-ITC-ADM-004 | Resume upload limit | `/it/admin/students` | 026 |
| DOC-ITC-ADM-005 | IT Counselor Dashboard with the Owner filter | `/it/admin/counselor-dashboard` | 030 |
| DOC-ITC-ADM-006 | Admin leads: convert, change stage, link | `/it/admin/leads` | 004, 011 |
| DOC-ITC-ADM-007 | Merge a duplicate lead | `/it/admin/leads` | 007 |
| DOC-ITC-ADM-008 | Record payments, refunds and corrections | `/it/admin/payments` | 013, 014 |
| DOC-ITC-ADM-009 | Approve or reject a discount | `/it/admin/payments` | 015 |
| DOC-ITC-ADM-010 | Fee reminder schedule | `/it/admin/payments` | 016 |
| DOC-ITC-ADM-011 | At-risk thresholds and flagged students | `/it/admin/at-risk` | 023 |
| DOC-ITC-ADM-012 | HR review assignment and rules | `/it/admin/hr-reviews` | 027 |
| DOC-ITC-ADM-013 | Status labels for lead and lifecycle stages | `/it/admin/status-labels` | 005 |
| DOC-ITC-ADM-014 | Overdue follow-up escalation (hours + notices) | `/telecaller/manager/alerts`, `/it/admin/notifications` | 009 |
| DOC-ITC-ADM-015 | Set a student's lifecycle stage; audit log | `.../profile`, `/it/admin/audit-log` | 031, 001 |
| DOC-ITC-HO-001 | Telecaller hands a lead to an IT counselor | `/telecaller/leads/[id]` | tel-018 |
| DOC-ITC-HO-002 | Telecaller Manager changes the counselor | `/telecaller/leads/[id]` | – |
| DOC-ITC-HO-003 | What the student sees (counselor, updates, fees, resume) | `/it/student/*` | 018, 028 |
| DOC-ITC-HO-004 | HR works the resume review | `/it/hr/queue` | 027 |

## 4. User Role Inventory
| Role | Code | Portal |
|---|---|---|
| **IT Counselor** | `counselor`, division `it` | `/it/counselor/*` |
| **IT Admin** | `it_admin` | `/it/admin/*` |
| **Super Admin** | `super_admin` | `/admin/*` (creates IT counselors, approves discounts, sets escalation hours) |
| **Telecaller / Telecaller Manager** | `telecaller` / manager, team `it` | `/telecaller/*` (handoff only) |
| **HR** | `hr_team` | `/it/hr/queue` (handoff only) |
| **Student** | IT student | `/it/student/*` (handoff only) |

## 5. Role differences worth a "What each role sees" table
- Counselor dashboard (Counselor) vs IT Counselor Dashboard with **Owner** filter (IT Admin).
- Student record: lifecycle read only (Counselor) vs editable (IT Admin).
- Leads: counselor lead page vs IT Admin leads (convert + merge).
- Overseas vs IT counselor sidebar (IT has no Tasks, Documents, Applications, Universities, Visa, Calendar, Chat, Reports, Archived Students; only IT has Timetable and Notifications).

## 6. Background jobs (`apps/api/app/worker.py`)
| Job | When | Shown in |
|---|---|---|
| `itc009-escalations` | every 15 min | ADM-014 (off by default, 0 h) |
| `itc023-at-risk` | 07:00 IST | STU-004, ADM-011, DASH-001 |
| `itc016-fee-reminders` | 08:30 IST | FEE-003 |
| `tel018-conversion-sweep` | every 15 min | CONV-004 (linked lead → Converted) |

## 7. External services in the docs stack
- **Email:** SMTP to local Mailpit only (`itcdocs`, 127.0.0.1:8032). Mailpit is never screenshotted.
- **WhatsApp/SMS:** no provider; **Send WhatsApp** records the send only.
- **Payments:** none recorded (owner I3). Razorpay online payment is described in text only.
- **ClamAV:** off (`CLAMAV_HOST` empty), so resume uploads are not scanned.

## 8. Required Test Data (created through the UI; all `Docs ` prefixed, `@example.test`)
- IT Admin (seeded) creates **Docs IT Counselor A** and **Docs IT Counselor B**, and **Docs IT Telecaller** (team `it`).
- Leads: **Docs IT Lead Arjun** (converted, new account), **Docs IT Lead Bhavna** (converted into existing student), **Docs IT Lead Chirag** (returned), **Docs IT Lead Deepa** (duplicate, merged), **Docs IT Lead Esha** (open, counseling recorded).
- A **Docs** IT programme and batch for conversion and timetable.
- Fees in fictional INR on the Docs batch. No payments, refunds or corrections are recorded (I3, revised); payment screens are captured unsubmitted.
- Sample resume PDF/DOCX from the scratchpad files folder.

## 9. Unknown workflows requiring browser verification
- Exact sidebar labels (title-cased from slugs) and **Management tasks** page content.
- Whether the welcome email link lands on an IT-branded page.
- Counseling objection list (maintained by the telecaller manager) and its effect on the counseling form.
- Onboarding checklist items after conversion.
- Enrol Existing page title and the Overseas-student search.

## 10. Product Findings and Open Questions (owner)
Documented as built, in neutral words; none blocks the docs.
- **P1** No bulk reassign of IT students between counselors; one row at a time on `/it/admin/students`.
- **P2** The IT counselor has no Tasks or Calendar page; follow-ups live on the lead page.
- **P3** No "Export my leads" for the IT counselor (overseas has it).
- **P4** Escalation hours for IT follow-ups are set on the telecaller manager's Alerts page, not in the IT Admin portal.
- **P5** The itc-033 retention policy is a document only; there is no automatic purge.
- **P7** The phone menu has no **Sign out**; use My profile → **Logout** in the public header.
- **P8** **Phone calls from our team** (itc-033) appears on staff profiles too, with student wording.
- **P9** Counselling can be booked only by the lead's telecaller before hand-over; the IT counselor cannot book.
- **P10** IT Admin **Leads** table needs sideways scrolling; **Merge a duplicate** opens inside the narrow Action column.
- **P11** IT Admin **Change counsellor** fails with "Student not found" for a student who joined IT from Overseas (the assign looks up primary IT students only), so their IT counselor cannot be changed.
- **P12** A counselor opening another counselor's student gets the bare "404 This page could not be found." page, with no portal menu or way back.
- **P13** Deactivating an IT counselor leaves their students assigned to the inactive account; nothing prompts the IT Admin to reassign them.
- **P14** The onboarding checklist is never ticked by the system: items the student has done (password set, agreement accepted) stay unticked until a counselor or IT Admin ticks them.
- **P6** itc-002 (event catalogue) and itc-016 (reminder schedule) are still `NEEDS_CONFIRMATION` in the backlog; pages describe current defaults.
