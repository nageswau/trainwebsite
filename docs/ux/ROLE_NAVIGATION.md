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

## Agent

- `SCR-AGT-001` — /overseas/agent/register — Agent self-registration.
- `SCR-AGT-003` — /overseas/agent (Dashboard: referred students) — Referred-student roster and status.
- `SCR-AGT-004` — /overseas/agent/commissions — Commission list (auto-accrued).
- `SCR-AGT-005` — /overseas/agent/commissions/[id]/claim — Commission claim action.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Overseas Admin

- `SCR-AGT-002` — /overseas/admin/agents — Agent approval queue (Overseas Admin side).
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
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Teacher (school-side) *(net-new, added 2026-09-14, `DEC-SCOPE-011` — role code `school_teacher`,
distinct from the existing Trainer/"Teacher" role above)*

- `SCR-SCH-013` — /school/invite/[token]/accept — True first entry point: accepting the Coordinator's invite (`DEC-SCOPE-012`).
- `SCR-SCH-007` — /school/teacher (Dashboard: assigned students) — Own class list only.
- `SCR-SCH-008` — /school/teacher/students/[id] — One assigned student's attendance/activities/progress.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Parent (school-side) *(net-new, added 2026-09-14, `DEC-SCOPE-011` — role code `school_parent`)*

- `SCR-SCH-013` — /school/invite/[token]/accept — True first entry point: accepting the Coordinator's invite (`DEC-SCOPE-012`).
- `SCR-SCH-009` — /school/parent (Dashboard: my children) — Own child(ren) only; per-child status chips, upcoming sessions, latest notifications (`SCH-007`, 2026-09-15).
- `SCR-SCH-022` — /school/parent/children/[id] (Child profile & progress) — One child's full overview (`SCH-007`); embeds `SCR-SCH-024`'s Journey Timeline (`SCH-008`).
- `SCR-SCH-023` — /school/parent/notifications — Own notification feed (`SCH-007`).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Academic Team *(net-new, added 2026-09-14, `DEC-ROLE-006` — supersedes `DEC-ROLE-005`'s single-Counselor-role framing)*

- `SCR-SCH-014` — /school/academic-team (Dashboard: assigned students) — Result status per assigned student.
- `SCR-SCH-015` — /school/academic-team/results/new — Enter a result (starts as Draft).
- `SCR-SCH-016` — /school/academic-team/results/[id] — Verify / Publish a result; status history.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Career Counselor *(net-new, added 2026-09-14, `DEC-ROLE-006`)*

- `SCR-SCH-017` — /school/career-counselor (Dashboard: assigned students) — Assigned student list.
- `SCR-SCH-018` — /school/career-counselor/students/[id]/records — Career guidance/counselling records.
- `SCR-SCH-033` — /school/career-counselor/skills — Soft Skills / Digital Skills batches across the portfolio, and batch creation (`ENH-011`, added 2026-09-22).
- `SCR-SCH-034` — /school/career-counselor/skills/[id] — One batch: enrolments, attendance, assessments, certification (`ENH-011`, added 2026-09-22).
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

## Psychometric Team *(net-new, added 2026-09-14, `DEC-ROLE-006`)*

- `SCR-SCH-019` — /school/psychometric-team (Dashboard: assigned students) — Assigned student list.
- `SCR-SCH-020` — /school/psychometric-team/students/[id]/assessments — Assign assessments, upload reports.
- `SCR-SEC-001` — /account/privacy (Data export/delete request) — GDPR self-service export/delete request.

*Note: `edusphere_school_manager` and `school_partnership_manager` (`DEC-ROLE-006`) have no nav
entries — their duties are OPEN (`PRD_OPEN_ITEMS.md` item 75) and no screen has been designed for
either yet.*

## Division isolation (confirmed, `DEC-ARCH-001`)

A user's nav never crosses `it` / `overseas` / `global` divisions except for **Super Admin**, the sole cross-division role. An `overseas_student` never sees `/it/*` nav items and vice versa, even though — per `DEC-ROLE-001` — both may be the *same person's* account. This is a navigation-visibility rule; the underlying identity-model question (one account, two role-assignments) is Architecture-phase work, tracked in `docs/features/FEATURE_QUESTIONS.md` item 3.

**School roles' division is `overseas` by proposed inference, not an explicit decision** (`RBAC_MATRIX.md` §1) — the four `/school/*` nav trees above are modeled under `overseas` for now; if that assignment is confirmed wrong, these nav entries move divisions along with the underlying RBAC change (`PRD_OPEN_ITEMS.md` item 72).
