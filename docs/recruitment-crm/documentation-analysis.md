# EduSphere Recruitment CRM — Documentation Analysis (Phase 1 scope)

> Analysis date 2026-11-18 · Code baseline `main` @ `6b61546c` · Read from the code; nothing here is browser-verified yet. Every feature page is verified in the browser in its capture session before it is written.

## 1. Application Overview

### 1.1 What the Recruitment CRM is
EduSphere's recruitment business has three parts:
- **Business development:** find companies that hire, win their job requirements and agree commercial terms.
- **Sourcing:** fill those requirements from a candidate pool. The pool holds external candidates (website, imports) and EduSphere's own IT students who opted in.
- **Hiring:** take candidates through screening, profile sharing, interviews, results, offers and joining, and close the placement.

HR and the HR Manager control quality (resume reviews, vacancy approvals, result release, data requests). Interviewers give feedback. Candidates follow their applications in their own portal.

### 1.2 Owner scope decisions (2026-11-18)
| ID | Decision |
|---|---|
| R1 | **Core first.** Phase 1 (this set) covers the hiring flow and the role portals. **Phase 2**, later in the same folder, covers vendors, campus drives, colleges and the campus calendar, receivables, targets, daily plans, activity reports, the management/business and performance dashboards, placement outcomes, insights, report libraries and recruitment dashboards. |
| R2 | Phase 1 also covers the **external candidate portal**, the **IT student opt-in** to the candidate pool, and the **admin set-up of recruitment staff**. Only recruitment-related admin screens are in scope. |
| R3 | **Placements are closed for real** with fictional Docs data, so the joined, guarantee and **invoice draft** states can be shown. **No money is ever recorded:** no Record payment, no Receivables entry, and Issue invoice only as a screenshot. |
| Stack | Reuse the `itcdocs` documentation stack (same code `6b61546c`). The IT students created for `docs/it-counselor-crm/` feed the opt-in pages. |

### 1.3 Roles and sign-in
| Role (code) | Shown as | Signs in at | Lands on |
|---|---|---|---|
| `placement_team` | Recruiter | `/it/login` | `/recruiter/dashboard` |
| `placement_manager` | Placement Manager / Team Lead (global) | `/admin/login` | `/recruiter/manager/team` |
| `placement_officer` | Placement Officer | `/it/login` | `/it/placement-officer/dashboard` |
| `hr_team` | HR Team | `/it/login` | `/it/hr/dashboard` |
| `hr_manager` | HR Manager | `/it/login` | `/it/hr-manager/dashboard` |
| `interviewer` | Interviewer | `/it/login` | `/it/interviewer/dashboard` |
| `candidate` | External candidate | `/it/login` (email verified first) | `/it/careers/portal/profile` |
| `it_admin` / `super_admin` | Admins (set-up only) | `/it/login` / `/admin/login` | — |

A wrong portal is refused with "sign in at …" (API `PORTAL_SIGN_IN`). Signed-out visitors to `/recruiter/*` go to `/it/login`; `/recruiter/manager/*` goes to `/admin/login`.

### 1.4 Cross-cutting rules to explain in every manual
- **Scope.** A recruiter sees their own companies, requirements and candidates. A Team Lead sees the team plus unassigned records. HR reads only. A Placement Officer sees only the requirements they co-own, and no candidates.
- **Permissions** are keys with default holders (`apps/api/app/core/rbac.py`), which the Super Admin can change per role or per user:
  - **Recruiter:** compensation view, candidate import, client and vendor commercials, placement and recruitment reports.
  - **Team Lead:** the recruiter's keys plus merge, export, job publish, notification retry, insights, CRM import and CRM merge.
  - **HR Manager:** job approval, candidate erase, notification retry, result release.
- **Statuses.**
  - **Requirement:** New, Pending Approval, Requirement Received, Sourcing, Shortlisting, Profiles Shared, Interviewing, Selected, Joined, Filled, On Hold, Closed, Cancelled.
  - **Application:** Sourced, Screened, Shortlisted, Profile Shared, Interview, Selected, Joined, Rejected, Withdrawn.
  - **Company pipeline:** 8 manual stages, then stages set by events.
