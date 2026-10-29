# EduSphere Overseas Counselor CRM — Documentation Analysis (Phase 1)

> Session S1 · 2026-10-29 · Code baseline `main` @ `045d8c40` · Reviewed from source only (no browser work yet).
> Evidence lives in `discovery/01..04` (file:line references). This file is the summary the plan builds on.

## 1. Application Overview

### 1.1 What the Counselor CRM is
The Overseas counselor works a student from first conversation to arrival abroad:
1. **Leads** come from telecaller handover (tel-018), website enquiries, or walk-ins the counselor records (csc-004).
2. The counselor logs calls, WhatsApp, email, meetings and notes, sets follow-ups and a next action, and moves the lead through its stages.
3. A qualified lead is **converted** to a student account (ccrm-008, reusing the csc-002 welcome link), or linked to an existing one.
4. On the **Student 360** the counselor keeps the structured profile and notes and creates **applications**. They then move each application through its stages and sub-statuses, gated by the document checklist (ccrm-019).
5. The counselor records **offers** and their conditions, **interviews**, **deposits**, the **visa** lifecycle, **enrolment** and **arrival/orientation**.
6. The daily tools are the **Dashboard** (action tiles and quick search), **Tasks**, **Calendar** with an iCal feed, **Reports** (My performance) and **Universities**.
7. The **Overseas Admin** creates counselors, assigns students and applications to them, watches overdue work (escalation), configures checklists, reminder rules and message templates, and restores archived students.

### 1.2 Technology (from code)
- Next.js 15 web app (`apps/web`) and FastAPI (`apps/api`) on PostgreSQL.
- Celery worker and beat run the reminder engine, escalation, expiry jobs and email retries (appendix 04 §1.4).
- Dev email goes to Mailpit, added by the docs compose override.

### 1.3 Authentication (appendix 03 §1)
- Counselors sign in at **/overseas/login** and land on `/overseas/counselor/dashboard`.
- The Overseas Admin also signs in at /overseas/login. The Super Admin signs in at **/admin/login**.
- First access is through the 72-hour welcome/set-password email. Forgot/reset password, Change password and My profile are reached from the sidebar footer.
- A deactivated counselor gets the generic `Invalid credentials` message.

### 1.4 Cross-cutting rules worth explaining in every manual
- **Caseload.** A counselor sees:
  - leads they own in their own division;
  - students linked to them (csc-001);
  - students of applications assigned to them.

  Anything else shows as "not found" (appendix 01 §1, 02 §0).
- **Lead permissions are state-driven** (appendix 01 §1 table):
  - Return: only when no student is linked.
  - Link: only when no student is linked and the lead is not closed.
  - Convert: only from Qualified up to Counselling Completed.
  - Activity, follow-ups and next action: only on open leads.
- **Lead stages.**
  - Open: New Lead → Converted (11 stages).
  - Closed: Not Interested, Not Eligible, Invalid Contact, No Response, Lost, Duplicate. Closing a lead asks for a reason (ccrm-006).
- **Where application work happens.** All writes are made in the **Evaluate Applications** card on Students/Applications (appendix 02 §0). The 360 Applications tab only lists applications and adds new ones.
- **Agency vs direct.**
  - Counselors record offers, visa and enrolment on agency applications too (CC4).
  - A counselor-created application is always **direct**.
- **Due dates** for follow-ups, tasks and document requests must be today or later. Overdue states only arise as real days pass (owner D3).
- **Sidebar names differ from page titles:**

  | Sidebar | Page title |
  |---|---|
  | Tasks | My tasks |
  | Leads | My leads |
  | Reports | My performance |
  | Students | Application Tracking |

  Docs name both the first time.

