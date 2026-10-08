# Role Navigation

Per-role navigation structure derived from `SCREEN_CATALOG.md`. Applies the confirmed UX principle from `CLAUDE.md`/the transcript: **clear, concise, minimal clutter — only relevant actions for the logged-in user.** A role's nav shows only its own screens; cross-role access attempts are blocked server-side (`FND-002`), not merely hidden.


## Visitor->Student/Trainer/Placement Team/HR Team/IT Admin

- `SCR-AUTH-001` — /it/login — IT-division login entry point.

## Visitor->Student/Counselor/University Rep/Agent/Overseas Admin

- `SCR-AUTH-002` — /overseas/login — Overseas-division login entry point, separate from IT login per the base codebase's division isolation.

## Visitor

- `SCR-PUB-001` — /it (Home) — IT division marketing homepage — hero, course discovery entry, career paths/projects/success-story teasers.
- `SCR-PUB-002` — /it/about — About EduSphere IT — mission, methodology, leadership.
- `SCR-PUB-003` — /it/career-paths — Career path list.
- `SCR-PUB-004` — /it/career-paths/[slug] — Career path detail.
- `SCR-PUB-005` — /it/projects — Real-world project list.
- `SCR-PUB-006` — /it/projects/[slug] — Project detail.
- `SCR-PUB-007` — /it/success-stories — Success story list.
- `SCR-PUB-008` — /it/success-stories/[slug] — Success story detail.
- `SCR-PUB-009` — /it/business-services — Business/corporate services overview.
- `SCR-PUB-010` — /it/blog — Blog list.
- `SCR-PUB-011` — /it/blog/[slug] — Blog post detail.
- `SCR-PUB-012` — /it/contact and /overseas/contact — Enquiry/callback form.
- `SCR-PUB-013` — /it/programs — Course catalogue with search/filter.
- `SCR-PUB-014` — /it/programs/[slug] — Course detail.
- `SCR-PUB-015` — /it/webinars — Webinar list.
- `SCR-PUB-016` — /it/webinars/[slug] — Webinar detail and registration.
- `SCR-PUB-017` — /news — News list (CMS-managed).
- `SCR-PUB-018` — /news/[slug] — News article detail.
- `SCR-PUB-019` — /gallery — Gallery (CMS-managed).
- `SCR-OVS-001` — /overseas/countries, /overseas/countries/[slug] — Study-destination list and country detail.
- `SCR-OVS-002` — /overseas/universities, /overseas/universities/[slug] — University list and profile.
- `SCR-OVS-003` — /overseas/courses — Overseas course list.
- `SCR-OVS-008` — /overseas/scholarships — Scholarship list and apply.
- `SCR-OVS-009` — /overseas/events — Events/workshops list and register.

## Student

- `SCR-STU-001` — /student/enrol/[courseId] — Trainer/time-slot selection at enrolment.
- `SCR-STU-002` — /student (Dashboard) — Student home: progress, attendance, fees, jobs, upcoming assignments.
- `SCR-STU-003` — /student/live/[sessionId] — Join a live class.
- `SCR-STU-004` — /student/assignments — Assignment list.
- `SCR-STU-005` — /student/assignments/[id] — Assignment detail and submission.
- `SCR-STU-006` — /student/support — Support ticket list and create.
- `SCR-STU-007` — /student/attendance — Attendance and progress view.
- `SCR-STU-008` — /student/certificates — Certificate list and download.
- `SCR-STU-009` — /student/feedback/[courseId] — Course/trainer feedback form.
- `SCR-STU-010` — /student/agreements — Digital agreement review and acceptance.
- `SCR-STU-011` — /student/payments — Payment dashboard: total/paid/pending/next due.
- `SCR-STU-012` — /student/payments/pay — Payment checkout (Razorpay).
- `SCR-STU-013` — /student/invoices/[id] and /student/receipts/[id] — Invoice/receipt detail.
- `SCR-STU-014` — /student/profile — Profile and document management.
- `SCR-TRN-004` — /trainer/recordings — Recording list per batch.
- `SCR-TRN-005` — /trainer/resources/upload — Resource/notes upload.
- `SCR-TRN-012` — /trainer/questions/[id] — Q&A thread detail and reply.
- `SCR-OVS-001` — /overseas/countries, /overseas/countries/[slug] — Study-destination list and country detail.
- `SCR-OVS-002` — /overseas/universities, /overseas/universities/[slug] — University list and profile.
- `SCR-OVS-003` — /overseas/courses — Overseas course list.
- `SCR-OVS-004` — /overseas/apply — Overseas application/interest submission.
- `SCR-OVS-006` — /overseas/applications/[id] — Application status tracker (student-facing).
- `SCR-OVS-007` — /overseas/applications/[id]/documents — Document upload against checklist.
- `SCR-OVS-008` — /overseas/scholarships — Scholarship list and apply.
- `SCR-OVS-009` — /overseas/events — Events/workshops list and register.
- `SCR-VISA-001` — /overseas/applications/[id]/visa (Checklist) — Visa checklist and documentation.
- `SCR-VISA-002` — /overseas/applications/[id]/visa/prep — Visa interview preparation.
- `SCR-VISA-003` — /overseas/applications/[id]/visa/status — Visa approval status tracking.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Trainer