- **WhatsApp** opens `wa.me`; a record is saved only after "Yes, record as sent". **LinkedIn** messages and calling scripts are copy-only. **Email** goes out through the server (Mailpit on the docs stack).
- Interview platforms (Google Meet, Teams, Zoom, Zoho Meeting) are labels on a meeting-link field only.

## 2. Module Inventory
| Module | Folder | Who |
|---|---|---|
| Account access, navigation | `account-access`, `navigation` | All roles |
| Dashboards | `dashboard` | Recruiter, Team Lead, HR, HR Manager, Placement Officer |
| Masters and templates | `masters` | Recruiter (read), Team Lead (manage) |
| Companies | `companies` | Recruiter, Team Lead |
| Job requirements | `requirements` | Recruiter, Team Lead, Placement Officer |
| Candidates | `candidates` | Recruiter, Team Lead, HR (read) |
| Search and pools | `search` | Recruiter, Team Lead, HR (read) |
| Hiring flow | `hiring` | Recruiter, Team Lead |
| Daily work | `work` | Recruiter, Team Lead |
| HR Team | `hr` | HR Team |
| HR Manager | `hr-manager` | HR Manager |
| Placement Officer | `placement-officer` | Placement Officer |
| Interviewer | `interviewer` | Interviewer |
| Candidate portal | `candidate-portal` | External candidate |
| IT student opt-in | `student` | IT student, staff |
| Administration | `admin-manual/admin` | IT Admin, Super Admin, Team Lead |

## 3. Feature Inventory (119 Doc IDs, `DOC-REC-<MOD>-NNN`)

### Account access and navigation
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| AUTH-001 | Sign in (staff at /it/login, Team Lead at /admin/login, wrong-portal message) | login pages | rec-001 |
| AUTH-002 | Set your first password (welcome link) | reset page | rec-001 |
| AUTH-003 | Forgot / reset your password | forgot page | — |
| AUTH-004 | Recruiter profile (mobile only editable) and My profile | `/recruiter/profile` | rec-001 |
| AUTH-005 | Sign out, deactivated account | — | rec-037 |
| NAV-001 | Recruiter workspace tour (27 items, legacy links) | sidebar | rec-001 |
| NAV-002 | Team Lead workspace tour | sidebar | rec-001 |
| NAV-003 | HR, HR Manager, Placement Officer and Interviewer portal tour | IT portals | hrc-002 |

### Dashboards
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| DASH-001 | Recruiter dashboard: tiles, quick actions, Find Candidates by Skill | `/recruiter/dashboard` | rec-032 |
| DASH-002 | Team Lead dashboard view (Whole team / one recruiter) | same | rec-032 |
| DASH-003 | HR dashboard | `/it/hr/dashboard` | — |
| DASH-004 | HR Manager dashboard | `/it/hr-manager/dashboard` | hrc-002 |
| DASH-005 | Placement Officer dashboard | `/it/placement-officer/dashboard` | hrc-002 |

### Masters and templates
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| MST-001 | Skills Master (read) | `/recruiter/skills` | rec-006 |
| MST-002 | Manage skills, categories, aliases, merge | `/recruiter/manager/skills` | rec-006, hrc-017 |
| MST-003 | Catalogues (sources, industries, lost reasons, tags, campaigns, exchange rates) | `/recruiter/manager/catalogue` | rec-002 |
| MST-004 | Message template library (add, preview, versions) | `/recruiter/templates` | rec-026, pob-023 |
| MST-005 | Approve shared templates | `/recruiter/manager/templates` | pob-023 |
| MST-006 | Screening question bank and form templates | `/recruiter/screening-bank` | pob-020 |

### Companies
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| CO-001 | Companies list and filters | `/recruiter/companies` | rec-003 |
| CO-002 | Add a company / Add recruiter (company + first contact) | `/recruiter/companies/new` | rec-003, rec-004 |
| CO-003 | Company page, edit, archive / restore | company page | rec-003, pob-003 |
| CO-004 | Company contacts | Contacts | rec-004, pob-005 |
| CO-005 | Log calls | Calls | rec-025, pob-007 |
| CO-006 | Company follow-ups | Follow-ups | rec-024 |
| CO-007 | Company meetings and outcomes | Meetings | rec-028 |
| CO-008 | Contract / MoU (terms, document, renewal; no money) | Contract / MoU | rec-030 |
| CO-009 | Messages: WhatsApp, email, LinkedIn, calling script, replies | Messages | rec-026, pob-023 |
| CO-010 | Pipeline stage, lost, inactive, reopen, client status | Pipeline | rec-005, pob-004 |
| CO-011 | Documents, timeline, shared profiles | company page | rec-027, pob-003 |
| CO-012 | Import companies | `/recruiter/companies/import` | pob-006 |
| CO-013 | Merge a duplicate company or contact | merge pages | pob-006 |
| CO-014 | Pipeline board | `/recruiter/pipeline` | rec-005 |
| CO-015 | Outreach cadences (Team Lead; start/stop from Messages) | `/recruiter/manager/cadences` | pob-008 |

