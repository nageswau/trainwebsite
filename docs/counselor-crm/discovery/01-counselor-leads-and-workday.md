# Counselor CRM discovery 01: leads and the counselor's workday

Baseline: main @045d8c40, read-only code discovery. Scope: the Overseas `counselor` lead side and daily-work tools under
`apps/web/app/overseas/counselor/` and their APIs. Student 360 / students pages and admin screens are covered by other passes.
Paths: `web/` = `apps/web/`, `api/` = `apps/api/app/`. All text in "quotes" is copied from code.

## 0. Sidebar (overseas counselor)

Source: `web/lib/navigation.ts:292` (labels are the slug title-cased) + `MANAGEMENT_TASKS_NAV` `web/lib/navigation.ts:29-30`. Sidebar footer: `web/components/PortalShell.tsx:21`.
Role pill reads "Counselor" + full name.

| # | Sidebar label | Route | Handled by | This pass? |
|---|---|---|---|---|
| 1 | Dashboard | /overseas/counselor/dashboard | `[section]`/dashboard -> `PortalPage` (`web/components/PortalPage.tsx:61`) | yes (DASH, SRCH) |
| 2 | Tasks | /overseas/counselor/tasks | dedicated page `web/app/overseas/counselor/tasks/page.tsx` | yes (TASK, FUP) |
| 3 | Students | /overseas/counselor/students | `[section]` | no (Student pass) |
| 4 | Leads | /overseas/counselor/leads | `[section]` -> `CounselorLeadsPanel` (`PortalPage.tsx:50`) | yes (LEAD) |
| 5 | Documents | /overseas/counselor/documents | `[section]` | no |
| 6 | Applications | /overseas/counselor/applications | `[section]` | no |
| 7 | Universities | /overseas/counselor/universities | dedicated page | yes (UNI) |
| 8 | School Applications | /overseas/counselor/school-applications | `[section]` | no |
| 9 | Visa | /overseas/counselor/visa | `[section]` | no |
| 10 | Appointments | /overseas/counselor/appointments | `[section]` -> `CounselorAppointmentsPanel` + student table (`PortalPage.tsx:51-55`) | yes (CAL) |
| 11 | Calendar | /overseas/counselor/calendar | dedicated page | yes (CAL) |
| 12 | Counselor Chat | /overseas/counselor/counselor-chat | `[section]` | no |
| 13 | Reports | /overseas/counselor/reports | dedicated page | yes (REP) |
| 14 | Archived Students | /overseas/counselor/archived-students | dedicated page | no |
| 15 | Management tasks | /account/management-tasks | shared page | no (shared) |
| footer | Change password / My profile / Sign out | /account/password, /account/profile | `PortalShell.tsx:21` | no |

- `[section]` catch-all (`web/app/overseas/counselor/[section]/page.tsx:2`): any slug not in the nav is `notFound()` (`PortalPage.tsx:4`).
- Not in the sidebar but reachable: /overseas/counselor/leads/new (button on My leads), /overseas/counselor/leads/[id], /overseas/counselor/universities/[id].
- No Notifications item and no "Student search" item, so no topbar unread badge or topbar search box for this role (`PortalShell.tsx:16,19`).
- Topbar shows "EduSphere Portal" + user name; mobile menu lists Change password, My profile + every nav item (`PortalShell.tsx:21`).

## 1. Common role/access rules

- Every lead route uses `counselor_scope`: `role == "counselor"` else 403 "Counselor role required"; leads where `owner_id == user` AND `division == user.division`; anything else reads as 404 "Lead not found" (`api/services/lead_handover.py:97-101`, `api/services/lead_pipeline.py:32`).
- Dashboard, quick search, calendar feed, reports, walk-in lead, convert: overseas counselor only (403 otherwise) (`api/api/counselor_dashboard.py:15-20`, `api/api/counselor_search.py:16-19`, `api/api/calendar_feeds.py:17-24`, `api/api/counselor_walk_in_leads.py:19-24`, `api/api/lead_handover.py:213`).
- Super Admin: passes the portal payload check (`api/api/portal.py:43`), so `[section]` pages render for them, but the lead/dashboard/search APIs refuse them (see findings F3). Dedicated pages (Tasks, Calendar, Reports, Universities) show the access-denied card with the REFUSED text to any non-overseas-counselor (`tasks/page.tsx:16,22`, `calendar/page.tsx:10,16`, `reports/page.tsx:13,26`, `universities/page.tsx:26`). /leads/new is `notFound()` for any other role (`leads/new/page.tsx:23`).
- Overseas Admin: none of these counselor pages; admin equivalents exist (Counselor tasks, Counselor performance, Reminder rules) - other pass.
- Lead-detail action visibility comes from API `permissions` (`api/services/lead_handover.py:121-131`):

| permission | true when |
|---|---|
| return | no student linked |
| link | no student linked and lead not closed |
| unlink | student linked and stage != Converted |
| stage | not closed and stage != Converted |
| follow_up (also next action) | not closed |
| convert | not linked, division overseas, stage in Qualified..Counselling Completed (`lead_handover.py:116-118`) |
| activity (calls/messages/meetings) | not closed |

Lead stages (`web/lib/leadStages.ts:4-24`): open = New Lead, Assigned, First Call Pending, Contacted, Qualified, Interested, Follow-up, Counselling Scheduled, Counselling Completed, Application/Enrollment, Converted; closed = Not Interested, Not Eligible, Invalid Contact (key `wrong_number`), No Response, Lost, Duplicate.

---

## DASH - Dashboard