- `SCR-TRN-001` — /trainer/batches (My Batches) — List of assigned batches only.
- `SCR-TRN-002` — /trainer/batches/[id] — Batch detail: roster + schedule.
- `SCR-TRN-003` — /trainer (Dashboard/Calendar) — Today's sessions, pending reviews, unanswered Q&A.
- `SCR-TRN-004` — /trainer/recordings — Recording list per batch.
- `SCR-TRN-005` — /trainer/resources/upload — Resource/notes upload.
- `SCR-TRN-006` — /trainer/assignments — Assignment management list (draft/published/closed).
- `SCR-TRN-007` — /trainer/assignments/new — Assignment create/edit.
- `SCR-TRN-008` — /trainer/assessments — Assessment management (draft/scheduled), distinct type from assignments.
- `SCR-TRN-009` — /trainer/submissions/[id] — Submission review and grading.
- `SCR-TRN-010` — /trainer/attendance/[sessionId] — Attendance marking.
- `SCR-TRN-011` — /trainer/questions — Q&A inbox (unanswered/assigned/resolved).
- `SCR-TRN-012` — /trainer/questions/[id] — Q&A thread detail and reply.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## IT Admin

- `SCR-ADM-001` — /it/admin (Operations Dashboard) — IT Admin landing dashboard.
- `SCR-ADM-002` — /it/admin/users, /it/admin/users/[id] — User/Student/Trainer directory and detail.
- /it/admin/counselors — *(tel-017, `DEC-SCOPE-076`)* the IT division's counselors (same directory as Trainers); Create user offers Counselor.
- `SCR-ADM-003` — /it/admin/courses — Course management.
- `SCR-ADM-004` — /it/admin/leads (Enquiries) — Enquiry/lead list synced via the CRM webhook.
- `SCR-ADM-005` — /it/admin/batches, /it/admin/batches/[id] — Batch creation and trainer assignment.
- `SCR-ADM-006` — /it/admin/enrolments, /it/admin/enrolments/[id] — Enrolment review and approval.
- `SCR-ADM-007` — /it/admin/certificates — Certificate administration (admin-issue path).
- `SCR-RPT-001` — /it/admin/reports — Domestic/Employer/Placement reporting dashboard.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Placement Team

- `SCR-ADM-008` — /it/placement/candidates — [base] Candidate pool.
- `SCR-ADM-009` — /it/placement/company-requirements — [base] Company hiring requirements review.
- `SCR-ADM-010` — /it/placement/interviews — [base] Interview coordination and offer/joining tracking.
- `SCR-RPT-001` — /it/admin/reports — Domestic/Employer/Placement reporting dashboard.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## HR Team

- `SCR-ADM-012` — /it/hr/job-requirements — [base] Hiring requirement intake.
- `SCR-ADM-013` — /it/hr/candidates — [base] Shortlist coordination.
- `SCR-ADM-014` — /it/hr/interviews — [base] Interview coordination.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Super Admin

- `SCR-ADM-015` — /admin (Super Admin console) — [base] Cross-division dashboard.
- `SCR-ADM-016` — /admin/content, /admin/blogs, /admin/events — [base] CMS management.
- `SCR-ADM-017` — /admin/security-logs, /admin/backups — [base] Security logs and backups.
- `SCR-SCH-021` — /overseas/admin/school-staff — Create/manage Academic Team, Career Counselor, Psychometric Team accounts and their school portfolios, cross-division *(net-new, added 2026-09-14, `DEC-SCOPE-014`)*.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Employer