### Job requirements
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| REQ-001 | Requirements list and filters | `/recruiter/requirements` | rec-007 |
| REQ-002 | Add a job requirement | `/requirements/new` | rec-007, hrc-005 |
| REQ-003 | Requirement page, edit, change status | requirement page | rec-007 |
| REQ-004 | Job description: create, upload, versions | JD | rec-008 |
| REQ-005 | Validation checklist and requirement tasks | Checklist, Tasks | pob-016 |
| REQ-006 | Sourcing plan and source funnel | Sourcing | pob-017 |
| REQ-007 | Submit for approval | Approval | hrc-007 |
| REQ-008 | Visibility (public, portal, segment, internal) | Visibility | hrc-008 |
| REQ-009 | Owners, placement officer, collaborators, assignment | Owners | hrc-006 |
| REQ-010 | Commercial terms (view; no money) | Commercial terms | pob-002 |

### Candidates
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| CAN-001 | Candidate Master list and filters | `/recruiter/candidates` | rec-009 |
| CAN-002 | Add a candidate (duplicate check, basis for holding data) | `/candidates/new` | rec-009, hrc-010 |
| CAN-003 | Candidate page, edit, archive, completeness | candidate page | rec-009 |
| CAN-004 | Ownership: primary recruiter, placement officer, collaborators | Ownership | hrc-012 |
| CAN-005 | Skills and tags | Skills, Tags | rec-011, pob-019 |
| CAN-006 | Resume upload and extracted details | Resume | rec-012, hrc-015 |
| CAN-007 | Document requests | Documents | hrc-015 |
| CAN-008 | Notes, tasks, timeline, change history | candidate page | hrc-016, hrc-004 |
| CAN-009 | Calls and messages to a candidate | Calls, Messages | rec-025, rec-026 |
| CAN-010 | Source, verification and permission to represent | Source and outreach | pob-018 |
| CAN-011 | Import candidates | `/candidates/import` | hrc-013 |
| CAN-012 | Duplicate review and merge | `/candidates/duplicates` | hrc-014 |
| CAN-013 | Unassigned queue and routing rules | `?owner=unassigned`, `/manager/routing` | hrc-024 |
| CAN-014 | Website registrations | `/recruiter/website-registrations` | hrc-025 |

### Search and pools
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| SRCH-001 | Find Candidates: skills AND/nice-to-have, Why matched | `/recruiter/find-candidates` | rec-013 |
| SRCH-002 | Resume search and refine filters | same | rec-014, hrc-019 |
| SRCH-003 | Saved searches and export | same | hrc-020 |
| SRCH-004 | Bulk actions: shortlist, share, assign task | same | pob-019 |
| SRCH-005 | Talent pools | `/recruiter/pools` | rec-015 |

### Hiring flow
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| HIRE-001 | Candidates on a requirement and application statuses | requirement page | rec-017, hrc-026 |
| HIRE-002 | Matching candidates and match weights | Matching | rec-016, hrc-018 |
| HIRE-003 | Screening form, screening checklist and sessions | Screening | rec-018, pob-020 |
| HIRE-004 | Share profiles with the client (consent, detail level) | share dialog | rec-019, pob-021 |
| HIRE-005 | Submission status and client response | Shared profiles | pob-021 |
| HIRE-006 | Schedule an interview and its panel | Interviews | rec-020, hrc-029 |
| HIRE-007 | Interviews list, reschedule, status, cancel | `/recruiter/interviews` | rec-020, hrc-028 |
| HIRE-008 | Recruiter interview feedback | Interviews | rec-021 |
| HIRE-009 | Interview automation (reminders, feedback chase) | Team Lead | pob-022 |
| HIRE-010 | Offers: record, status, offer letter | Offer | rec-022 |
| HIRE-011 | Joining: Joined / Did not join, proof | Joining | rec-023 |
| HIRE-012 | Joinings list | `/recruiter/joinings` | rec-023 |
| HIRE-013 | Placement record and confirmations | `/recruiter/placements` | pob-024 |
| HIRE-014 | Invoice draft (view, discard; Issue screenshot only) | placement page | pob-024 |
| HIRE-015 | Guarantee, dropout and replacement | placement page | pob-025 |
| HIRE-016 | Satisfaction surveys | placement page | pob-026 |