### DOC-CNS-DASH-001 Counselor dashboard (action dashboard + application table)
- Route: /overseas/counselor/dashboard; sidebar "Dashboard". Login lands here (`web/lib/navigation.ts:50`).
- Roles: overseas counselor. IT counselor: action sections 403. Super Admin: page renders, sections show the failure card (F3).
- Layout top-down (`PortalPage.tsx:61`): payload title "Counselor Dashboard", subtitle "Application pipeline and next actions." (`api/services/portal.py:1129-1130`) -> Quick search card (SRCH-001) -> 12 action sections -> metric tiles + application table -> WorkflowPanel.
- Action sections (`web/components/CounselorDashboardPanel.tsx:18-31`; queries `api/services/counselor_dashboard.py:104-200`). Each: title + count badge, first 10 items soonest first, "View all N" link when more than 10 (`CounselorDashboardPanel.tsx:62-66`), red "Overdue" tag on overdue items.

| Section title | Empty text | "View all" goes to | Content rule |
|---|---|---|---|
| New and not-contacted leads | "No new leads waiting." | /leads | own leads in New / Assigned / First Call Pending; detail "<Stage>, received" |
| Today's appointments | "No appointments today." | /appointments | open appointments with this counselor, today IST |
| Calls logged today | "No calls logged today." | /leads | calls this counselor logged today IST |
| Follow-ups due | "No follow-ups in the next 7 days." | /leads | open follow-ups on own leads due before end of today+7 (incl. overdue) |
| Tasks due | "No tasks due in the next 7 days." | /tasks | own open tasks due on/before today+7 |
| Leads without a next action | "Every lead has a next action." | /leads | own leads not in not-contacted, closed, Application/Enrollment or Converted, with no next action; detail "<Stage> since" |
| Students with pending documents | "No documents pending." | /documents | out of this pass |
| Applications not ready | "No applications waiting on documents." | /applications | out of this pass |
| Submitted, awaiting decision | "No applications awaiting a decision." | /applications | out of this pass |
| Offer deadlines and conditions | "Nothing due on offers." | /applications | note "Offers, conditions and deposits due in the next 14 days, or overdue." |
| Visa appointments and decisions | "No visa appointments or pending decisions." | /visa | out of this pass |
| Enrolment and arrival | "No enrolment or arrival to confirm." | /applications | out of this pass |

- Notes under Follow-ups due / Tasks due: "Overdue or due in the next 7 days, soonest first." (`CounselorDashboardPanel.tsx:82`; `FOLLOW_UP_DAYS = 7`, `WINDOW_DAYS = 14` `api/services/counselor_dashboard.py:43-44`).
- Times: timestamps in IST "day month time"; dates as "day month year" (`CounselorDashboardPanel.tsx:34-38`).
- Failure: "Dashboard sections are unavailable right now." + "Try again" link (`CounselorDashboardPanel.tsx:112-116`). Loading skeleton: 12 grey panels.
- Metric tiles (`api/services/portal.py:1133-1138`): "Applications", "Awaiting documents", "Offers". Table columns: "EduSphere ID", "Student", "University", "Status", "Next action" (`portal.py:1131`), max 500 rows.
- Screenshot prerequisites: overseas counselor with handed-over leads in New/Assigned and in Contacted/Interested without next action; a follow-up due within 7 days and one overdue; a call logged today; an open task due this week; a lead appointment today; at least one assigned application.

## SRCH - Quick search

### DOC-CNS-SRCH-001 Quick search (dashboard)
- Route: on /overseas/counselor/dashboard, card "Quick search" (`web/components/CounselorQuickSearch.tsx:85-93`). API GET /api/v1/counselor/search?q= (`api/api/counselor_search.py:16-21`).
- Field: "Name, phone, email or ID" (search, max 100), placeholder "e.g. APP-000012, 98765 43210"; button "Search" (disabled while searching). Searches on submit only.
- Matches (case-insensitive substring; phone-shaped text matches digits ignoring separators) (`api/services/counselor_search.py:1-7,78-125`):
  - Leads: own leads (lead scope) by name, email, Lead ID, phone -> opens lead.
  - Students: visible students by name, email, student code, phone -> opens /students/{id}/notes.
  - Applications: applications assigned to the counselor by EduSphere ID, owner name, email, phone -> opens /applications?university=..&intake=.. (F7).
- Results: three groups "Leads (n)", "Students (n)", "Applications (n)" ("n+" when more); each max 10, "Showing the first 10 -- refine your search."; empty group "No matches"; all empty "Nothing in your leads, students or applications matches “<q>”." (`CounselorQuickSearch.tsx:56-79`).
- Messages: under 3 chars "Type at least 3 characters" (client `:33-35`, server `TOO_SHORT`); over 100 "Use at most 100 characters"; rate limit 30/min -> 429 "Too many searches; try again in N seconds" (`counselor_search.py:24-31,83`); network "Search did not complete. Check your connection and try again."; "Searching…".
- Every search writes an audit row (counts only).
- Prerequisites: a lead, a linked/visible student and an application with a known name/phone.

## LEAD - Leads

### DOC-CNS-LEAD-001 My leads list
- Route: /overseas/counselor/leads; sidebar "Leads". Component `web/components/CounselorLeadsPanel.tsx`; API GET /api/v1/counselor/leads (`api/api/lead_handover.py:68-81`).
- Title: eyebrow "Leads", heading "My leads", text "Leads telecallers handed to you and walk-ins you recorded. Open one to link the student account or return it to the telecaller." (`:104-109`). Button "New walk-in lead" (overseas only, `:112`).
- Filters (form "Filter leads", kept in URL, apply on change) (`:114-138`): "Stage" (All + all 17 stages), "Priority" (All, Hot, Warm, Cold), "Lead date from" (date, max = to), "Lead date to" (date, min = from); "Clear filters" link when any set.
- Table "Leads handed to you": "Lead ID" (link to detail), "Name", "Interest" (lead subject), "Stage", "Telecaller" ("Unassigned" if none), "Lead date". Newest first, 20 per page; "x–y of N", "Previous", "Next" (`:73-94`).
- Export (overseas, only when rows exist): "Export my leads" -> "Download CSV" / "Download Excel" ("Preparing CSV…"/"Preparing Excel…"); all rows matching filters; file `my-leads`; columns Lead ID, Name, Interest, Stage, Priority, Source, Telecaller, Lead date - never phone/email (`:96`, `api/api/crm_exports.py:45-48,131-165`, `web/components/ExportButtons.tsx:28-29`).
- Messages: "Loading leads…"; "Unable to load your leads." + "Try again"; 422 filter refusal shows server text; empty "No leads have been handed to you yet." / filtered "No leads match these filters." (`:60-69`).
- Prerequisites: telecaller handover(s) to the counselor (tel-018) and/or walk-ins; mixed stages/priorities/dates for filter shots.