## 2. Module Inventory
| Code | Module | Portal | Features |
|---|---|---|---|
| AUTH | Account access | Counselor | 6 |
| NAV | Portal tour | Counselor | 1 |
| DASH / SRCH | Dashboard and quick search | Counselor | 2 |
| LEAD | Leads | Counselor | 9 |
| CONV | Lead → student | Counselor | 2 |
| ACT | Activity logging on a lead | Counselor | 6 |
| CHAT | Counselor chat with students | Counselor | 1 |
| FUP | Follow-ups and reminders | Counselor | 3 |
| TASK | Tasks | Counselor | 1 |
| CAL | Appointments and calendar feed | Counselor | 2 |
| REP | My performance | Counselor | 1 |
| UNI | Universities | Counselor | 2 |
| STU | Students, 360, profile, notes, archive | Counselor | 10 |
| APP | Applications | Counselor | 10 |
| OFR | Offers, conditions, interviews | Counselor | 3 |
| DOC | Checklists, documents, requests | Counselor | 4 |
| VISA | Visa lifecycle | Counselor | 1 |
| FIN | Deposits, finance tab, receipts | Counselor | 3 |
| ARR | Enrolment, arrival, orientation | Counselor | 2 |
| HO | Handoffs into the counselor | Counselor + other roles | 4 |
| ADM | Counselor accounts and assignment | Overseas Admin / Super Admin | 4 |
| ESC | Overdue work and escalation | Overseas Admin | 2 |
| PERF | Counselor performance | Overseas Admin | 2 |
| CFG | Checklists, reminder rules, templates, archive restore | Overseas Admin | 4 |
| **Total** | | | **85** |

## 3. Feature Inventory
Full records with labels, fields, messages and evidence are in the appendices. Discovery IDs were consolidated as follows:
- Discovery ADM-003/004 (walk-in student) → **STU-003**.
- Discovery ADM-005 (walk-in lead) → **LEAD-002**.
- Discovery ADM-008 (lead owner change) has no UI, so it is product finding P15 rather than a feature.
- Discovery CFG-005 and NAV-002 are notes, not features.
- Discovery FIN-004 (commission) is folded into ARR-001.
- **CHAT-001** was added from the sidebar.