### Daily work
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| WORK-001 | Follow-ups (Today, Overdue, Upcoming) | `/recruiter/follow-ups` | rec-024 |
| WORK-002 | My tasks | `/recruiter/tasks` | hrc-016 |
| WORK-003 | Meetings list | `/recruiter/meetings` | rec-028 |
| WORK-004 | Notifications | `/recruiter/notifications` | hrc-032 |
| WORK-005 | Intake automation and escalation rules (Team Lead) | `/recruiter/manager/automation` | pob-027 |

### HR Team, HR Manager, Placement Officer, Interviewer, legacy
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| HR-001 | Job requirements and shortlists (read) | `/it/hr/job-requirements`, `/shortlists` | — |
| HR-002 | Candidate database and interviews (read) | `/it/hr/candidates`, `/interviews` | — |
| HR-003 | Placement reports | `/it/hr/reports` | — |
| HR-004 | Students in the placement pool and the student page | `/it/hr/students` | nehn-017 |
| HR-005 | Resume review queue and review | `/it/hr/queue` | itc-027 |
| HR-006 | Candidate Master, Find Candidates and Pools (read only) | `/recruiter/*` | rec-009 |
| HRM-001 | Vacancy approvals | `/it/hr-manager/approvals` | hrc-007 |
| HRM-002 | Result approvals and publishing | `/it/hr-manager/results` | hrc-030 |
| HRM-003 | Candidate data requests and retention | `/it/hr-manager/data-requests` | hrc-035 |
| HRM-004 | Delivery exceptions and retry | `/recruiter/notification-exceptions` | hrc-032 |
| HRM-005 | Website registrations (read) | `/recruiter/website-registrations` | hrc-025 |
| PO-001 | Co-owned requirements: edit and change status | `/recruiter/requirements` | hrc-006 |
| INT-001 | My interviews | `/it/interviewer/dashboard` | hrc-029 |
| INT-002 | Submit interview feedback | same | hrc-029 |
| LEG-001 | Legacy placement screens (`/it/placement/*`) | legacy | ADM-007/008 |

### Candidate portal and IT student opt-in
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| CAND-001 | Careers page and Apply online | `/it/careers` | hrc-023 |
| CAND-002 | Track an application | `/it/careers` | hrc-022 |
| CAND-003 | Create a candidate account and verify email | `/it/careers/register` | hrc-022 |
| CAND-004 | Candidate profile and change email | `/portal/profile` | hrc-022 |
| CAND-005 | Jobs for you and apply | `/portal/jobs` | hrc-027 |
| CAND-006 | My applications and offers | `/portal/applications` | hrc-031 |
| CAND-007 | Interviews and results | `/portal/interviews`, `/results` | hrc-030 |
| CAND-008 | Documents | `/portal/documents` | hrc-015 |
| CAND-009 | Notifications | `/portal/notifications` | hrc-031 |
| CAND-010 | Privacy: pool consent and data deletion | `/portal/privacy` | hrc-035 |
| STU-001 | IT student joins / leaves the placement pool | `/it/student/placement-status` | rec-010 |
| STU-002 | What staff see: Journey and training progress | candidate page | rec-036 |

### Administration
| Doc ID | Feature | Where | Backlog |
|---|---|---|---|
| ADM-001 | Create a recruiter (Recruiter Staff) | `/it/admin/recruiter-staff`, `/admin/recruiter-staff` | rec-001 |
| ADM-002 | Create other recruitment users (HR, HR Manager, PO, Interviewer, Team Lead) | Users | hrc-002 |
| ADM-003 | Edit, deactivate, reactivate a recruiter | Recruiter Staff | rec-037 |
| ADM-004 | Team page and bulk reassignment (Team Lead) | `/recruiter/manager/team` | rec-037 |
| ADM-005 | Permission matrix and user overrides (Super Admin) | `/admin/permissions` | hrc-002 |
| ADM-006 | Approval sources, automatic result release, retention rule (Super Admin) | HR Manager queues | hrc-007/030/035 |
| ADM-007 | Candidate collaborators and self-service fields | Candidate Master | hrc-012, hrc-022 |
| ADM-008 | Match weights | Requirements | hrc-018 |