### DOC-CNS-LEAD-002 New walk-in lead
- Route: /overseas/counselor/leads/new; reached via "New walk-in lead" on My leads. Page `web/app/overseas/counselor/leads/new/page.tsx`; form `web/components/NewLeadForm.tsx`; API POST /api/v1/counselor/walk-in-leads (`api/api/counselor_walk_in_leads.py:34-41`).
- Roles: overseas counselor only (page 404 for others; API 403 "Only an overseas counselor can record walk-in leads").
- Header: "← Back to my leads", eyebrow "Leads", "New walk-in lead", text "For a student who came to the office. The lead is yours; a telecaller from the Overseas team is also assigned and can see it. We check the mobile number and email against every lead first, so a person is never entered twice." (`page.tsx:27-35`).
- Fields (`NewLeadForm.tsx:23-31,218-281`): "Student name *" (160), "Mobile number *" (tel, 40), "Email" (255), "WhatsApp number", "City", "State", "Qualification", "Passing year" (number), "College/University"; "Product interest *" (select "Choose a product", overseas/no-team products only); "Intake" (overseas products only); "Campaign"; "Lead source *" (preset "Walk-in"; options Instagram, Facebook, Google, Website, WhatsApp, Walk-in, College, School, Agent, Referral, Exhibition/Event, BDM, Other `web/lib/telecallerCatalogue.ts:22-25`); "Priority" (Hot/Warm/Cold, default Warm, with help text e.g. "Interested but needs follow-up."); "Enquiry subject" (placeholder = product or "Defaults to the product"); fieldset "Contact and consent" (DOC-CNS-LEAD-004 fields); "Notes" (5000). No Division picker (team fixed). Buttons "Create lead" ("Creating…"), "Cancel".
- Validation: "Enter the <student name, mobile number, product interest, lead source>." (`:33,176-178`); intake problem text; "Unable to load the products and campaigns. Reload the page to try again."; server 422 "Walk-in leads are for the Overseas team", "This campaign is for another product", "This campaign belongs to another lead source", "The intake is asked for overseas study leads only" (`api/services/lead_intake.py:31,124-135`).
- Duplicates: mobile/email checked on entry and on create (409) -> panel "⚠️ Lead already exists." "A lead with this mobile number or email is already in the CRM. Add this enquiry to it instead of creating another lead." with per match Lead ID, name "(same mobile/email)", "Existing telecaller", "Counselor", "Last contact", "Current status", "Previous enquiries", buttons "Add enquiry to this lead" ("Adding…"/"Enquiry added") and "Open lead" (own leads only); notice "This person is already a lead. Add the enquiry to the existing lead instead."; add success "Enquiry added to <code>." (`NewLeadForm.tsx:70-110,204-207`). Add-enquiry needs source: "Choose the lead source first." / "Enter the enquiry subject or choose a product first."
- Success: opens the new lead page. Lead is owned by the counselor, stage New Lead then distributed to a telecaller (tel-007) (`api/services/lead_intake.py:146-157`).
- Prerequisites: active overseas product(s) in the telecaller catalogue; distribution rules for an Overseas telecaller; a pre-existing lead with a known mobile for the duplicate shot.

### DOC-CNS-LEAD-003 Lead detail page (layout)
- Route: /overseas/counselor/leads/[id]; from My leads "Lead ID", dashboard items, quick search, task links, Tasks overdue follow-ups. Page `web/components/CounselorLeadPage.tsx`; body `web/components/CounselorLeadDetail.tsx:318-493`; API GET /api/v1/counselor/leads/{id}.
- Not own lead -> 404 page; non-counselor -> access card (`CounselorLeadPage.tsx:18-21`).
- Order: "Back to my leads", Lead ID eyebrow, name, "Stage: <label>", closure line (LEAD-006) -> Next action (LEAD-005) -> Stage (LEAD-006) -> Follow-ups (FUP-001) -> Calls (ACT-001) -> Messages (ACT-002/003) -> Meetings (ACT-004) -> "Return to telecaller" (LEAD-008) -> "Student account" (CONV-001/002) -> "Student and milestones" (LEAD-009) -> "Lead details" (LEAD-004) -> "Qualification" (LEAD-007) -> "Notes" (ACT-005) -> "Activity" (ACT-006).
- After a return, the action sections disappear and "Lead returned to the telecaller." shows (`:401-402`).
- No lead appointments section on this page (counselor sees them under Appointments only).

### DOC-CNS-LEAD-004 Lead details (view + edit contact/consent/referral)
- Section "Lead details" with "Edit details" (hidden after return) (`CounselorLeadDetail.tsx:448-471`). API PATCH /api/v1/counselor/leads/{id} (`api/api/lead_handover.py:89-97`).
- View rows: "Lead ID", "Mobile number", "Email", "City", "Qualification", "Lead source", "Product interest", "Telecaller" ("Unassigned"), "Lead date", "Enquiry date", "Preferred contact", "Marketing consent" (+ time), "Referred by"; then subject (bold) and message (`:358-363`, `web/components/LeadContactFields.tsx:36-44`).
- Editable fields only (`LeadContactFields.tsx:57-85`): "Preferred contact method" (Not recorded / Phone call / WhatsApp / Email / SMS), "Enquiry date" (date, 2000-01-01..today, help "Leave blank for today."), "Marketing consent" (Not asked / "Yes — agreed to marketing messages" / "No — no marketing messages"), "Referred by (name)" (160), "Referrer's phone or email" (120). All optional; only changes sent; enquiry date never cleared.
- Buttons "Save details" ("Saving…"), "Cancel". Success "Details saved."; failure "Unable to save the details." or server text. Name/phone/email/product cannot be edited by the counselor here.