| Doc ID | Feature | Appendix |
|---|---|---|
| DOC-CNS-AUTH-001 | Sign in to the Overseas portal | 03 §1 |
| DOC-CNS-AUTH-002 | Set your first password from the welcome email | 03 §1 |
| DOC-CNS-AUTH-003 | Forgot / reset your password | 03 §1 |
| DOC-CNS-AUTH-004 | Change your password | 03 §1 |
| DOC-CNS-AUTH-005 | My profile | 03 §1 |
| DOC-CNS-AUTH-006 | Sign out, ended sessions, deactivated account | 03 §1 |
| DOC-CNS-NAV-001 | Portal tour: 15-item sidebar, top bar, mobile menu | 01 §0, 03 §2 |
| DOC-CNS-DASH-001 | Counselor dashboard (action tiles + application table) | 01 DASH |
| DOC-CNS-SRCH-001 | Quick search | 01 SRCH |
| DOC-CNS-LEAD-001 | My leads list | 01 LEAD |
| DOC-CNS-LEAD-002 | Record a new walk-in lead | 01 LEAD, 03 ADM-005 |
| DOC-CNS-LEAD-003 | Lead detail page layout | 01 LEAD |
| DOC-CNS-LEAD-004 | Lead details: view and edit contact, consent, referral | 01 LEAD |
| DOC-CNS-LEAD-005 | Next action | 01 LEAD |
| DOC-CNS-LEAD-006 | Change stage, record loss, close a lead | 01 LEAD |
| DOC-CNS-LEAD-007 | Lead qualification | 01 LEAD |
| DOC-CNS-LEAD-008 | Return a lead to the telecaller | 01 LEAD |
| DOC-CNS-LEAD-009 | Student and milestones panel (read only) | 01 LEAD |
| DOC-CNS-CONV-001 | Convert a lead to a new student | 01 CONV |
| DOC-CNS-CONV-002 | Link / unlink an existing student account | 01 CONV |
| DOC-CNS-ACT-001 | Log a call | 01 ACT |
| DOC-CNS-ACT-002 | Record a WhatsApp message | 01 ACT |
| DOC-CNS-ACT-003 | Email a lead | 01 ACT |
| DOC-CNS-ACT-004 | Log a meeting | 01 ACT |
| DOC-CNS-ACT-005 | Lead notes | 01 ACT |
| DOC-CNS-ACT-006 | Lead activity timeline | 01 ACT |
| DOC-CNS-CHAT-001 | Counselor Chat with students | 01 §0 (sidebar 12), ccrm-044 |
| DOC-CNS-FUP-001 | Follow-ups on a lead | 01 FUP |
| DOC-CNS-FUP-002 | Overdue follow-ups on the Tasks page | 01 FUP |
| DOC-CNS-FUP-003 | Automatic reminders (what triggers them, where they show) | 01 FUP, 04 §1.4 |
| DOC-CNS-TASK-001 | My tasks | 01 TASK |
| DOC-CNS-CAL-001 | Appointments page and lead appointments | 01 CAL |
| DOC-CNS-CAL-002 | Calendar and iCal feed | 01 CAL |
| DOC-CNS-REP-001 | My performance | 01 REP |
| DOC-CNS-UNI-001 | Partner universities list | 01 UNI |
| DOC-CNS-UNI-002 | University 360 view (incl. course commission display) | 01 UNI |
| DOC-CNS-STU-001 | Students page: Application Tracking table and filters | 02 STU |
| DOC-CNS-STU-002 | My students card (Source filter, search) | 02 STU |
| DOC-CNS-STU-003 | Add a walk-in student / edit pending / resend link | 02 STU, 03 ADM-003/004 |
| DOC-CNS-STU-004 | Student 360: header, tabs, Overview | 02 STU |
| DOC-CNS-STU-005 | Structured profile (Academic / Preferences / English) | 02 STU |
| DOC-CNS-STU-006 | Internal student notes | 02 STU |
| DOC-CNS-STU-007 | Activities and History tabs | 02 STU |
| DOC-CNS-STU-008 | Archive a student / Archived Students | 02 STU |
| DOC-CNS-STU-009 | Overseas consent (read only for staff) | 02 STU |
| DOC-CNS-STU-010 | When a student or application is reassigned to you | 02 STU |
| DOC-CNS-APP-001 | Add an application from the 360 | 02 APP |
| DOC-CNS-APP-002 | Intake Month YYYY picker | 02 APP |
| DOC-CNS-APP-003 | Applications tab list (EduSphere ID) | 02 APP |
| DOC-CNS-APP-004 | Advance an application's stage | 02 APP |
| DOC-CNS-APP-005 | Sub-status and the Ready-for-Submission gate | 02 APP |
| DOC-CNS-APP-006 | Journey stage | 02 APP |
| DOC-CNS-APP-007 | Record an outcome / resume | 02 APP |
| DOC-CNS-APP-008 | Application details (fields and dates) | 02 APP |
| DOC-CNS-APP-009 | Application status history | 02 APP |
| DOC-CNS-APP-010 | Agency vs direct applications | 02 APP |
| DOC-CNS-OFR-001 | Record, close or decide an offer | 02 OFR |
| DOC-CNS-OFR-002 | Offer conditions | 02 OFR |
| DOC-CNS-OFR-003 | Admission interviews | 02 OFR |
| DOC-CNS-DOC-001 | Application document checklist | 02 DOC |
| DOC-CNS-DOC-002 | Documents page and document status | 02 DOC |
| DOC-CNS-DOC-003 | Request documents from the student | 02 DOC |
| DOC-CNS-DOC-004 | Upload a document for the student (incl. offer letter) | 02 DOC |
| DOC-CNS-VISA-001 | Start and track a visa case | 02 VISA |
| DOC-CNS-FIN-001 | University deposit record | 02 FIN |
| DOC-CNS-FIN-002 | Finance tab: fees, payments, deposits, refunds | 02 FIN |
| DOC-CNS-FIN-003 | Upload a deposit receipt / payment proof | 02 FIN |
| DOC-CNS-ARR-001 | Confirm enrolment (agency commission note) | 02 ARR |
| DOC-CNS-ARR-002 | Arrival and orientation | 02 ARR |
| DOC-CNS-HO-001 | A telecaller hands a lead to you | 03 HO |
| DOC-CNS-HO-002 | A website enquiry becomes your lead | 03 HO |
| DOC-CNS-HO-003 | Agency students and applications | 03 HO |
| DOC-CNS-HO-004 | Self-registered students | 03 HO |
| DOC-CNS-ADM-001 | Create a counselor account | 03 ADM-001 |
| DOC-CNS-ADM-002 | Manage counselor users: set-up status, re-send link, edit, deactivate | 03 ADM-002 |
| DOC-CNS-ADM-003 | Assign / change a student's counselor (with reason) | 03 ADM-006 |
| DOC-CNS-ADM-004 | Assign / change an application's counselor (with reason) | 03 ADM-007 |
| DOC-CNS-ESC-001 | Counselor tasks (admin view) | 03 ESC |
| DOC-CNS-ESC-002 | Overdue by counselor and the escalation notice | 03 ESC |
| DOC-CNS-PERF-001 | Team performance | 03 PERF |
| DOC-CNS-PERF-002 | One counselor's report | 03 PERF |
| DOC-CNS-CFG-001 | Document checklist templates | 03 CFG |
| DOC-CNS-CFG-002 | Reminder rules and Run now | 03 CFG |
| DOC-CNS-CFG-003 | Counselor message templates | 03 CFG |
| DOC-CNS-CFG-004 | Archived students: admin restore | 03 CFG |