## 4. Role differences worth a "What each role sees" table
- Candidate Master, Find Candidates and Pools: Recruiter and Team Lead write; HR reads only; the Placement Officer has no access.
- Requirements: Recruiter (own), Team Lead (team and unassigned), Placement Officer (co-owned, no candidate sections), HR (legacy read-only list).
- Follow-ups, Meetings, Interviews, Joinings: the Recruiter works them; the Team Lead reads the team's.
- Templates: the Recruiter adds them (shared ones stay Draft); the Team Lead approves.

## 5. Background jobs (`apps/api/app/worker.py`), Phase 1
| Job | When | Shown in |
|---|---|---|
| `hrc032-feedback-overdue` | Hourly :10 | INT-002, WORK-004 (feedback overdue notices) |
| `hrc032-new-matches` | Hourly :40 | CAND-005, CAND-009 |
| `pob004-company-inactive-sweep` | 01:00 IST | CO-010 (Inactive after 182 days) |
| `pob022-interview-reminders` | Every 15 min | HIRE-009 |
| `pob022-feedback-chase` | Hourly :20 | HIRE-009, WORK-001 |
| `pob008-follow-up-reminders`, `pob008-cadences` | 5 / 15 min | CO-006, CO-015 |
| `pob027-escalations` | Every 15 min | WORK-005 |
| `pob024-invoice-notices` | 08:45 IST | HIRE-014 (notice only) |
| `pob025-guarantee-alerts` | 09:15 IST | HIRE-015 |
| `pob026-placement-surveys` | 09:00 IST | HIRE-016 |
| `hrc035-candidate-retention` | 02:00 IST | HRM-003 (off until a period is set) |

Time states are prepared as in the IT Counselor set: back-date rows with SQL on the `itcdocs` database only, run the job with `celery call`, and label the screenshot "state prepared by data setup".

## 6. External services in the docs stack
- **Email:** SMTP to Mailpit only (127.0.0.1:8032). Mailpit is never screenshotted.
- **WhatsApp:** `wa.me` is blocked in the browser and the send is recorded only. Twilio is not configured.
- **Files:** local storage. Resume extraction runs locally.
- **Money:** the requirement **Revenue** section (Add invoice, **Record payment**) and Receivables are never used (R3).

## 7. Required Test Data (through the UI; `Docs ` prefix; `@example.test` unless a public form refuses it)
| Persona | Role | Created by |
|---|---|---|
| Docs Recruiter A, Docs Recruiter B | `placement_team` | IT Admin, Recruiter Staff (manager: Docs Team Lead) |
| Docs Team Lead | `placement_manager` | Super Admin, Users |
| Docs Placement Officer | `placement_officer` | IT Admin, Users |
| Docs HR, Docs HR Manager | `hr_team`, `hr_manager` | IT Admin / Super Admin |
| Docs Interviewer | `interviewer` | IT Admin, Users |

Records:
- **Companies:** Docs Acme Technologies, with contacts Docs Priya HR Lead and Docs Rahul Hiring Manager, and Docs Beta Systems.
- **Requirement:** Docs Python Developer (2 vacancies).
- **Candidates:** Docs Candidate Kiran and Docs Candidate Meena, added by hand; one imported; one duplicate.
- **External candidate:** registers on `/it/careers/register`. The public forms may refuse `.test`, in which case use `@example.com`, as the Counselor set did.
- **IT student:** Docs IT Lead Arjun, from the IT Counselor set, joins the placement pool.

## 8. Unknown workflows requiring browser verification
1. Whether a placement closed with fictional data creates the invoice draft at once, and whether **Discard draft** is safe to use.
2. Interview feedback timing ("Feedback opens once the interview time has passed") needs a back-dated interview.
3. The candidate verification email link in Mailpit, and whether `.test` addresses are accepted on `/it/careers/register`.
4. The duplicate checks on candidate create and import.
5. The approval sources defaults: which requirement sources need HR Manager approval by default.