### DOC-CNS-LEAD-005 Next action
- Section "Next action" (`CounselorLeadDetail.tsx:108-175`); API PUT /api/v1/counselor/leads/{id}/next-action (`api/api/lead_handover.py:170-179`).
- Shows "<action> · due <date>" with red "Overdue" badge when due before today IST on an open lead (`api/services/lead_handover.py:270-273`). Empty: "No next action set. Add one before moving the lead to an open stage." (closed lead: "No next action.").
- Button "Set next action" / "Edit next action" (only when `follow_up` permission). Form: "Action" (200, placeholder "e.g. Send the university shortlist"), "Due date" (date); "Save next action" ("Saving…"), "Cancel".
- Messages: "Add the next action and its due date." (client); "Choose a due date from today onwards" (server, only when the date changes - an overdue action's text can still be edited) (`lead_handover.py:33,276-282`); closed lead 409 "This lead is closed; it needs no next action"; success "Next action saved.".
- Cleared when the lead is returned (`lead_handover.py:142`).

### DOC-CNS-LEAD-006 Stage change, loss capture and closure line
- Section "Stage" shown when `stage` permission (`CounselorLeadDetail.tsx:381-389`); control `web/components/AdminLeadStage.tsx:41-158`; API POST /api/v1/counselor/leads/{id}/stage (`api/api/lead_handover.py:158-167`).
- Button "Change stage" -> select "Choose a stage". Counselor options (`web/lib/leadStages.ts:47-55`): before Application/Enrollment: Qualified, Follow-up, Counselling Scheduled, Counselling Completed + Not Interested, Not Eligible, Lost; from Application/Enrollment: only the three closed outcomes; closed/Converted: no control. Counselor cannot choose Duplicate, Invalid Contact, No Response, Interested, or reopen.
- Lost / Not Interested: "Lost reason (required)" select ("Choose a reason", from the telecaller lost-reason list) and "Lost to (optional)" (160, placeholder "Competitor or chosen destination"). Reason textarea "Reason (required)" for Not Eligible, else "Reason (optional)" (500) (`leadStages.ts:69-70`). Buttons "Save" ("Saving…"), "Cancel".
- Client errors: "Choose a stage.", "Add a reason for this stage.", "Choose why the lead was lost."; lost-reason load: "Loading lost reasons…", "Unable to load the lost reasons." + "Retry", "No lost reasons are set up yet. Ask a telecaller manager to add one." (`AdminLeadStage.tsx:82-87,128-136`).
- Server errors (`api/services/lead_pipeline.py:34-51`): "Set a next action and its due date first" (open target with no next action, A2), "The lead is already at this stage", "This stage is set by the system", "The lead is with the counselor; its stage moves with the application", "Add a reason for closing the lead", "Choose why the lead was lost", "Choose an active lost reason".
- Success: "Stage updated."; a closing move cancels open follow-ups (reason "Lead closed") and appointments; page re-reads the lead.
- Closure line under the stage (`web/components/LeadClosure.tsx:4-10`): "Duplicate of <Lead ID>" or "Lost reason: <name> · Lost to: <text>".
- Prerequisites: next action set on the lead; at least one active lost reason (telecaller manager catalogue).

### DOC-CNS-LEAD-007 Qualification (lead)
- Section "Qualification", button "Edit qualification" (`web/components/LeadQualificationForm.tsx:305-317`); API GET/PUT /api/v1/counselor/leads/{id}/qualification (`api/api/lead_handover.py:100-120`). Stage never moves.
- Basic fields (`web/lib/telecallerLeads.ts:87-93`): "Qualification", "Current college/company", "Passing year" (1950-2100, "Enter a year from 1950 to 2100."), "Work experience (years)" (0-50, "Enter whole years from 0 to 50."), "City", "State".
- "Overseas requirement" (product row "Destination: <product> (change it in Lead details)"): "UG / Master's" (UG/Masters), "Preferred course", "Intake", "Academic percentage" (0-100), "IELTS/PTE status", "Budget", "Passport status" (No passport / Applied / Has a valid passport), "Preferred country", "Study mode" (Full-time/Part-time/Online), "Preferred campus", "CGPA (out of 10)", "Backlogs" (0-99); English tests list "Add English test" ("No English tests added.") (`telecallerLeads.ts:103-119`, `LeadQualificationForm.tsx:217-236`).
- No product: "Set the lead's product interest in Lead details to see its IT or overseas questions." Buttons "Save qualification"/"Cancel"; "Check the highlighted fields."; success "Qualification saved."; footer "Last updated by <name> · <time>".

### DOC-CNS-LEAD-008 Return lead to telecaller
- Button "Return to telecaller" when `return` permission (`CounselorLeadDetail.tsx:70-104,405`); API POST /api/v1/counselor/leads/{id}/return (`api/api/lead_handover.py:182-188`).
- Form: "Reason for returning" (textarea, 500, required); note "The lead goes back to Follow-up with <telecaller|the telecaller>; any open counselling appointment is cancelled."; "Return lead" ("Returning…"), "Cancel".
- Messages: "Add a reason for returning the lead."; 409 "Unlink the student before returning the lead" (`api/services/lead_handover.py:28`); success "Lead returned to the telecaller."
- Effect: owner cleared, next action cleared, open follow-ups and appointments cancelled ("Returned to telecaller"), telecaller alerted (`lead_handover.py:134-148`). The lead then leaves My leads.

### DOC-CNS-LEAD-009 Student and milestones (read only)
- Section "Student and milestones" + "Converted" badge (`web/components/LeadMilestones.tsx:9-36`). "No student account is linked yet." / "Linked student: <name (email)>"; list "<kind> · <label> — <status> · <reference> · <time>"; "No enrolment or application yet."

## CONV - Lead to student

### DOC-CNS-CONV-001 Convert lead to a new student
- In section "Student account" when not linked and `convert` (`CounselorLeadDetail.tsx:263-313,431-435`); API POST /api/v1/counselor/leads/{id}/convert (`api/api/lead_handover.py:210-221`).
- Hint when not yet allowed (overseas): "Move the lead to Qualified to convert it to a new student."
- Button "Convert to student" -> "Full name" (160), "Email" (255), "Phone (optional)" (40), prefilled from lead; text "Creates the student's account, copies this lead's details into their profile, emails a set-password link and moves the lead to Application/Enrollment."; "Create student account" ("Creating…"), "Cancel".
- Messages: "Add the student's name and email."; server "Only an overseas counselor can convert a lead to a student", "This lead is closed; reopen it before converting it", "Move the lead to Qualified before converting it", "A student account already has this email or mobile. Link the existing student instead.", "Unlink the current student first" (`api/services/lead_conversion.py:21-24,72-79`); 5xx "The server couldn't complete this. Please try again in a moment."
- Success: "Student account created for <name>. A set-password link was emailed to <email>." or "Student account created for <name>, but the set-password email was not delivered. Re-send it from My students." + "Open the student's profile" (`:420-427`).
- Allowed stages: Qualified, Interested, Follow-up, Counselling Scheduled, Counselling Completed (`lead_handover.py:116-118`).
- Prerequisites: email delivery configured (or capture the not-delivered variant); lead at Qualified with a unique email/mobile.

### DOC-CNS-CONV-002 Link / unlink an existing student account
- Same section; panel loads suggestions (same email or mobile) then search (`CounselorLeadDetail.tsx:178-261`); APIs GET .../link-suggestions, POST/DELETE .../student-link (`api/api/lead_handover.py:191-231`).
- Labels: "Looking for student accounts…", "Unable to load student accounts.", "No student account has this lead's email or mobile. Search for one below.", "No active student account matches that search."; each match name, email · phone, "Already linked to another lead" or "Link" -> confirm "Link <name> to this lead? The lead moves to Application/Enrollment." "Yes, link"/"Keep looking" ("Linking…"). Search "Search students" (placeholder "Name, email or mobile") + "Search"; "Enter at least 3 characters."; success "Student linked."
- Linked view: "Linked to <name> (<email>)", "Unlink student" -> "Unlink <name>? The lead goes back to Follow-up." "Yes, unlink"/"Keep it"; success "Student unlinked."; Converted: "The student has enrolled, so the lead is converted. Only an admin can unlink it." Errors "This student is already linked to another lead", "Only an admin can unlink a converted lead", "This lead is not linked to a student".
- Closed lead with no link: "No student account is linked."
- Conversion to Converted is automatic (system) once the student enrols (`api/lead_stages.py:54`).

## ACT - Activity logging on a lead

### DOC-CNS-ACT-001 Calls
- Section "Calls", button "Log call" when `activity` (`web/components/LeadCalls.tsx:143-208`); form `web/components/CallLogForm.tsx`; APIs GET/POST /api/v1/counselor/leads/{id}/calls, PATCH/DELETE /api/v1/counselor/calls/{id}.
- Form: "Outcome (required)" ("Select an outcome"; Connected: Connected – Interested / Need Information / Follow-up Required / Appointment Fixed, Not Interested, Call Back Requested, Already Joined Elsewhere, Duplicate Lead, Not Eligible; Not connected: Wrong Number, Busy, No Answer, Switched Off `web/lib/telecallerCalls.ts:8-22`), "Call date and time (IST)", "Duration" (Minutes / Seconds), "Call type" (Outgoing/Incoming), "Remarks" (2000; "(required: name the other lead)" for Duplicate Lead). Checkbox "Add a next follow-up" or fieldset "Next follow-up (required for this outcome)" for Follow-up Required / Call Back Requested: "Follow-up due (IST, required)", "Follow-up reason", "Next action". No "Also move the lead to Follow-up" for counselors. Buttons "Save call"/"Save changes", "Cancel".
- Client errors: "Choose the call date and time", "Enter whole minutes and seconds (0–59), up to 4 hours", "Choose an outcome", "Add remarks naming the other lead", "Choose a due date and time", "Choose a reason" (`CallLogForm.tsx:64-69`). Server: "The call time can't be in the future", "Calls can be logged up to 7 days back", "This lead is closed. A manager can reopen it before a call is logged", "Only the person who logged this call can change it", "Only today's calls can be changed", "A call can only be moved within today", "Add the next follow-up for this outcome" (`api/services/lead_calls.py:40-51`).
- A counselor's call never moves the stage, even for closing outcomes (`api/api/telecaller_calls.py:77-81`, `telecallerCalls.ts:121-129`).
- List item: outcome, "Connected"/"Not connected", "<IST time> · <duration> · Outgoing|Incoming · <caller>", remarks; Edit/Delete only on own calls logged today IST; delete confirm "Delete this call? Any follow-up it added stays." "Yes, delete"/"Keep it". Notices "Call logged.", "Call updated.", "Call deleted."; empty "No calls logged yet."; "Showing the latest N of M calls."

### DOC-CNS-ACT-002 WhatsApp send record
- Section "Messages", buttons "Send WhatsApp" / "Send email" (disabled with "No WhatsApp or mobile number on this lead." / "No email address on this lead.") (`web/components/LeadMessages.tsx:119-163`); APIs .../leads/{id}/messages, .../render, DELETE /api/v1/counselor/messages/{id}.
- Composer (`web/components/WhatsAppComposer.tsx`): "Template" (active WhatsApp templates; "Custom message"), "Message" (1000), "Open WhatsApp" (new tab, wa.me) -> "Did you send it in WhatsApp?" "Yes, record as sent" / "Not sent"; "Cancel". Warnings "Unable to load the templates. You can still write a custom message.", "This template was made for another product. Check the text before sending."
- Success "WhatsApp send recorded."; Delete only by sender on the same IST day: "Delete this record? It does not unsend the WhatsApp message."; "Message deleted.". Server: "This lead has no WhatsApp or mobile number", "Choose an active WhatsApp template", "Only today's messages can be deleted", "This lead is closed. A manager can reopen it before a message is sent" (`api/services/lead_messages.py:34-47`).

### DOC-CNS-ACT-003 Email to lead
- Composer (`web/components/EmailComposer.tsx`): "Template", "Subject" (200), "Message" (5000), "Send email" ("Sending…"), "Cancel". Success "Email queued for sending."; list polls every 5 s while queued.
- Item states: "This email was not delivered. Check the lead's email address and send it again." / "The mail server didn't accept it yet. It will be retried automatically." Emails cannot be deleted ("A sent email can't be deleted"). Server: "This lead has no email address", "Choose an active email template", "Email is not set up. Ask an administrator to configure SMTP.", cap 100 emails/sender/IST day.
- Prerequisites: active WhatsApp/email templates (telecaller content library, readable by counselors `api/services/telecaller_content.py:32`); email provider configured.

### DOC-CNS-ACT-004 Meetings
- Section "Meetings", button "Record meeting" when `activity` (`web/components/LeadMeetings.tsx:100-117`); API GET/POST /api/v1/counselor/leads/{id}/meetings (`api/api/lead_handover.py:144-155`).
- Form "Record meeting": "Meeting date and time (IST)", "Mode" (In person / Online / Phone `web/lib/leadMeetings.ts:6`), "Notes (required)"; "Save meeting", "Cancel". Errors "Choose the meeting date and time", "Add what was discussed"; server "The meeting time can't be in the future", "This lead is closed, so no meeting can be recorded" (`api/services/lead_meetings.py:21-22`). Success "Meeting recorded."; append-only (no edit/delete); empty "No meetings recorded yet."

### DOC-CNS-ACT-005 Lead notes
- Section "Notes" (hidden after return) (`web/components/LeadNotes.tsx`; `CounselorLeadDetail.tsx:480-485`); API GET/POST .../notes (`api/api/lead_handover.py:130-141`).
- "Add a note" textarea (4000, counter "n / 4000"), "Add note" ("Adding…"); "Write a note first."; "Note added."; list "Lead notes" newest first with author + time. Append-only; allowed on closed leads.

### DOC-CNS-ACT-006 Activity timeline
- Section "Activity" (`CounselorLeadDetail.tsx:487-490`), `web/components/LeadTimeline.tsx`, API GET .../timeline. Merged stage changes and events, newest first; re-reads after every action on the page.

## FUP - Follow-ups and reminders

### DOC-CNS-FUP-001 Follow-ups on a lead
- Section "Follow-ups", "Add follow-up" when `follow_up` (`web/components/LeadFollowUps.tsx`, `FollowUpForm.tsx`, `FollowUpItem.tsx`); APIs .../leads/{id}/follow-ups, /api/v1/counselor/follow-ups/{id}[/complete|/cancel] (`api/api/telecaller_follow_ups.py:77-175`).
- Form: "Due date and time (IST, required)" (min now), "Reason (required)" ("Select a reason"; Need to discuss with parents, Need course details, Need fee details, Waiting for salary, Waiting for documents, Comparing courses, Interested next month, Interested next intake, Waiting for university information, Requested counselor call `web/lib/telecallerFollowUps.ts:9-20`), "Next action" (200, placeholder "e.g. Call today at 4:00 PM"), "Notes" (2000). Buttons "Add follow-up"/"Save changes", "Cancel"; leave guard "Discard this follow-up?".
- Item: reason, "Overdue"/"Done"/"Cancelled" badges, "Due <IST>", next action, notes, "Done <time> by <name>", "Cancelled <time> — <reason>"; actions "Done", "Reschedule", "Cancel follow-up" (reason form, "Cancel it"). Notices "Follow-up added.", "Marked done.", "Follow-up rescheduled.", "Follow-up cancelled."
- Errors: "Choose a due date and time", "Choose a reason"; server "Choose a due time in the future", "Choose a due time within the next 12 months", "This lead is closed. A manager can reopen it before a follow-up is added", "Follow-up not found"; max 20 open per lead (`api/services/lead_follow_ups.py:30-37`); session expiry "Your session has ended — sign in again to continue."; generic "We couldn't save this. Please try again."
- Counselor may change any open follow-up on their lead (`lead_follow_ups.py:60-62`); handover cancels the telecaller's open ones.

### DOC-CNS-FUP-002 Overdue follow-ups list (Tasks page)
- On /overseas/counselor/tasks, section "Overdue follow-ups (N)" (`web/app/overseas/counselor/tasks/page.tsx:46-62`); API GET /api/v1/counselor/follow-ups?view=overdue&limit=50.
- Item: "<Lead ID> · <name>" link + "Was due <IST> · <reason>". Empty "No follow-ups on your leads are overdue."; failure "Your follow-ups can't be loaded right now. Try again in a moment." (tasks still show).
- No "due today" follow-up list on this page (dashboard "Follow-ups due" covers the week).

### DOC-CNS-FUP-003 Automatic reminders (rule engine)
- No counselor UI; rules are set by the Overseas Admin (/overseas/admin/reminder-rules; `api/api/counselor_reminders.py:17-40`). Rules (`api/services/counselor_reminders.py:78-91`): task-type ("New lead assigned", "No response after contact", "Document request overdue", "University decision overdue", "On-hold review date") appear in the counselor's Tasks (source rule); notify-type ("Application deadline approaching", "Offer deadline approaching", "Deposit due", "Offer condition due", "Visa appointment approaching") create in-app notifications - see F1.

## TASK - Tasks

### DOC-CNS-TASK-001 My tasks
- Route /overseas/counselor/tasks; sidebar "Tasks". Page `tasks/page.tsx`; `web/components/CounselorTaskForm.tsx`, `CounselorTaskList.tsx`; API /api/v1/counselor/tasks (`api/api/counselor_tasks.py`).
- Title: eyebrow "Workspace", "My tasks", "<n> overdue · <n> due today · <n> upcoming. Tasks the Overseas Admin gives you show here too."
- Form "Add a task": "Title" (2-200), "Due date" (date, default today, min today), "Priority" (High/Medium/Low, default Medium), "About (optional)" ("Nothing in particular"; groups Leads / Students / Applications - counselor's own); "Add task" ("Saving…").
- Errors: "Give the title (2-200 characters)", "Choose the due date", "The due date can't be in the past", "Check the highlighted fields."; server "Choose a due date from today up to two years ahead", "Choose a lead, student or application of this counselor", "You can add tasks for yourself only" (`api/services/counselor_tasks.py:39-46`). Success "Task added."
- List bands (`web/lib/counselorTasks.ts` BANDS): "Overdue", "Today", "Upcoming", "Done (last 7 days)" with counts; row "<title> — due <date>", "<Priority> priority" badge, "<Lead|Student|Application>: <label>" link, "Given by <name>." when assigned by someone else. Actions: "Mark done", "Reopen" (done), "Edit" (own tasks only), "Cancel task" -> "Cancel this task? It can't be reopened." "Yes, cancel it"/"Keep it". Admin-given tasks: status only ("You can change only the status of a task someone else gave you"); cancelled: "This task was cancelled; it can't be changed".
- Empty: "You have no open tasks. Add one above." Bands are IST days (`counselor_tasks.py:27-30`).
- Link targets: lead -> lead page; student -> /students/{id}/notes; application -> /applications (`counselorTasks.ts` linkHref).
- Prerequisites: own tasks in each band (one overdue needs a DB-backdated due date since the form blocks past dates), one task created by the Overseas Admin, a done task within 7 days.

## CAL - Appointments and calendar

### DOC-CNS-CAL-001 Lead appointments
- Route /overseas/counselor/appointments; sidebar "Appointments". `web/components/CounselorAppointmentsPanel.tsx`, `LeadAppointmentCard.tsx`; API GET /api/v1/counselor/appointments, POST /api/v1/lead-appointments/{id}/{confirm|complete|no-show|cancel|reschedule} (`api/api/lead_appointments.py:91,132-158`).
- Header: eyebrow "Appointments", "Lead appointments", "Counselling sessions telecallers booked with you for leads. Confirm them, then mark each one completed or a no-show." Filter "Status": All statuses, Scheduled, Confirmed, Rescheduled, Completed, Cancelled, No show. 20 per page, Previous/Next.
- Card: "<type> <code>", status badge; "When", "Lead", "Mobile", "Email", "Mode", "Meeting link", "Location", "Purpose", "Remarks", "Booked by", "Outcome notes"; "History (n)".
- Actions (`api/services/lead_appointments.py:176-187`): "Confirm" (allowed transition); "Mark completed" / "Mark no-show" only once the start time has passed; "Reschedule" ("New date and time (IST)", "Reason (optional)", "Save new time"), "Cancel appointment" ("Reason for cancelling" required); "Back". Errors "Add a reason for cancelling.", "Choose the new date and time.", "Choose a time in the future", "The counselor already has an appointment at this time", "Only the counselor can do this", "Appointment is already <status>". Success "Appointment <status>." (F8).
- Below: payload table "Student appointments" + WorkflowPanel "Schedule appointment" / "Update appointment" (student appointments; status options scheduled/completed/cancelled/no_show) (`web/components/WorkflowPanel.tsx:245,338`).
- Empty: "No lead appointments booked with you yet." / "No <status> lead appointments."
- Prerequisites: telecaller-booked appointments (tel-016) with this counselor, one in the past (for complete/no-show).

### DOC-CNS-CAL-002 Calendar feed (iCal)
- Route /overseas/counselor/calendar; sidebar "Calendar". `web/components/CounselorCalendarFeed.tsx`; API GET/POST/DELETE /api/v1/counselor/calendar-feed; feed GET /api/v1/calendar/feeds/{token}.ics (no login) (`api/api/calendar_feeds.py`).
- Title "Calendar": "Appointment emails carry a calendar invite (.ics). Add the feed below to see every appointment in your own calendar." Card "Calendar feed": "Subscribe to this private link in Google Calendar, Outlook or Apple Calendar to see your counselling appointments and your students' visa appointments. It is read-only: changes made in your calendar app do not come back to EduSphere." "Status: On (link created <time>)" / "Off".
- Off: "Create calendar link". On: "Create a new link" (confirm "Create a new link? The current link stops working at once, so calendars subscribed to it stop updating."), "Turn off feed" (confirm "Turn off the calendar feed? The link stops working at once and subscribed calendars stop updating.") (`web/lib/counselorCalendar.ts`).
- After create: "Your calendar link" + "Copy link"; "Your calendar link is ready. Copy it now: for your security it is shown only once."; "Link copied. Paste it into your calendar app's “subscribe to calendar” option." / "Copy the selected link by hand (Ctrl+C or long-press)."; warning "Anyone with this link can see these appointments. Don't share it."; off: "The calendar feed is off. The old link no longer works."
- Feed: calendar "EduSphere appointments", 90-day look-back, max 500 events (`api/services/calendar_feeds.py:19-22`).

## REP - Reports

### DOC-CNS-REP-001 My performance
- Route /overseas/counselor/reports; sidebar "Reports". `web/components/CounselorPerformance.tsx`; API GET /api/v1/counselor/performance (`api/api/counselor_performance.py`).
- Title "My performance": "Your leads, follow-ups, tasks and conversions for a period, and your applications, offers, visas and enrolments now."
- Filters (GET form "Choose a period"): "From", "To" (required dates; default this month), intake filter, "Lead division" (All divisions / Overseas / IT); "Show", "This month". Empty values are stripped from the URL (`reports/page.tsx:18-19`).
- "In the period" ("<from> to <to>, India time (IST). Counted the same way as the management counseling dashboard."): Leads, Overseas leads, IT leads, Leads assigned, Calls, Counseling sessions, Follow-ups, Conversions, Conversion %, Lead follow-ups due, Lead follow-ups completed, Follow-up completion %, Tasks completed (`api/services/counselor_performance.py:30-44`). Zero-denominator shares show "No leads assigned" / "No follow-ups due".
- "Now": Overdue tasks, Overdue follow-ups, Applications, Students, Offers, Visas pending/approved/refused, Enrolments, Documents pending verification.
- Table "Applications by stage and sub-status": Stage, Sub-status, Applications, Students, Total row; definitions list below. Empty "No applications are assigned to you yet."
- Errors: "Your performance figures are unavailable right now. Please try again."; 422 "Choose the Overseas or IT lead division".

## UNI - Universities

### DOC-CNS-UNI-001 Partner universities list
- Route /overseas/counselor/universities; sidebar "Universities". Page `web/app/overseas/counselor/universities/page.tsx`; API GET /api/v1/public/universities?q=.
- Eyebrow "Universities", "Partner universities", "What each university offers: courses, entry and English requirements, contacts and documents." Search "Search by name or city" (100) + "Search" (GET form). Cards: name (link) + city; first 50 + "Showing 50 of N. Search to narrow the list."; empty "No universities match “<q>”." / "No universities are published yet."
- Prerequisite: published, active universities.

### DOC-CNS-UNI-002 University 360 view
- Route /overseas/counselor/universities/[id]; "← All universities". `web/components/UniversityView.tsx`; API gate `api/services/university_view.py` ("University view access required").
- Sections: "Profile" (University ID, Institution type, Public / private, Country, State / region, City, Website, Course levels, Popular programmes, Campuses, Fee structure, Rankings, Overview, Eligibility), "Partnership", "Application contacts" ("Primary"; "No shareable contacts yet."), "Courses" ("No active courses yet."), "Documents" ("Download"; "No shareable documents yet."), applications table (Student, Reference, Intake, Status, Next action, Updated; "No applications for this university yet.") (`UniversityView.tsx:53-144`).
- Prerequisites: a university with contacts marked shareable, active courses, shareable documents, and an application by this counselor.

---

## Product finding candidates (neutral, for triage)

- F1 Reminder notifications have no counselor inbox: the rule engine writes `Notification` rows for the counselor (`api/services/counselor_reminders.py:189,305-349`) but the overseas counselor nav has no Notifications item (`web/lib/navigation.ts:292`) and no counselor notifications page exists (only agent/BDM/telecaller/school pages). NEEDS_CONFIRMATION whether email also goes out.
- F2 Return offered on a closed lead: `return` permission is "not linked" only (`api/services/lead_handover.py:124`); the "returned" event moves only stages up to Counselling Completed (`api/lead_stages.py:53`), so returning a closed lead clears the owner but leaves it closed and records no history row with the reason, while the form says "The lead goes back to Follow-up" (`web/components/CounselorLeadDetail.tsx:96`).
- F3 Super Admin on counselor `[section]` pages: portal payload admits super_admin (`api/api/portal.py:43`) but `/counselor/leads` and `/counselor/dashboard` refuse non-counselors (`lead_handover.py:99-100`, `counselor_dashboard.py:19-20`), so they see "Unable to load your leads." / "Dashboard sections are unavailable right now." rather than an access message.
- F4 Counselor-facing messages point to roles the counselor may not have: "No lost reasons are set up yet. Ask a telecaller manager to add one." (`web/components/AdminLeadStage.tsx:136`); "This lead is closed. A manager can reopen it before …" (`api/services/lead_follow_ups.py:32`, `lead_calls.py:43`, `lead_messages.py:38`) - counselors cannot reopen and have no manager in this flow.
- F5 Dashboard "View all" targets are unfiltered: "Calls logged today", "Follow-ups due" and "Leads without a next action" all link to plain My leads (`web/components/CounselorDashboardPanel.tsx:20-23`), which has no follow-up/next-action/call filter.
- F6 My leads has a Priority filter but no Priority column (`web/components/CounselorLeadsPanel.tsx:75,122-127`); the export does include Priority (`api/api/crm_exports.py:46`). Column "Interest" is the free-text subject, while detail uses "Product interest" for the product.
- F7 Quick-search application hits open the applications list filtered by university + intake, not the application (`api/services/counselor_search.py:117-121`; comment "no counselor application page yet").
- F8 Appointment success text is built from the lowercased status: no-show gives "Appointment no show." (`web/components/LeadAppointmentCard.tsx:58`, `web/lib/leadAppointments.ts:25-27`).
- F9 Performance "Leads" counts every lead the counselor owns across Overseas and IT (`api/services/counselor_performance.py:32-34,98-101`), while My leads shows only the counselor's own division (`lead_handover.py:101`); an overseas counselor seeing an "IT leads" figure may be unexpected.
- F10 Quick-search text "Showing the first 10 -- refine your search." shows a literal double hyphen to users (`web/components/CounselorQuickSearch.tsx:76`).
- F11 Naming mismatch sidebar vs page: "Tasks" -> "My tasks", "Leads" -> "My leads", "Reports" -> "My performance" (docs should name both).
- F12 Task list band "Cancelled" exists in the UI (`web/lib/counselorTasks.ts` BANDS) but the API list returns only overdue/today/upcoming/done (`api/services/counselor_tasks.py:28`), so cancelled tasks disappear from the counselor's page with no way to view them.
- F13 The counselor lead page has no lead-appointment section and the counselor cannot book a counselling appointment for a lead; "Counselling Scheduled" can be set manually without any appointment (`web/lib/leadStages.ts:47`). NEEDS_CONFIRMATION whether intended.

## Could not determine (static read only)
- Exact rendering of the dashboard table "Status" cell (raw key vs label) - depends on `PortalSection`; verify in browser.
- Whether the walk-in lead shows "Assigned" or "New Lead" right after creation (depends on distribution rules at run time).
- `LeadTimeline` event wording per event type (not enumerated here).
- IT-division counselor behaviour (shares `CounselorLeadDetail`; Convert hidden) - outside this Overseas scope.