## 4. User Role Inventory
| Role | Sign-in | Landing | In this set |
|---|---|---|---|
| Counselor (`counselor`, division overseas) | /overseas/login | /overseas/counselor/dashboard | User manual |
| Overseas Admin (`overseas_admin`) | /overseas/login | /overseas/admin/* | Admin manual |
| Super Admin (`super_admin`) | /admin/login | /admin/* | Admin manual: differences only (§5) |
| Telecaller, Agent, Student | their own portals | — | Touchpoints in HO-001..004 only |
| IT counselor | /it/login | /it/counselor/* | **Out of scope** |

## 5. Role Permission Matrix (summary; detail in appendix 03 §8)
| Capability | Counselor | Overseas Admin | Super Admin |
|---|---|---|---|
| Work own leads, students, applications | ✅ | — | ❌ Pages open but data calls fail (P3) |
| Create counselor | — | ✅ Division locked to Overseas | ✅ Division defaults to **IT** (P4) |
| Deactivate / re-send link | — | ✅ Users page only, not Counselors page | ✅ |
| Assign student / application counselor | — | ✅ | ❌ (403, column hidden) |
| Counselor tasks, performance, checklists, reminder rules, message templates | — | ✅ | URL only; shows Overseas Admin nav |
| Archived-student restore | Archive own linked students | ✅ | ❌ "Overseas Administrator role required" |
| Receives escalation notice | — | ✅ | ❌ |

## 6. Frontend Route Inventory (in scope)
- **Counselor:** /overseas/counselor/
  - Sidebar: dashboard, tasks, students, leads, documents, applications, universities, visa, appointments, calendar, counselor-chat, reports, archived-students.
  - Not in the sidebar: leads/new, leads/[id], students/[id] (+ /notes, /profile), universities/[id].
  - `school-applications` is listed in the sidebar but out of scope (§11).
  - `/account/management-tasks` is a shared page, noted only.
- **Account:** /overseas/login, /admin/login, set-password and reset pages, /account/password, /account/profile.
- **Admin:** /overseas/admin/users, /overseas/admin/counselors, counselor-tasks, counselor-performance and /[id], checklists, reminder-rules, message-templates, archived students. On the Super Admin side: /admin/users.

## 7. Backend API Mapping
See appendix 01 (counselor_dashboard, counselor_search, counselor_tasks, counselor_reminders, counselor_messages, counselor_walk_in_leads, lead_handover, lead_appointments, calendar_feeds, university_view), appendix 02 (student_360, counselor_students, student_profiles, workflows, application_offers, application_checklists, application_interviews, document_checklists, student_document_requests) and appendix 03 (admin, portal, counselor_performance). The decision map (DEC-SCOPE / API / RBAC per item) is in appendix 04 §3.

## 8. Major User Workflows
1. **Telecaller handover → counselling → conversion:** HO-001 → LEAD-003..007 → ACT → FUP → CONV-001.
2. **Walk-in:** LEAD-002 or STU-003 → STU-004/005 → APP-001.
3. **Application to offer:** APP-001 → DOC-001/003 → APP-005 (Ready-for-Submission) → APP-004 → OFR-001/002/003.
4. **Offer to arrival:** OFR-001 (accept) → FIN-001/003 → VISA-001 → ARR-001 → ARR-002.
5. **Admin oversight:** ADM-001 → ADM-003/004 → ESC-001/002 → PERF-001/002.

## 9. Required Screenshots
About 170 to 200 PNGs: at least one per step, plus "what each role sees" variants and error/locked states. Settings and naming are in plan §Global Constraints.

## 10. Required Test Data (created through the UI by capture specs; all `Docs ` prefixed, `@example.test`)
- **Personas (owner D1)**, all Overseas:
  - Docs Counselor A (main), Docs Counselor B (reassignment and comparison), Docs Counselor C (to deactivate);
  - Docs Telecaller (handover);
  - students: Docs Walk-in Student, Docs Converted Student, Docs Pending Walk-in, Docs Self-registered Student.
  - The seeded Overseas Admin and Super Admin are used for admin screens. `demo-accounts.md` maps the personas to the seeded demo accounts.
- **Catalogue:** Docs University with two Docs courses, using fictional commission values (owner D5, for example 10% university and 12% course).
- **Config:** one Docs checklist template (block mode), reminder rules left at their defaults, one Docs message template.
- **Work:** leads at several stages, including a closed one and a duplicate; follow-ups, tasks and appointments dated relative to capture day; two direct applications on Docs Counselor A; one agency application (seeded Ananya, assigned to Docs Counselor A).

## 11. Unknown Workflows Requiring Browser Verification
- How the dashboard table's Status cell renders.
- The stage a walk-in lead shows right after creation.
- Timeline wording per event.
- Whether reminders are emailed.
- What the Super Admin sees on /overseas/admin/users.
- What the Overseas Admin is told when an agency application arrives with no counselor.
- Who owns the lost-reason catalogue.
- What the **School Applications** and **Management tasks** sidebar items show to an Overseas counselor. Both are recorded as discovered functionality.

## 12. Product Findings and Open Questions (owner)
Documented as built, in neutral wording. P1–P22 are code-read candidates; P4 was confirmed in the browser in S2 and P18 in S3; each is confirmed or dropped in the browser session that covers it.

| # | Finding | Evidence | Docs impact |
|---|---|---|---|
| P1 | Reminder notifications have no counselor inbox: no Notifications item or page for counselors | `counselor_reminders.py:189`, `navigation.ts:292` | FUP-003 |
| P2 | "Return to telecaller" is offered on closed leads. Returning one clears the owner but stays closed, and keeps no reason in history. The form says "goes back to Follow-up" | `lead_handover.py:124`, `lead_stages.py:53`, `CounselorLeadDetail.tsx:96` | LEAD-008 |
| P3 | Super Admin opening counselor Leads or Dashboard gets load errors, not an access message | `portal.py:43`, `counselor_dashboard.py:19` | NAV-001, admin README |
| P4 | Super Admin create-user defaults Division to IT. A counselor created that way cannot sign in at /overseas/login | `WorkflowPanel.tsx:389` | ADM-001 |
| P5 | Counselor messages say "Ask a telecaller manager…" and "A manager can reopen it…" | `AdminLeadStage.tsx:136`, `lead_follow_ups.py:32` | LEAD-006, FUP-001 |
| P6 | Dashboard "View all" links open the unfiltered My leads list. My leads has a Priority filter but no Priority column | `CounselorDashboardPanel.tsx:20`, `CounselorLeadsPanel.tsx:75` | DASH-001, LEAD-001 |
| P7 | Quick-search application hits open a filtered list, not the application. The results text shows a literal "--" | `counselor_search.py:117`, `CounselorQuickSearch.tsx:76` | SRCH-001 |
| P8 | Appointment no-show success text reads "Appointment no show." | `LeadAppointmentCard.tsx:58` | CAL-001 |
| P9 | My performance counts IT and Overseas leads together; My leads shows only one division | `counselor_performance.py:32` | REP-001 |
| P10 | Cancelled tasks vanish (the UI has a band, but the API never returns them) | `counselor_tasks.py:28` | TASK-001 |
| P11 | The counselor cannot book a lead appointment from the lead page; "Counselling Scheduled" can be set without one | `leadStages.ts:47` | LEAD-006, CAL-001 |
| P12 | Student notification after an advance shows the raw stage code (e.g. `visa_documentation`) | `workflows.py:2730` | APP-004 |
| P13 | Agency enrolment: the Enrolment panel lets a counselor confirm, while advance/sub-status say "Only the agency's Master confirms enrollment" | `application_offers.py:445`, `workflows.py:202` | ARR-001, APP-010 |
| P14 | Evaluate Applications cards show no EduSphere ID or intake; there is no counselor screen to change an existing intake | `CounselorEvaluationPanel.tsx:19`, `applicationDetails.ts:11` | APP-002, APP-008 |
| P15 | Changing a lead's counselor (owner + reason, ccrm-003 A7 / ccrm-033) is API-only: no admin screen | `AdminLeadManagementPanel.tsx` | ADM README |
| P16 | Archive gaps: the archived list shows only csc-001-linked students; only the linked counselor can archive; profile edits and document requests still work on an archived student | `student_archive.py:49,119` | STU-008 |
| P17 | The 360 "Counselor" field shows only the csc-001 link ("Not assigned" for the application counselor). The My students application count includes other counselors' applications | `counselor_student_360.py:105`, `counselor_students.py:280` | STU-004, STU-002 |
| P18 | Below 980 px there is no Sign out (no sidebar, and the mobile menu has no item for it). **Confirmed S3**; workaround: menu → My profile → public header **Logout** | `globals.css:12`, `PortalShell.tsx` | NAV-001, AUTH-006 |
| P19 | Deactivating a counselor has no guard or handover; their work stays on the inactive account | `admin.py:839` | ADM-002 |
| P20 | A telecaller handover sends no direct notice; it relies on the "New lead assigned" reminder rule | `lead_handover.py:46` | HO-001 |
| P21 | The 360 has no Visa tab and no document-review action; counselors cannot download invoices/receipts on Finance; any caseload counselor can upload a payment proof | appendix 02 VISA/DOC/FIN | VISA-001, DOC-002, FIN-002/003 |
| P22 | A counselor-created application for an agency student is always direct | `workflows.py:2435` | APP-001, APP-010 |
| P23 | (Found in S2, browser) The Overseas Admin's **Manage users** table is 716 px wide inside a 500 px panel at 1440 px: the Status badge is clipped and the Action column is off-screen; acting on a row scrolls the name out of view | `/overseas/admin/users`, `AdminUserManagementPanel.tsx` | ADM-002 |

**Default-based behaviours (owner D4).** About 40 counselor decisions are builder defaults marked NEEDS_CONFIRMATION or UNVERIFIED, not owner-approved (appendix 04 §3, column "Authority"). Manual pages describe them as built, with no warning banners. The owner reviews that list separately.

**Owner answers recorded for this set (2026-10-29):**
- **D1** Docs personas plus a `demo-accounts.md` mapping.
- **D2** Scope: Overseas counselor plus the admin side; IT counselors out.
- **D3** Time-dependent states are captured on real later days, and reminders/escalation use the Overseas Admin's **Run now**. No SQL back-dating.
- **D4** Default-based behaviours are documented as built and listed here only.
- **D5** Commission fields are shown with Docs test values only.
- **D6** The `cnsdocs` stack (3050/8050/8029) may be started, seeded, reset and snapshotted by Claude.
- **D7** Baseline is `main` @ 045d8c40, in `docs/counselor-crm/`.