- `SCR-EMP-001` — /employer/register — [new] Employer registration.
- `SCR-EMP-002` — /employer (Dashboard) — [new] Employer landing dashboard.
- `SCR-EMP-003` — /employer/jobs, /employer/jobs/new — [new] Job posting list and create/edit.
- `SCR-EMP-004` — /employer/candidates — [new] Candidate search.
- `SCR-EMP-005` — /employer/candidates/[id] — [new] Candidate profile detail.
- `SCR-EMP-006` — /employer/shortlist — [new] Shortlist management.
- `SCR-EMP-007` — /employer/interviews/new — [new] Interview scheduling.
- `SCR-EMP-008` — /employer/interviews — [new] Interview list and status.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Counselor

- `SCR-OVS-005` — /overseas/students/[id]/evaluate — Eligibility evaluation (Counselor-side).
- `SCR-VISA-001` — /overseas/applications/[id]/visa (Checklist) — Visa checklist and documentation.
- `SCR-VISA-003` — /overseas/applications/[id]/visa/status — Visa approval status tracking.
- `SCR-CNS-001` — /overseas/counselor (Dashboard) — [base] Counselor landing dashboard.
- `SCR-CNS-002` — /overseas/counselor/students — [base] Assigned-student list.
- `SCR-CNS-003` — /overseas/counselor/appointments — [base] Appointment management.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## IT Counselor *(added 2026-10-06, `DEC-SCOPE-076`, `tel-017`)*

Role `counselor` in division `it`; signs in at `/it/login`; lands on `/it/counselor/dashboard`. Sidebar: Dashboard · Leads (C1; tel-016 adds
Appointments, tel-018 the student link). The overseas counselor pages show "Role/division mismatch" with a link back to the IT dashboard.

- /it/counselor/dashboard — leads routed to you, new leads, the five most recent.
- /it/counselor/leads — My Leads: IT enquiries whose owner is this counselor.

## Agent

- `SCR-AGT-001` — /overseas/agent/register — Agent self-registration.
- `SCR-AGT-003` — /overseas/agent (Dashboard: referred students) — Referred-student roster and status.
- `SCR-AGT-004` — /overseas/agent/commissions — Commission list (auto-accrued).
- `SCR-AGT-005` — /overseas/agent/commissions/[id]/claim — Commission claim action.
- `SCR-AGT-007` — /overseas/agent/team — The agency's Master accounts: list, invite, deactivate *(net-new, 2026-09-28, `AGN-001`)*.
- **Agency Staff (`AGN-002`, `AGN-003`):** staff never see Team or Commissions. They see **Reports** only when their Master has switched on
  their Reports permission (`can_view_reports`, off by default; `agentNavFor(nav, memberRole, permissions)` from `user.agent_permissions`).
  Masters' navigation is unchanged. A typed `/overseas/agent/reports` URL without the permission shows the access-unavailable card
  (server `403`). The Documents page gains a review queue only for Masters and staff with Verify (`SCR-AGT-005` AGN-003 update).
- **Staff activity (`AGN-021`, `DEC-SCOPE-046`):** an **Activity** button on each staff row of the Team page (`SCR-AGT-007`), visible to Masters only. No new navigation item; staff never reach the Team page.
- **Commission Revenue and report (`AGN-014`, `DEC-SCOPE-051`):** no navigation change. Masters see a **Revenue** metric on the Dashboard and a **Commission report** panel (filters, CSV) on their existing **Reports** page (`SCR-AGT-005` AGN-014 update). Staff never see either; staff with Reports switched on keep the commission-free staff report.
- `SCR-AGT-009` — /overseas/agent/universities — The agency's own university list (Master: add/edit/delete; Staff: view) *(net-new, 2026-10-01, `AGN-007`, `DEC-SCOPE-049`)*. **The Agent nav gains "Universities", visible to both Master and Staff** (it is not in the staff-hidden list in `lib/navigation.ts`; `navigation.agent.test.ts`). The student shortlist is a panel inside `SCR-AGT-008`'s detail view, not a nav item.
- **Staff Performance (`AGN-019`, `DEC-SCOPE-066` P7):** a Master-only sidebar item "Staff Performance" after Reports →
  `/overseas/agent/performance` (`SCR-AGT-011`); also linked from the dashboard staff table ("View staff performance"). Hidden from staff
  (`STAFF_HIDDEN`), with or without the reports toggle; a staff member who opens the address sees a Masters-only note and the API
  refuses them (`403`).