## 9. Product Findings and Open Questions (from code; confirm in the browser)
- **P1** The Team Lead's **Team** page has no Deactivate. Deactivation is on the admin Recruiter Staff page and is refused while the recruiter still holds companies or open requirements, so the Team Lead must **Reassign** first.
- **P2** The Placement Officer co-owns requirements but cannot see their candidates, matches or shares.
- **P3** HR's **Students** list uses "not withdrawn from the placement profile", while the Candidate Master uses the IT student's opt-in. The two lists can disagree.
- **P4** The HR Manager sees Website registrations but cannot open the candidate from there.
- **P5** The Team Lead is a global-division user and gets 403 on the legacy `/it/placement/*` screens that recruiters still use.
- **P6** Interview platform names are labels only. No meeting is created; the recruiter pastes the link.
- ~~P7~~ Checked in S2: the IT Admin's Create user form does **not** offer HR Manager; only the Super Admin creates one. Not a finding.
- **P8** (S6) **Start cadence** is offered on every unanswered message, but the API refuses it ("This contact has already replied") when the contact replied to any message or has a meeting booked. The button could be hidden for such contacts.
- **P9** (S6) Only the Team Lead can reopen a lost or inactive company. Once a recruiter marks their company lost, they see no action on the Pipeline card and must ask the Team Lead.
- **P10** (S6) Imported companies are unassigned; the Team Lead must assign each one from its company page (no bulk assign on the import result).
- **P11** (S6) The message composer locks **To** while it is open. Choosing a recipient after opening a composer has no effect, which is easy to miss.
- **P12** (S7) On Add job requirement, **Hiring manager** searches EduSphere staff accounts (only Docs Interviewer was offered), not the company's contacts; the client's person goes in **Decision-maker**. The two labels are easy to confuse.
- **P13** (S8) Candidate email fields (Add candidate, careers apply, registration) refuse addresses ending in `.test` with "Enter a valid email address", while staff and IT student accounts use `.test`. Not a defect for real use; noted because test data must use another domain.
- **P14** (S8) Profile completeness item **Contact verified** (10%) is met only when the candidate verifies their own email in the candidate portal. A recruiter's **Verify details** does not count, so recruiter-added candidates stop at 90%.
- **P15** (S8) Resume extraction filed "REST APIs" from a Python resume under the **Java Technologies** category, and new extracted skills start ticked, so saving without checking adds a mis-categorised skill.
- **P16** (S9) After a duplicate merge the surviving candidate shows the merged-in record's **Basis for holding**: Kiran's "They agreed to be in the candidate pool (added by a recruiter)" became "They shared their details for job placement (file import)". Both consent records are kept, but the profile shows only the newest, so the original consent is no longer visible.
- **P17** (S10) An application from the public careers page (`/it/careers`, no account) is stored apart from the hiring pipeline: it shows on the candidate page and Website registrations, but not on the requirement's **Candidates** list nor in the candidate's portal **My applications**, even after the person creates an account with the same email. A recruiter must add the candidate to the requirement by hand, or the applicant is easy to miss. Applying from the candidate portal does create the pipeline application.
- **P18** (S11) The schedule form's **Interviewer** field is free text that only labels the interview card. The interviewer gets nothing (no dashboard entry, no feedback form) until they are added on **Assign interviewers** (the panel). Two places to name an interviewer is easy to get wrong.
- **P19** (S11) The recruiter sidebar's **Offers** link opens the older Offer Management page (`/it/placement/offers`), which showed "0 role-scoped records" while Kiran's offer, recorded on the requirement, was accepted.
- **P20** (S11) HR's Job Requirements, Shortlists, Candidate Database and Interviews are older generic screens: internal UUIDs instead of REQ/INT codes, raw status values (`requirement_received`) and raw UTC timestamps. HR Interviews listed Nisha's interview (portal account) but not Kiran's, and showed Result "—" after her result was published. The Candidate Database lists IT students, not the recruitment Candidate Master.
- **P21** (S12) The placement's **PO owner** is set from the company's assigned recruiter (Docs Recruiter A), not from the requirement's **Placement officer owner** (Docs Placement Officer); only a Team Lead can change it. The same "PO owner" words mean different people on the requirement and the placement.