- **Master / Staff dashboard and the staff sidebar (`AGN-018`, `DEC-SCOPE-062` G4; relabel and link existing pages only — no access is removed):** `/overseas/agent/dashboard` (`SCR-AGT-003`) shows the agency KPI board to both roles — a Master the whole agency (with the Commission group and the Staff performance table), Staff their assigned students only. Navigation, both roles: **Applications** children now start with **All applications** (`/overseas/agent/applications`, the list's default — browser QA18-07), then the AGN-008 status filters; **Tasks** is labelled **Tasks & Follow-ups**. Staff only: **Students** becomes **My Students** with children **All** (`/overseas/agent/students`) and **Add** (`/overseas/agent/students?new=1`, which opens the existing add form once and then drops `new=1` from the URL); Masters keep **Students** without children. Unchanged: Universities, the Withdrawn filter, Reports gating, Team/Commissions hidden from staff, the unread badge; mobile shows children as "Parent: Child" (e.g. "My Students: Add"). **No Journey link** until a route exists.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Overseas Admin

- `SCR-AGT-002` — /overseas/admin/agents — Agent approval queue (Overseas Admin side); since `AGN-001` it acts on agent organisations (approve / reject / suspend / reinstate).
- `SCR-AGT-006` — /overseas/admin/commissions — Commission payout approval queue.
- `SCR-SCH-010` — /overseas/admin/schools — All partner schools + create School/seed Coordinator on the same screen *(net-new, added 2026-09-14, `DEC-SCOPE-012`; `SCR-SCH-011`'s separate `/new` route merged in during `SCH-003`'s build, same day)*.
- `SCR-SCH-021` — /overseas/admin/school-staff — Create/manage Academic Team, Career Counselor, Psychometric Team accounts and their school portfolios *(net-new, added 2026-09-14, `DEC-SCOPE-014`)*.
- `SCR-SCH-031` — /overseas/admin/school-transfers — Approve or reject school transfer requests (`ENH-005`, added 2026-09-21).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## University Representative

- `SCR-UNI-001` — /overseas/university (Dashboard) — [base] University Rep landing.
- `SCR-UNI-002` — /overseas/university/applications/[id] — [base] Application review and offer-letter tracking.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Principal *(net-new, added 2026-09-14, `DEC-SCOPE-011`)*

- `SCR-SCH-013` — /school/invite/[token]/accept — **True first entry point**: accepting the School Coordinator's invite (`DEC-SCOPE-012`), before any dashboard nav exists.
- `SCR-SCH-001` — /school/principal (Dashboard) — School-wide read-only progress overview.
- `SCR-SCH-026` — /school/principal/students/[id] — One student's Journey Timeline (`SCH-008`, added 2026-09-15).
- `SCR-SCH-035` — /school/principal/students/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (from the student page's "Open 360° view") (`ENH-013`, added 2026-09-23).
- `SCR-SCH-036` — /school/principal/notifications — Own notifications, e.g. partnership tier changes (`ENH-023`, added 2026-09-23).
- `SCR-SCH-038` — /school/principal/global-education — Global Education: the school's students on the global education pathway, a funnel and a per-student high-level stage list; sidebar label "Global Education", after "Reports" (`ENH-017`, added 2026-09-29).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## School Coordinator *(net-new, added 2026-09-14, `DEC-SCOPE-011`/`DEC-SCOPE-010` part 1/`DEC-SCOPE-012`)*

- `SCR-SCH-002` — /school/coordinator (Dashboard) — Coordinator landing view.
- `SCR-SCH-003` — /school/coordinator/students — Student roster, view/edit.
- `SCR-SCH-004` — /school/coordinator/students/new — Add one student by hand.
- `SCR-SCH-025` — /school/coordinator/students/[id] — One student's Journey Timeline (`SCH-008`, added 2026-09-15).
- `SCR-SCH-027` — /school/coordinator/promotion — Promote or hold back students at academic-year rollover (`ENH-004`, added 2026-09-19).
- `SCR-SCH-029` — /school/coordinator/transfers — Request a student transfer (either direction), track and cancel requests (`ENH-005`, added 2026-09-21).
- `SCR-SCH-030` — /school/coordinator/notifications — The school's in-app notices, including transfer decisions (`ENH-005`, added 2026-09-21).
- `SCR-SCH-005` — /school/coordinator/students/bulk-upload — Bulk roster upload (template-download-first).
- `SCR-SCH-006` — /school/coordinator/activities — Schedule activities, track attendance.
- `SCR-SCH-012` — /school/coordinator/team — Invite Principal/Teacher/Parent accounts.
- `SCR-SCH-035` — /school/coordinator/students/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (from the student page's "Open 360° view") (`ENH-013`, added 2026-09-23).
- `SCR-SCH-038` — /school/coordinator/global-education — Global Education: the school's students on the global education pathway, a funnel and a per-student high-level stage list; sidebar label "Global Education", after "Reports" (`ENH-017`, added 2026-09-29).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Teacher (school-side) *(net-new, added 2026-09-14, `DEC-SCOPE-011` — role code `school_teacher`,
distinct from the existing Trainer/"Teacher" role above)*

- `SCR-SCH-013` — /school/invite/[token]/accept — True first entry point: accepting the Coordinator's invite (`DEC-SCOPE-012`).
- `SCR-SCH-007` — /school/teacher (Dashboard: assigned students) — Own class list only.
- `SCR-SCH-008` — /school/teacher/students/[id] — One assigned student's attendance/activities/progress.
- `SCR-SCH-035` — /school/teacher/students/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (assigned students only, from the student page's "Open 360° view") (`ENH-013`, added 2026-09-23).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Parent (school-side) *(net-new, added 2026-09-14, `DEC-SCOPE-011` — role code `school_parent`)*

- `SCR-SCH-013` — /school/invite/[token]/accept — True first entry point: accepting the Coordinator's invite (`DEC-SCOPE-012`).
- `SCR-SCH-009` — /school/parent (Dashboard: my children) — Own child(ren) only; per-child status chips, upcoming sessions, latest notifications (`SCH-007`, 2026-09-15).
- `SCR-SCH-022` — /school/parent/children/[id] (Child profile & progress) — One child's full overview (`SCH-007`); embeds `SCR-SCH-024`'s Journey Timeline (`SCH-008`).
- `SCR-SCH-023` — /school/parent/notifications — Own notification feed (`SCH-007`).
- `SCR-SCH-035` — /school/parent/children/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (own child(ren) only, from the child page's "Open 360° view") (`ENH-013`, added 2026-09-23).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Academic Team *(net-new, added 2026-09-14, `DEC-ROLE-006` — supersedes `DEC-ROLE-005`'s single-Counselor-role framing)*

- `SCR-SCH-014` — /school/academic-team (Dashboard: assigned students) — Result status per assigned student.
- `SCR-SCH-015` — /school/academic-team/results/new — Enter a result (starts as Draft).
- `SCR-SCH-016` — /school/academic-team/results/[id] — Verify / Publish a result; status history.
- `SCR-SCH-037` — /school/academic-team/students/[id] — The student's editable Digital Portfolio, incl. Skill India certifications (own school portfolio, from the dashboard's "Students" list) (`ENH-024`, added 2026-09-28, browser QA finding QA24-01).
- `SCR-SCH-035` — /school/academic-team/students/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (own school portfolio, from the student page's "Open 360° view"; "Back to student" returns there) (`ENH-013`, added 2026-09-23; entry point updated 2026-09-28 by `ENH-024` — it was the dashboard's "Student 360° view" list).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Career Counselor *(net-new, added 2026-09-14, `DEC-ROLE-006`)*

- `SCR-SCH-017` — /school/career-counselor (Dashboard: assigned students) — Assigned student list.
- `SCR-SCH-018` — /school/career-counselor/students/[id]/records — Career guidance/counselling records.
- `SCR-SCH-033` — /school/career-counselor/skills — Soft Skills / Digital Skills batches across the portfolio, and batch creation (`ENH-011`, added 2026-09-22).
- `SCR-SCH-034` — /school/career-counselor/skills/[id] — One batch: enrolments, attendance, assessments, certification (`ENH-011`, added 2026-09-22).
- `SCR-SCH-041` — /school/career-counselor/funding — Funding support cases (loan / financial assistance / scholarship / funding guidance) across the portfolio; sidebar "Funding" (`ENH-020`, added 2026-10-01).
- `SCR-SCH-035` — /school/career-counselor/students/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (own school portfolio, from the dashboard's "Student 360° view" list; sets the career goal) (`ENH-013`, added 2026-09-23).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Psychometric Team *(net-new, added 2026-09-14, `DEC-ROLE-006`)*

- `SCR-SCH-019` — /school/psychometric-team (Dashboard: assigned students) — Assigned student list.
- `SCR-SCH-020` — /school/psychometric-team/students/[id]/assessments — Assign assessments, upload reports.
- `SCR-SCH-035` — /school/psychometric-team/students/[id]/360 — Student 360° view / Career Passport, 16 tabs scoped to this role (own school portfolio, from the dashboard's "Student 360° view" list) (`ENH-013`, added 2026-09-23).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

*Note: `edusphere_school_manager` and `school_partnership_manager` (`DEC-ROLE-006`) have no nav
entries — their duties are OPEN (`PRD_OPEN_ITEMS.md` item 75) and no screen has been designed for
either yet.*

## BDM *(net-new, added 2026-10-02, `DEC-SCOPE-055`, `bdm-001`)*

Signs in at `/it/login` (College BDM, division `it`) or `/overseas/login` (Agent / School BDM, division `overseas`); lands on `/bdm/my-day`.

- /bdm/my-day — My Day (`bdm-014`): welcome + one-line profile summary; Today's appointments (time — organization), Upcoming travel (date — route, appointments scheduled), Follow-ups due today or overdue by organization type; then the type's eight "Today's overview" tiles ("Not tracked yet" where there is no source). Empty sections offer Book an appointment / Plan a trip / View follow-ups. A BDM manager opening it is sent to `/bdm/manager/dashboard`.
- /bdm/profile — read-only §1 profile.
- /bdm/organizations — Organization CRM (`bdm-002`): every organization of the BDM's module, filters (name/code, city, type, assigned to me, show archived); `/bdm/organizations/new` (add, ≥1 contact, duplicate warning); `/bdm/organizations/{id}` (details, contacts, edit/archive when assigned). Sidebar: My Day · Organizations · Appointments · Travel · Notifications · Profile.
- /bdm/appointments — Appointments (`bdm-006`): the BDM's own, filters date range (default today onward), status, type, organization; `/bdm/appointments/new` (book; `?organization=` preselects, opened by "Add appointment" on an assigned, non-archived organization); `/bdm/appointments/{id}` (details, outcome, history; edit, confirm, reschedule, cancel, no-show, complete).
- /bdm/follow-ups — Follow-ups and tasks (`bdm-008`): tabs Today / Overdue / Upcoming / Done / Cancelled with counts (IST dates), organization-type chips that filter, kind filter; add a follow-up or task, Done (then "Log activity" / "Book appointment"), Edit and Cancel (reason) on manual items. Nav item "Follow-ups" after Appointments. The organization profile shows its open items ("Follow-ups & tasks"; Add task when assigned).
- /bdm/calendar — Calendar (`bdm-013`): `?view=day|week&date=YYYY-MM-DD` (default: this week, Monday–Sunday, IST). One line per day in the §5 style ("Vijayawada – College Meetings", "Return travel", "Follow-ups") over that day's trips, appointments (seminars badged), follow-ups and tasks; each item links to its page; read-only. Nav item "Calendar" after My Day.
- /bdm/notifications — the BDM's in-app notices (bdm-010 T15; nav item "Notifications" with the unread count on every BDM page).
- /bdm/travel — My trips (bdm-010): list with an approval-status filter; /bdm/travel/new (draft); /bdm/travel/[id] (actions, details, edit while draft/rejected, costs and expenses, remarks). Nav item "Travel".

## BDM Manager *(net-new, added 2026-10-02, `DEC-SCOPE-055`, `bdm-001`)*

Division `global`; signs in at `/admin/login` (heading "Administration sign-in"); lands on `/bdm/manager/dashboard`. Password recovery stays in the admin portal (QA-05, B11): "Forgot your password?" on `/admin/login` → public `/admin/forgot-password`; the welcome/reset link opens public `/admin/reset-password`, whose links point to `/admin/login`; after a reset the form also follows the API's `login_portal`.

- /bdm/manager/dashboard — team counts, then the management dashboard (bdm-023, `DEC-SCOPE-108`): 8 overview tiles and the alert list, each alert linking to its record. super_admin reaches it from "BDM Dashboard" in the admin sidebar (all teams, or one manager's).
- /bdm/manager/team — the BDMs who report to this manager (paged).
- /bdm/manager/organizations — the team's organizations (`bdm-002`), read-only except reassign and restore; `/bdm/manager/organizations/{id}`. Sidebar: Dashboard · Team · Organizations · Appointments · Approvals · Notifications.
- /bdm/manager/appointments — the team's appointments (`bdm-006`), read-only with a BDM filter; `/bdm/manager/appointments/{id}` (details and history, no actions).
- /bdm/manager/follow-ups — the team's follow-ups and tasks (`bdm-008`), read-only with a BDM filter; nav item "Follow-ups" after Appointments.
- /bdm/manager/calendar — one team BDM's calendar (`bdm-013`), read-only: pick a BDM (`?bdm=`), then the same day / week views; a BDM outside the team reads "This BDM is not on your team." Nav item "Calendar" after Follow-ups.
- /bdm/manager/notifications — the manager's in-app notices, e.g. "Travel approval needed" (bdm-010 T15; nav item with the unread count).
- /bdm/manager/approvals — trips waiting for this manager's approval (bdm-010; nav item "Approvals"); /bdm/manager/trips/[id] — read-only trip with Approve / Reject (reason required).

**Signed-out `/bdm/*`:** `/bdm/manager/*` → `/admin/login?next=…`; any other `/bdm/*` → the public chooser `/bdm/sign-in?next=…` (College BDM / Agent-School BDM / Administration links; `next` kept only when same-origin).

**Admin entry points:** a "BDMs" nav item for Super Admin (`/admin/bdms`), IT Admin (`/it/admin/bdms`, College) and Overseas Admin (`/overseas/admin/bdms`, Agent + School). BDM Managers are created by a Super Admin from Users (division Global). bdm-010 adds "BDM Travel Approvals" for Super Admin (`/admin/bdm-travel-approvals`): trips whose reporting manager is inactive.

## Telecaller *(net-new, 2026-10-05, `DEC-SCOPE-073`, `tel-001`)*

Signs in at `/it/login` (IT team, division `it`) or `/overseas/login` (Overseas team, division `overseas`) by team; lands on `/telecaller/dashboard`. Sidebar: Dashboard · Profile.

- /telecaller/dashboard — greeting, a profile summary card (team, Employee ID, reporting manager) and *(tel-022)* a "My targets" card (today / this month per KPI); tel-021 fills in the rest. A missing profile shows the 403 message.
- /telecaller/profile — read-only profile (name, email, team, Employee ID, reporting manager, status) plus an editable phone (TL3).
- /telecaller — redirects to `/telecaller/dashboard`.

## Telecaller Manager *(net-new, 2026-10-05, `DEC-SCOPE-073`, `tel-001`)*

Division `global`; signs in at `/admin/login`; lands on `/telecaller/manager/team`. Sidebar: Team · Leads (tel-008) · Lead assignment · Distribution rules (tel-007) · Targets (tel-022) · Products · Campaigns (tel-002) · Scripts · Templates · Brochures (tel-012). Password recovery stays in the admin portal: "Forgot your password?" on `/admin/login` → `/admin/forgot-password`; the welcome/reset link opens `/admin/reset-password`, and after a reset the form follows the API's `login_portal` (`"admin"`).

- /telecaller/manager/team — the telecallers who report to this manager (paged, inactive included).
- /telecaller/manager/assignment — *(tel-007, `DEC-SCOPE-087`)* Lead assignment: Unassigned queue of my reports' teams and Assigned to my team, bulk assign/reassign to a direct report; `?view=assigned&telecaller=&q=&offset=` keep the place.
- /telecaller/manager/distribution — *(tel-007)* product and city rules for my reports (all rules readable), with the distribution order explained; `?team=` filters.
- /telecaller/manager/targets — *(tel-022, `DEC-SCOPE-080`)* daily + monthly targets: team defaults (IT/Overseas) and per-telecaller overrides from a future date, targets in effect on any date, history; `?for=it|overseas|<telecaller id>` keeps the choice on refresh.
- /telecaller/manager/products — *(tel-002, `DEC-SCOPE-074`)* the product/interest catalogue: create, edit, deactivate/reactivate; a Super Admin uses the same URL.
- /telecaller/manager/campaigns — *(tel-002)* the campaign list (source → product → campaign): create, edit, deactivate/reactivate.
- /telecaller/manager/scripts — *(tel-012, `DEC-SCOPE-083`)* call scripts: one active script per product, ordered steps.
- /telecaller/manager/templates — *(tel-012)* WhatsApp and email message templates with placeholders and a sample-value preview.
- /telecaller/manager/brochures — *(tel-012)* brochure / fee-sheet PDFs: upload, edit, deactivate/reactivate, copy a 7-day link.

**Signed-out `/telecaller/*` (TL1):** `/telecaller/manager/*` → `/admin/login?next=…`; any other `/telecaller/*` → the public chooser `/telecaller/sign-in?next=…` ("IT team" → `/it/login?next=…`, "Overseas team" → `/overseas/login?next=…`, plus the line "Telecaller Managers sign in at Administration" linking to `/admin/login`).

**Admin entry points:** a "Telecallers" nav item for Super Admin (`/admin/telecallers`, both teams), IT Admin (`/it/admin/telecallers`, IT) and Overseas Admin (`/overseas/admin/telecallers`, Overseas). Telecaller Managers are created by a Super Admin from Users (division Global); telecallers are created on the Telecallers page.

## Partnership Manager *(net-new, 2026-10-08, `DEC-SCOPE-118`, `upc-001`)*

Division `overseas`; signs in at `/overseas/login`; lands on `/partnership/dashboard`. Sidebar: Dashboard · Profile. The EVID-020 §32
menu (19 entries, `PARTNERSHIP_MENU` in `lib/navigation.ts`) joins the sidebar one entry at a time as each upc item lands (PU8).

- /partnership/dashboard — greeting, a profile summary card (Employee ID, reporting head) and "Coming soon to your CRM" (the §32 areas not yet built, as text). upc-022 fills in the dashboard. A missing profile shows the 403 message.
- /partnership/profile — read-only profile (name, Employee ID, mobile, email, reporting head, status) plus an editable mobile (PU3).
- /partnership — redirects to `/partnership/dashboard`.
- /partnership/universities — *(upc-003, `DEC-SCOPE-120`)* the University Master, now a live sidebar entry (Dashboard · University
  Master · Profile). Reads every university; edits those where the manager is primary or backup.

## Partnership Head *(net-new, 2026-10-08, `DEC-SCOPE-118`, `upc-001`)*

Division `global`; created only by a Super Admin from Users; signs in at `/admin/login`; lands on `/partnership/head/team`. Sidebar: Team. Password recovery stays in the admin portal (the welcome/reset link opens `/admin/reset-password`, and `login_portal` is `"admin"`).

- /partnership/head/team — the partnership managers who report to this head (paged, inactive included). A Super Admin sees all of them.
- /partnership/head — redirects to `/partnership/head/team`.
- /partnership/universities — *(upc-003)* University Master in the head's sidebar (Team · University Master): add, edit and publish
  unowned or team-owned universities and assign their managers. Overseas Admin and Super Admin reach it from their Universities section.

**Signed-out `/partnership/*` (PU1):** `/partnership/head*` → `/admin/login?next=…`; any other `/partnership/*` → `/overseas/login?next=…`.

**Admin entry points:** a "Partnership managers" nav item for Super Admin (`/admin/partnership-managers`) and Overseas Admin (`/overseas/admin/partnership-managers`). IT Admin has none (managers are Overseas).

## Division isolation (confirmed, `DEC-ARCH-001`)

A user's nav never crosses `it` / `overseas` / `global` divisions except for **Super Admin**, the sole cross-division role. An `overseas_student` never sees `/it/*` nav items and vice versa, even though — per `DEC-ROLE-001` — both may be the *same person's* account. This is a navigation-visibility rule; the underlying identity-model question (one account, two role-assignments) is Architecture-phase work, tracked in `docs/features/FEATURE_QUESTIONS.md` item 3.

**School roles' division is `overseas` by proposed inference, not an explicit decision** (`RBAC_MATRIX.md` §1) — the four `/school/*` nav trees above are modeled under `overseas` for now; if that assignment is confirmed wrong, these nav entries move divisions along with the underlying RBAC change (`PRD_OPEN_ITEMS.md` item 72).

## rec-005 addendum (2026-10-08, `DEC-SCOPE-126`)

- `placement_team` and `placement_manager`: a "Pipeline" entry (`/recruiter/pipeline`) after "Candidate Master".
- `super_admin`: "Recruiter Pipeline" (`/recruiter/pipeline`) after "Recruiter Companies".
