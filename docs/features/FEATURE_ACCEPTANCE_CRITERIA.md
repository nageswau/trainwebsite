# Feature Acceptance Criteria

Generated per feature, ID format `<FEATURE-ID>-AC##`. Derived directly from each feature's main/alternate/error workflow in `MASTER_FEATURE_CATALOG.md` — no criteria introduces scope beyond what that feature's PRD/BR/Decision trace supports.


## FND-001 — Reference-implementation extension baseline

- **FND-001-AC01:** Given Reference implementation accessible at the given path., when the primary actor performs the main workflow (Codebase imported/forked; local dev environment runs via docker-compose.), then it completes successfully and is visible to the correct actor(s) only.
- **FND-001-AC02:** Given the error/edge condition, when Missing dependency/tooling halts setup; documented in LOCAL_DEVELOPMENT.md (base repo)., then the system responds as specified — no silent failure, no partial state.
- **FND-001-AC03:** RBAC — an actor outside N/A cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## FND-002 — Division-aware RBAC & identity framework

- **FND-002-AC01:** Given FND-001 complete., when the primary actor performs the main workflow (Every protected API route validates JWT, division, and role before executing.), then it completes successfully and is visible to the correct actor(s) only.
- **FND-002-AC02:** Given the error/edge condition, when Unauthorized/wrong-division request returns 401/403, never partial data., then the system responds as specified — no silent failure, no partial state.
- **FND-002-AC03:** RBAC — an actor outside All roles cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AUTH-001 — Division-aware authenticated login

- **AUTH-001-AC01:** Given Account exists (self-registered or admin-created)., when the primary actor performs the main workflow (User submits credentials on the correct division's login page; session established.), then it completes successfully and is visible to the correct actor(s) only.
- **AUTH-001-AC02:** Given the alternate path applies, when Password reset flow., then the system handles it without violating the main workflow's data integrity.
- **AUTH-001-AC03:** Given the error/edge condition, when Invalid credentials rejected with generic error (no user enumeration)., then the system responds as specified — no silent failure, no partial state.
- **AUTH-001-AC04:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AUTH-002 — Role-based access control enforcement (UI)

- **AUTH-002-AC01:** Given AUTH-001, FND-002., when the primary actor performs the main workflow (Only role-permitted navigation/actions render.), then it completes successfully and is visible to the correct actor(s) only.
- **AUTH-002-AC02:** Given the error/edge condition, when Role-restricted UI accessed via direct URL/API is still blocked server-side (FND-002) even if briefly rendered client-side before redirect., then the system responds as specified — no silent failure, no partial state.
- **AUTH-002-AC03:** RBAC — an actor outside All roles cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AUTH-003 — Google OAuth login

- **AUTH-003-AC01:** Given AUTH-001., when the primary actor performs the main workflow (-), then it completes successfully and is visible to the correct actor(s) only.
- **AUTH-003-AC02:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **AUTH-003-AC03: NOT APPLICABLE YET** — feature is BLOCKED (PRD-AUTH-003 is PROPOSED (unconfirmed) — sourced only from the original tech-stack document, never independently re-confirmed via the Decision Register.); no AC should be executed against code until unblocked.

## PUB-001 — Corporate & IT marketing content

- **PUB-001-AC01:** Given None., when the primary actor performs the main workflow (Visitor browses list/detail pages.), then it completes successfully and is visible to the correct actor(s) only.
- **PUB-001-AC02:** Given the error/edge condition, when Unpublished/missing content shows empty state, not an error., then the system responds as specified — no silent failure, no partial state.
- **PUB-001-AC03:** RBAC — an actor outside Public cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## PUB-002 — Enquiry submission synced to CRM

- **PUB-002-AC01:** Given None (public form)., when the primary actor performs the main workflow (Submission creates an enquiry record; webhook fires to Zoho.), then it completes successfully and is visible to the correct actor(s) only.
- **PUB-002-AC02:** Given the error/edge condition, when Webhook failure must not lose the locally-captured enquiry (retry/queue)., then the system responds as specified — no silent failure, no partial state.
- **PUB-002-AC03:** RBAC — an actor outside Public submit / Admin view cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## PUB-003 — Course catalogue and detail

- **PUB-003-AC01:** Given None., when the primary actor performs the main workflow (Visitor searches/filters/opens a course.), then it completes successfully and is visible to the correct actor(s) only.
- **PUB-003-AC02:** Given the error/edge condition, when No results → empty state with guidance., then the system responds as specified — no silent failure, no partial state.
- **PUB-003-AC03:** RBAC — an actor outside Public cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## PUB-004 — Webinar listing and registration

- **PUB-004-AC01:** Given None., when the primary actor performs the main workflow (Visitor registers for a webinar.), then it completes successfully and is visible to the correct actor(s) only.
- **PUB-004-AC02:** Given the error/edge condition, when Capacity/waitlist rule unspecified — open item., then the system responds as specified — no silent failure, no partial state.
- **PUB-004-AC03:** RBAC — an actor outside Public cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## PUB-005 — News and gallery (CMS-managed)

- **PUB-005-AC01:** Given CMS content published., when the primary actor performs the main workflow (Visitor browses; Admin publishes via CMS.), then it completes successfully and is visible to the correct actor(s) only.
- **PUB-005-AC02:** Given the error/edge condition, when Empty state when nothing published., then the system responds as specified — no silent failure, no partial state.
- **PUB-005-AC03:** RBAC — an actor outside Public view / Admin publish cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## PUB-010 — Site search, FAQ, and legal pages

- **PUB-010-AC01:** Given no precondition., when the primary actor performs the main workflow (Visitor searches across public site content and reads FAQ.), then it completes successfully and is visible to the correct actor(s) only.
- **PUB-010-AC02:** Given the error/edge condition, when Privacy Policy/Terms & Conditions/Cookie Preferences pages ship as explicitly-labeled non-final placeholder content — real legal sign-off is DEC-PRIV-001, still open — and must never be presented as final legal text., then the system responds as specified — no silent failure, no partial state.
- **PUB-010-AC03:** RBAC — an actor outside Public cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-001 — Trainer/batch slot enrolment

- **STU-001-AC01:** Given Student has selected a course/track; payment initiated or completed per business rule., when the primary actor performs the main workflow (Student browses capacity-aware slot list and books one.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-001-AC02:** Given the error/edge condition, when Booking a full slot is rejected; changing a locked slot is rejected., then the system responds as specified — no silent failure, no partial state.
- **STU-001-AC03:** RBAC — an actor outside Self (Student) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-002 — Student dashboard

- **STU-002-AC01:** Given STU-001., when the primary actor performs the main workflow (Dashboard aggregates data from enrolment, attendance, payments, assignments.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-002-AC02:** Given the error/edge condition, when A failed data source for one dashboard widget (e.g. payments) does not block the rest of the dashboard from rendering., then the system responds as specified — no silent failure, no partial state.
- **STU-002-AC03:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-003 — Live class access

- **STU-003-AC01:** Given Session scheduled by Trainer (TRN-003)., when the primary actor performs the main workflow (Student joins from dashboard at session time.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-003-AC02:** Given the error/edge condition, when No recording available for a session hit by the concurrency limit — accepted limitation, not a fault., then the system responds as specified — no silent failure, no partial state.
- **STU-003-AC03:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-004 — Assignment submission

- **STU-004-AC01:** Given TRN-006 assignment created., when the primary actor performs the main workflow (Student submits; Trainer grades (TRN-007).), then it completes successfully and is visible to the correct actor(s) only.
- **STU-004-AC02:** Given the alternate path applies, when Late submission per trainer rule., then the system handles it without violating the main workflow's data integrity.
- **STU-004-AC03:** Given the error/edge condition, when Submission after due date flagged, not silently accepted unless allowed., then the system responds as specified — no silent failure, no partial state.
- **STU-004-AC04:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-005 — Support ticket

- **STU-005-AC01:** Given Student is authenticated., when the primary actor performs the main workflow (Student raises ticket; staff responds/resolves.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-005-AC02:** Given the error/edge condition, when A ticket with no assigned staff member remains visibly unassigned, not silently lost., then the system responds as specified — no silent failure, no partial state.
- **STU-005-AC03:** RBAC — an actor outside Self / assigned staff cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-006 — Attendance and progress view

- **STU-006-AC01:** Given TRN-008 attendance marked., when the primary actor performs the main workflow (Student views read-only attendance/progress.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-006-AC02:** Given the error/edge condition, when No attendance recorded yet for a session shows as not-yet-marked, never defaulted to absent., then the system responds as specified — no silent failure, no partial state.
- **STU-006-AC03:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-007 — Certificate download

- **STU-007-AC01:** Given Course completion criteria met., when the primary actor performs the main workflow (Student downloads certificate (auto-generated or admin-uploaded — mechanism open).), then it completes successfully and is visible to the correct actor(s) only.
- **STU-007-AC02:** Given the error/edge condition, when Certificate unavailable before eligibility met., then the system responds as specified — no silent failure, no partial state.
- **STU-007-AC03:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-008 — Feedback submission

- **STU-008-AC01:** Given Student is enrolled in the course/trainer being reviewed., when the primary actor performs the main workflow (Student submits feedback form.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-008-AC02:** Given the alternate path applies, when Anonymous option (open item)., then the system handles it without violating the main workflow's data integrity.
- **STU-008-AC03:** Given the error/edge condition, when A student cannot submit feedback for a course/trainer they are not enrolled with., then the system responds as specified — no silent failure, no partial state.
- **STU-008-AC04:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-009 — Digital agreement / consent

- **STU-009-AC01:** Given STU-001 enrolment initiated., when the primary actor performs the main workflow (Student reviews and accepts agreement; acceptance timestamped.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-009-AC02:** Given the error/edge condition, when Enrolment cannot complete without acceptance., then the system responds as specified — no silent failure, no partial state.
- **STU-009-AC03:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-010 — Fee payment, EMI, invoices, receipts

- **STU-010-AC01:** Given STU-001 enrolment., when the primary actor performs the main workflow (Student pays via Razorpay; invoice/receipt generated; EMI schedule tracked.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-010-AC02:** Given the alternate path applies, when Manual/offline payment record (base codebase)., then the system handles it without violating the main workflow's data integrity.
- **STU-010-AC03:** Given the error/edge condition, when Failed payment does not mark fee as paid; webhook signature must verify., then the system responds as specified — no silent failure, no partial state.
- **STU-010-AC04:** RBAC — an actor outside Self (Student) / Admin (view) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## STU-011 — Profile and document management

- **STU-011-AC01:** Given Student is authenticated., when the primary actor performs the main workflow (Student edits profile fields.), then it completes successfully and is visible to the correct actor(s) only.
- **STU-011-AC02:** Given the error/edge condition, when An invalid file type/size on document upload is rejected with a clear message, not silently dropped., then the system responds as specified — no silent failure, no partial state.
- **STU-011-AC03:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-001 — My Batches

- **TRN-001-AC01:** Given Trainer has at least one assigned batch (ADM-003)., when the primary actor performs the main workflow (Trainer views own batch list.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-001-AC02:** Given the error/edge condition, when No batches → empty state., then the system responds as specified — no silent failure, no partial state.
- **TRN-001-AC03:** RBAC — an actor outside Self (Trainer) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-002 — Batch detail (roster and schedule)

- **TRN-002-AC01:** Given TRN-001., when the primary actor performs the main workflow (Trainer opens batch, sees roster+schedule.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-002-AC02:** Given the error/edge condition, when Roster scoped strictly to that batch., then the system responds as specified — no silent failure, no partial state.
- **TRN-002-AC03:** RBAC — an actor outside Self (Trainer, own batch only) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-003 — Upcoming sessions and live-class join

- **TRN-003-AC01:** Given TRN-001; batch has a scheduled session., when the primary actor performs the main workflow (Trainer views/joins upcoming session.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-003-AC02:** Given the error/edge condition, when Not-yet-joinable session shown as such, not an error., then the system responds as specified — no silent failure, no partial state.
- **TRN-003-AC03:** RBAC — an actor outside Self (Trainer) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-004 — Recording list and resource upload

- **TRN-004-AC01:** Given TRN-002., when the primary actor performs the main workflow (Trainer uploads resource / recording appears post-session.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-004-AC02:** Given the error/edge condition, when Missing recording (concurrency limit) shown as unavailable, not an error., then the system responds as specified — no silent failure, no partial state.
- **TRN-004-AC03:** RBAC — an actor outside Self (Trainer) / enrolled Students (view) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-005 — Assignment create and edit

- **TRN-005-AC01:** Given TRN-002., when the primary actor performs the main workflow (Trainer authors assignment; visible to batch students by due date.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-005-AC02:** Given the error/edge condition, when Editing an assignment after student submissions exist does not retroactively invalidate work already submitted., then the system responds as specified — no silent failure, no partial state.
- **TRN-005-AC03:** RBAC — an actor outside Self (Trainer, own batch) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-006 — Assessment create and edit

- **TRN-006-AC01:** Given TRN-002., when the primary actor performs the main workflow (Trainer authors assessment in Draft; moves to Scheduled to publish.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-006-AC02:** Given the error/edge condition, when Draft assessment never visible to Students., then the system responds as specified — no silent failure, no partial state.
- **TRN-006-AC03:** RBAC — an actor outside Self (Trainer, own batch) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-007 — Submission review and grading

- **TRN-007-AC01:** Given STU-004 submission exists., when the primary actor performs the main workflow (Trainer grades; Student sees result.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-007-AC02:** Given the error/edge condition, when Re-grading a submission overwrites the prior grade with an audit trail, not a duplicate record., then the system responds as specified — no silent failure, no partial state.
- **TRN-007-AC03:** RBAC — an actor outside Self (Trainer, own batch) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-008 — Attendance marking

- **TRN-008-AC01:** Given TRN-002; session occurred., when the primary actor performs the main workflow (Trainer marks attendance per student per session.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-008-AC02:** Given the error/edge condition, when Marking attendance for a session with no scheduled students returns an empty roster, not an error., then the system responds as specified — no silent failure, no partial state.
- **TRN-008-AC03:** RBAC — an actor outside Self (Trainer, own batch) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## TRN-009 — Q&A response

- **TRN-009-AC01:** Given TRN-002., when the primary actor performs the main workflow (Trainer answers a question; Student sees the reply.), then it completes successfully and is visible to the correct actor(s) only.
- **TRN-009-AC02:** Given the error/edge condition, when Only the Trainer assigned to that batch can reply; multiple replies on one question show in order., then the system responds as specified — no silent failure, no partial state.
- **TRN-009-AC03:** RBAC — an actor outside Self (Trainer, own batch) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-001 — User/course/batch administration

- **ADM-001-AC01:** Given FND-002., when the primary actor performs the main workflow (Admin performs CRUD on core entities.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-001-AC02:** Given the error/edge condition, when Deleting/deactivating an entity with active dependents (e.g. a course with active batches) is blocked or requires explicit cascade confirmation, never a silent cascade delete., then the system responds as specified — no silent failure, no partial state.
- **ADM-001-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-002 — CRM-linked enquiry/lead management

- **ADM-002-AC01:** Given PUB-002 enquiry submitted., when the primary actor performs the main workflow (Admin views/routes enquiry.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-002-AC02:** Given the error/edge condition, when An enquiry that fails to sync to Zoho remains visible and actionable in Admin regardless of sync status., then the system responds as specified — no silent failure, no partial state.
- **ADM-002-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-003 — Batch creation and trainer assignment

- **ADM-003-AC01:** Given ADM-001., when the primary actor performs the main workflow (Admin creates batch and assigns trainer; batch becomes student-selectable.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-003-AC02:** Given the error/edge condition, when Capacity exceeding 20 rejected., then the system responds as specified — no silent failure, no partial state.
- **ADM-003-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-004 — Directory management: Students, Trainers, Employers

- **ADM-004-AC01:** Given ADM-001., when the primary actor performs the main workflow (Admin views/edits directory detail records.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-004-AC02:** Given the error/edge condition, when Editing a Student/Trainer/Employer record never overwrites a field the acting Admin lacks permission to change., then the system responds as specified — no silent failure, no partial state.
- **ADM-004-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-005 — Enrolment review and approval

- **ADM-005-AC01:** Given ADM-002., when the primary actor performs the main workflow (Admin approves; student enrolment becomes active.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-005-AC02:** Given the error/edge condition, when Rejected enrolment does not silently proceed., then the system responds as specified — no silent failure, no partial state.
- **ADM-005-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-006 — Certificate administration

- **ADM-006-AC01:** Given Student course-completion criteria met., when the primary actor performs the main workflow (Admin uploads/issues certificate.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-006-AC02:** Given the error/edge condition, when Issuing a certificate for a student who hasn't met completion criteria requires an explicit override, not silent allowance., then the system responds as specified — no silent failure, no partial state.
- **ADM-006-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-007 — Placement Team workspace

- **ADM-007-AC01:** Given FND-002., when the primary actor performs the main workflow (Placement Team manages the domestic placement pipeline.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-007-AC02:** Given the error/edge condition, when A candidate withdrawn from the pool no longer appears in active matching, but historical placement records are retained., then the system responds as specified — no silent failure, no partial state.
- **ADM-007-AC03:** RBAC — an actor outside Placement Team cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-008 — HR Team workspace

- **ADM-008-AC01:** Given FND-002., when the primary actor performs the main workflow (HR Team manages hiring requirements and shortlists.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-008-AC02:** Given the error/edge condition, when A hiring requirement with no matching candidates shows an empty state, not an error., then the system responds as specified — no silent failure, no partial state.
- **ADM-008-AC03:** RBAC — an actor outside HR Team cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-009 — Resources/recordings oversight

- **ADM-009-AC01:** Given TRN-004., when the primary actor performs the main workflow (IT Admin views Trainer-uploaded resources/recordings across all batches, not just their own.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-009-AC02:** Given the error/edge condition, when A batch with no uploaded resources shows an honest empty state, not an error., then the system responds as specified — no silent failure, no partial state.
- **ADM-009-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-010 — Agreement/consent oversight

- **ADM-010-AC01:** Given STU-009., when the primary actor performs the main workflow (IT Admin views student agreement/consent status across all students.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-010-AC02:** Given the error/edge condition, when A student with no recorded consent shows an honest "not yet consented" state, not an error., then the system responds as specified — no silent failure, no partial state.
- **ADM-010-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-011 — Notification template management

- **ADM-011-AC01:** Given NOT-001., when the primary actor performs the main workflow (IT Admin manages email notification templates and monitors delivery status.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-011-AC02:** Given the error/edge condition, when WhatsApp/SMS template management is out of scope until NOT-002/NOT-003 (Twilio credentials) unblock — DEC-NOT-001's 2026-09-03 extension., then the system responds as specified — no silent failure, no partial state.
- **ADM-011-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-012 — Roles/permission administration

- **ADM-012-AC01:** Given FND-002., when the primary actor performs the main workflow (IT Admin views and adjusts the role/permission matrix.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-012-AC02:** Given the error/edge condition, when An attempt to remove a permission a role structurally requires (e.g. a role's own login) is rejected, not silently accepted., then the system responds as specified — no silent failure, no partial state.
- **ADM-012-AC03:** RBAC — an actor outside IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-013 — Operational-tooling cluster

- **ADM-013-AC01:** Given FND-002., when the primary actor performs the main workflow (Super Admin views system settings, audit logs, data import/export, backup/restore status, system health, and background-job monitoring.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-013-AC02:** Given the error/edge condition, when A failed or in-progress background job/backup shows its real status, never a fabricated "success"., then the system responds as specified — no silent failure, no partial state.
- **ADM-013-AC03:** RBAC — an actor outside Super Admin (DEC-SCOPE-008 resolves the prior IT Admin/Super Admin ownership ambiguity) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## ADM-014 — Super Admin cross-division console

- **ADM-014-AC01:** Given FND-002., when the primary actor performs the main workflow (Super Admin operates cross-division console.), then it completes successfully and is visible to the correct actor(s) only.
- **ADM-014-AC02:** Given the error/edge condition, when A cross-division privileged action (e.g. security-log export) is itself audit-logged, per the base codebase's privileged-write audit requirement., then the system responds as specified — no silent failure, no partial state.
- **ADM-014-AC03:** RBAC — an actor outside Super Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## EMP-001 — Employer registration

- **EMP-001-AC01:** Given FND-002 (new role/route to add)., when the primary actor performs the main workflow (Company self-registers.), then it completes successfully and is visible to the correct actor(s) only.
- **EMP-001-AC02:** Given the error/edge condition, when Approval-before-activation workflow open — see FEATURE_QUESTIONS.md., then the system responds as specified — no silent failure, no partial state.
- **EMP-001-AC03:** RBAC — an actor outside Employer (new) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## EMP-002 — Job posting

- **EMP-002-AC01:** Given EMP-001., when the primary actor performs the main workflow (Employer posts a job; visible to eligible Students.), then it completes successfully and is visible to the correct actor(s) only.
- **EMP-002-AC02:** Given the error/edge condition, when A job posting past its closing date is not shown to Students as open, even if the Employer never explicitly closed it., then the system responds as specified — no silent failure, no partial state.
- **EMP-002-AC03:** RBAC — an actor outside Employer (own postings) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## EMP-003 — Candidate profile search

- **EMP-003-AC01:** Given EMP-001; STU-011 profile exists., when the primary actor performs the main workflow (Employer searches; sees permission-limited profile fields.), then it completes successfully and is visible to the correct actor(s) only.
- **EMP-003-AC02:** Given the error/edge condition, when Fields outside approved visibility never returned to Employer., then the system responds as specified — no silent failure, no partial state.
- **EMP-003-AC03:** RBAC — an actor outside Employer cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## EMP-004 — Interview scheduling and shortlist

- **EMP-004-AC01:** Given EMP-003., when the primary actor performs the main workflow (Employer shortlists, then schedules an interview.), then it completes successfully and is visible to the correct actor(s) only.
- **EMP-004-AC02:** Given the error/edge condition, when Scheduling conflicts (same candidate, overlapping time) are flagged, not silently double-booked., then the system responds as specified — no silent failure, no partial state.
- **EMP-004-AC03:** RBAC — an actor outside Employer (own candidates) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## EMP-005 — Interview list and status

- **EMP-005-AC01:** Given EMP-004., when the primary actor performs the main workflow (Employer reviews interview list.), then it completes successfully and is visible to the correct actor(s) only.
- **EMP-005-AC02:** Given the error/edge condition, when Cancelled interviews remain visible in history, not deleted., then the system responds as specified — no silent failure, no partial state.
- **EMP-005-AC03:** RBAC — an actor outside Employer cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## EMP-006 — Placement status tracking

- **EMP-006-AC01:** Given EMP-004., when the primary actor performs the main workflow (Employer/IT Admin tracks placement status — offer/accepted/joined — per interviewed candidate.), then it completes successfully and is visible to the correct actor(s) only.
- **EMP-006-AC02:** Given the error/edge condition, when An interviewed candidate with no placement outcome yet shows an honest "no outcome recorded" state, not a fabricated status., then the system responds as specified — no silent failure, no partial state.
- **EMP-006-AC03:** RBAC — an actor outside Employer, IT Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-001 — Destination/university/course discovery

- **OVS-001-AC01:** Given None., when the primary actor performs the main workflow (User browses country/university/course listings and detail.), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-001-AC02:** Given the error/edge condition, when A university/course with incomplete admin-entered data (per DEC-DATA-002) shows only the fields that exist -- never a fabricated placeholder value., then the system responds as specified — no silent failure, no partial state.
- **OVS-001-AC03:** RBAC — an actor outside Public cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-002 — Overseas application submission

- **OVS-002-AC01:** Given OVS-001; Student authenticated., when the primary actor performs the main workflow (Student submits interest; application enters the state sequence (OVS-003/004).), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-002-AC02:** Given the error/edge condition, when Submitting interest in the same university/course twice does not create a duplicate application record., then the system responds as specified — no silent failure, no partial state.
- **OVS-002-AC03:** RBAC — an actor outside Self (Student) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-003 — Eligibility evaluation

- **OVS-003-AC01:** Given OVS-002., when the primary actor performs the main workflow (Counselor reviews and advances/declines the application stage.), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-003-AC02:** Given the error/edge condition, when Rejection/waitlist/deferral outcomes are an open item — do not invent., then the system responds as specified — no silent failure, no partial state.
- **OVS-003-AC03:** RBAC — an actor outside Counselor (assigned students) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-004 — Application status tracking and notifications

- **OVS-004-AC01:** Given OVS-002., when the primary actor performs the main workflow (Stage change triggers a notification and updates the Student's tracking view.), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-004-AC02:** Given the error/edge condition, when A stage-change notification that fails to send does not block the status update itself from being recorded., then the system responds as specified — no silent failure, no partial state.
- **OVS-004-AC03:** RBAC — an actor outside Self (Student) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-005 — Document upload against checklist

- **OVS-005-AC01:** Given OVS-002., when the primary actor performs the main workflow (Student uploads; Counselor verifies (verification_status).), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-005-AC02:** Given the error/edge condition, when Unsupported file types/sizes — open item., then the system responds as specified — no silent failure, no partial state.
- **OVS-005-AC03:** RBAC — an actor outside Self (Student) / Counselor (verify) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-006 — Scholarship listing and application

- **OVS-006-AC01:** Given OVS-001 context., when the primary actor performs the main workflow (Student applies to a listed scholarship.), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-006-AC02:** Given the error/edge condition, when No eligibility rule engine — listing only., then the system responds as specified — no silent failure, no partial state.
- **OVS-006-AC03:** RBAC — an actor outside Public view / Self (Student) apply cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OVS-007 — Events and workshops

- **OVS-007-AC01:** Given None., when the primary actor performs the main workflow (User registers for an event.), then it completes successfully and is visible to the correct actor(s) only.
- **OVS-007-AC02:** Given the error/edge condition, when Capacity/waitlist unspecified — open item., then the system responds as specified — no silent failure, no partial state.
- **OVS-007-AC03:** RBAC — an actor outside Public cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## VISA-001 — Visa checklist and documentation

- **VISA-001-AC01:** Given OVS-005 documents verified., when the primary actor performs the main workflow (Student completes checklist; status tracked.), then it completes successfully and is visible to the correct actor(s) only.
- **VISA-001-AC02:** Given the error/edge condition, when An unverified document does not block viewing the checklist -- only advancing past the stage that requires it., then the system responds as specified — no silent failure, no partial state.
- **VISA-001-AC03:** RBAC — an actor outside Self (Student) / Counselor cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## VISA-002 — Visa interview preparation

- **VISA-002-AC01:** Given VISA-001., when the primary actor performs the main workflow (Student views prep material.), then it completes successfully and is visible to the correct actor(s) only.
- **VISA-002-AC02:** Given the error/edge condition, when Missing prep material for a specific country shows a clear fallback, not a broken page., then the system responds as specified — no silent failure, no partial state.
- **VISA-002-AC03:** RBAC — an actor outside Self (Student) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## VISA-003 — Visa approval status tracking

- **VISA-003-AC01:** Given VISA-001., when the primary actor performs the main workflow (Status updates as the case progresses (checklist → ... → decision).), then it completes successfully and is visible to the correct actor(s) only.
- **VISA-003-AC02:** Given the error/edge condition, when Compliance rule: never represent EduSphere as the visa decision-maker (found in reference implementation copy)., then the system responds as specified — no silent failure, no partial state.
- **VISA-003-AC03:** RBAC — an actor outside Self (Student) / Counselor cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AGT-001 — Agent self-registration and approval gate

- **AGT-001-AC01:** Given FND-002., when the primary actor performs the main workflow (Agent registers; Overseas Admin approves/rejects (ADM-015).), then it completes successfully and is visible to the correct actor(s) only.
- **AGT-001-AC02:** Given the error/edge condition, when Pending/Rejected Agent cannot refer students or view data., then the system responds as specified — no silent failure, no partial state.
- **AGT-001-AC03:** RBAC — an actor outside Agent (self) / Overseas Admin (approve) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AGT-002 — Referred-student roster and status

- **AGT-002-AC01:** Given AGT-001 approved; OVS-002 applications linked via agent_id., when the primary actor performs the main workflow (Agent views own referrals only.), then it completes successfully and is visible to the correct actor(s) only.
- **AGT-002-AC02:** Given the error/edge condition, when Agent never sees another agent's referrals., then the system responds as specified — no silent failure, no partial state.
- **AGT-002-AC03:** RBAC — an actor outside Self (Agent, own referrals) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AGT-003 — Commission accrual (automatic trigger)

- **AGT-003-AC01:** Given AGT-002; application reaches the (to-be-mapped) joined status., when the primary actor performs the main workflow (System auto-creates eligible commission on trigger.), then it completes successfully and is visible to the correct actor(s) only.
- **AGT-003-AC02:** Given the alternate path applies, when Overseas Admin sets/adjusts amount., then the system handles it without violating the main workflow's data integrity.
- **AGT-003-AC03:** Given the error/edge condition, when No commission creatable before the trigger condition — extends the base codebase's manual-only creation., then the system responds as specified — no silent failure, no partial state.
- **AGT-003-AC04:** RBAC — an actor outside Agent (view own) / Overseas Admin (amount) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## AGT-004 — Commission payout request and approval

- **AGT-004-AC01:** Given AGT-003 commission eligible/estimated., when the primary actor performs the main workflow (Agent claims; Overseas Admin approves payout (new endpoint).), then it completes successfully and is visible to the correct actor(s) only.
- **AGT-004-AC02:** Given the error/edge condition, when No commission reaches paid without explicit Overseas Admin approval, distinct from the Agent's own claim., then the system responds as specified — no silent failure, no partial state.
- **AGT-004-AC03:** RBAC — an actor outside Agent (claim) / Overseas Admin (approve) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## CNS-001 — Counselor workspace

- **CNS-001-AC01:** Given FND-002., when the primary actor performs the main workflow (Counselor manages their assigned Overseas caseload end-to-end.), then it completes successfully and is visible to the correct actor(s) only.
- **CNS-001-AC02:** Given the error/edge condition, when A Counselor cannot act on a student who is not assigned to them, even via a direct record ID., then the system responds as specified — no silent failure, no partial state.
- **CNS-001-AC03:** RBAC — an actor outside Counselor (own assigned students) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## UNI-001 — University Representative portal

- **UNI-001-AC01:** Given FND-002; a University partner record exists., when the primary actor performs the main workflow (Rep reviews/updates applications sent to their university.), then it completes successfully and is visible to the correct actor(s) only.
- **UNI-001-AC02:** Given the error/edge condition, when Rep sees only applications addressed to their own institution., then the system responds as specified — no silent failure, no partial state.
- **UNI-001-AC03:** RBAC — an actor outside University Representative (own institution only) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## SCH-001 — School Portal role-based access (Principal/Coordinator/Teacher/Parent)

- **SCH-001-AC01:** Given FND-002; SCH-003 (a School partner record and the acting account both exist, provisioning mechanism resolved and built — `DEC-SCOPE-012`)., when the primary actor (Principal, School Coordinator, Teacher, or Parent) performs the main workflow (logs in and sees/acts on only their own institution's data, further scoped per role), then it completes successfully and is visible to the correct actor(s) only.
- **SCH-001-AC02:** Given the error/edge condition, when no role ever sees another institution's data, even via a direct record ID., then the system responds as specified — no silent failure, no partial state.
- **SCH-001-AC03:** RBAC — an actor outside their own role's scope (Principal/Coordinator: own institution only; Teacher: own institution + assigned students only; Parent: own institution + own child(ren) only) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **SCH-001-AC04:** Scope boundary — Principal, Teacher, and Parent are strictly read-only; only School Coordinator has create/edit access, and only to students within their own institution, one at a time. Bulk upload is a separate Feature ID (`SCH-002`).
- **SCH-001-AC05:** Role-name collision check — the `school_teacher` role must never be granted any permission belonging to `trainer` (`DEC-ROLE-002`'s Teacher/Trainer), and the `school_coordinator` role must never be granted any permission belonging to `coordinator` (`DEC-ROLE-003`'s certificate-issuance Coordinator) — verified at the API layer, since the names alone are easy to conflate.
- **SCH-001-AC06:** Scope boundary — no Career Guidance/Psychometric/Counselling/Academic Results content-creation action is reachable through this feature for any of the four roles; that data belongs to `SCH-004`/`005`/`006`'s own specialized roles (`career_counselor`/`psychometric_team`/`academic_team`, `DEC-ROLE-006` — supersedes this AC's original `DEC-ROLE-005`/Counselor framing), out of scope for this Feature ID.

## SCH-002 — School Coordinator bulk student roster upload (template-download-first)

- **SCH-002-AC01:** Given SCH-001 (School Coordinator account exists and is scoped to their institution)., when the primary actor performs the main workflow (downloads template, uploads filled file, system validates and applies row-level, returns a per-row accept/reject report), then it completes successfully and is visible to the correct actor(s) only.
- **SCH-002-AC02:** Given the error/edge condition, when a Coordinator can only bulk-create/update students within their own institution, never another's, even via a crafted upload row., then the system responds as specified — no silent failure, no partial state.
- **SCH-002-AC03:** RBAC — an actor outside School Coordinator (own institution only) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **SCH-002-AC04:** Partial-batch integrity — a row that fails validation does not block the rest of the batch from being processed; each row succeeds or fails independently and is reported individually, never a silent partial success masked as a full success.
- **SCH-002-AC05:** Scope boundary — this feature covers student-roster upload only; no academic-results field or action is reachable through it (`DEC-SCOPE-010` part 2, `PENDING`).

## SCH-003 — School partner onboarding (Admin-created, Coordinator-seeded invites)

- **SCH-003-AC01:** Given FND-002; Overseas Admin's own division-management access., when the primary actor performs the main workflow (Overseas Admin creates School + seed Coordinator, active immediately -> Coordinator invites/creates Principal/Teacher/Parent for the same institution, active immediately), then it completes successfully and is visible to the correct actor(s) only.
- **SCH-003-AC02:** Given the error/edge condition, when an account the Coordinator creates is always scoped to the Coordinator's own `school_id`, server-derived, never client-supplied., then the system responds as specified — no silent failure, no partial state.
- **SCH-003-AC03:** RBAC — an actor outside Overseas Admin (create School + seed Coordinator) or School Coordinator (invite/create Principal/Teacher/Parent, own institution only) cannot perform this feature's action, verified at the API layer (not just hidden in UI).
- **SCH-003-AC04:** No activation gate — a School, or any of its four accounts, is usable immediately on creation; no Pending state or separate approval action exists in this flow, unlike Agent's registration (`AGT-001-AC02`).
- **SCH-003-AC05:** Tier independence — provisioning behaves identically regardless of School Partnership tier; no code path branches on tier for this feature.
- **SCH-003-AC06:** Invite-token integrity — a Coordinator-issued invite for Principal/Teacher/Parent is single-use and scoped to one institution; a consumed or cross-institution invite token is rejected, not silently accepted.

## SCH-004 — Career Guidance & Counselling module

- **SCH-004-AC01:** Given FND-002; ADM-001 (Overseas Admin or Super Admin creates the Career Counselor account and assigns their school portfolio via the Admin console, `DEC-SCOPE-014`)., when the primary actor performs the main workflow (Career Counselor creates/manages career guidance sessions and counselling records for school-affiliated students at any school in their own portfolio; Coordinator and Parent/Student/Teacher view read-only), then it completes successfully and is visible to the correct actor(s) only.
- **SCH-004-AC02:** Given the error/edge condition, when Career Counselor never manages a student at a school outside their own portfolio (`DEC-SCOPE-013`), even via a direct record ID; School Coordinator never edits this content, only views it, for their own institution only., then the system responds as specified — no silent failure, no partial state.
- **SCH-004-AC03:** RBAC — an actor outside Career Counselor (own school portfolio, write) or School Coordinator/Parent/Student/Teacher (read-only, own scope) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **SCH-004-AC04:** Scope boundary — no create/edit action on this content is reachable by School Coordinator, Parent, Student, or Teacher; only Career Counselor writes it.

## SCH-005 — Psychometric Assessment module

- **SCH-005-AC01:** Given FND-002; ADM-001 (Overseas Admin or Super Admin creates the Psychometric Team account and assigns their school portfolio via the Admin console, `DEC-SCOPE-014`)., when the primary actor performs the main workflow (Psychometric Team assigns assessments and uploads reports for school-affiliated students at any school in their own portfolio; Coordinator and Parent/Student/Teacher view read-only), then it completes successfully and is visible to the correct actor(s) only.
- **SCH-005-AC02:** Given the error/edge condition, when Psychometric Team never manages a student at a school outside their own portfolio (`DEC-SCOPE-013`), even via a direct record ID; School Coordinator never edits this content, only views it, for their own institution only., then the system responds as specified — no silent failure, no partial state.
- **SCH-005-AC03:** RBAC — an actor outside Psychometric Team (own school portfolio, write) or School Coordinator/Parent/Student/Teacher (read-only, own scope) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **SCH-005-AC04:** Scope boundary — no create/edit action on this content is reachable by School Coordinator, Parent, Student, or Teacher; only Psychometric Team writes it.

## SCH-006 — Academic Results module (Draft → Verified → Published)

- **SCH-006-AC01:** Given FND-002; ADM-001 (Overseas Admin or Super Admin creates the Academic Team account and assigns their school portfolio via the Admin console, `DEC-SCOPE-014`; a portfolio needs at least two Academic Team members for publishing to be possible at all, `DEC-ROLE-007`)., when the primary actor performs the main workflow (Academic Team uploads a result (Draft) -> a different Academic Team member verifies it (Verified) -> a different Academic Team member publishes it (Published) -> Parent/Student/Teacher can then view it), then it completes successfully and is visible to the correct actor(s) only.
- **SCH-006-AC02:** Given the error/edge condition, when a Draft or Verified (not yet Published) result is never visible to Parent/Student/Teacher, even via a direct record ID., then the system responds as specified — no silent failure, no partial state.
- **SCH-006-AC03:** RBAC — an actor outside Academic Team (own school portfolio, write) or School Coordinator/Parent/Student/Teacher (read-only, own scope, Published only) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **SCH-006-AC04:** Gate integrity — a result cannot skip a stage (e.g. Draft directly to Published); each transition is explicit and individually auditable. **Same-actor restriction (`DEC-ROLE-007`, resolved 2026-09-14):** the `academic_team` member recorded as `uploaded_by_user_id` may never also be recorded as `verified_by_user_id` or `published_by_user_id` — a verify/publish attempt by the uploader themselves is rejected (**403**, corrected 2026-09-14 as-built — same status code as every other role/scope deny in this API, not 409, which this API reserves for a state-conflict such as a duplicate email or an already-consumed invite), not silently accepted. This gate design and its verify/publish actor are both confirmed (`DEC-ROLE-006`, `DEC-ROLE-007`), no longer an open re-confirmation item.
- **SCH-006-AC05:** Academic Team never edits a result at a school outside their own portfolio (`DEC-SCOPE-013`), even via a direct record ID.

## NOT-001 — Email notifications

- **NOT-001-AC01:** Given Triggering event occurs., when the primary actor performs the main workflow (System sends email on defined trigger.), then it completes successfully and is visible to the correct actor(s) only.
- **NOT-001-AC02:** Given the error/edge condition, when A failed send is retried per a defined policy (policy itself open -- PRD_OPEN_ITEMS item 13), never silently dropped., then the system responds as specified — no silent failure, no partial state.
- **NOT-001-AC03:** RBAC — an actor outside System cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## NOT-002 — WhatsApp notifications (Twilio)

- **NOT-002-AC01:** Given Triggering event occurs., when the primary actor performs the main workflow (System sends WhatsApp message via Twilio on defined trigger.), then it completes successfully and is visible to the correct actor(s) only.
- **NOT-002-AC02:** Given the error/edge condition, when Opt-out respected once defined., then the system responds as specified — no silent failure, no partial state.
- **NOT-002-AC03:** RBAC — an actor outside System cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## NOT-003 — SMS notifications

- **NOT-003-AC01:** Given Triggering event occurs., when the primary actor performs the main workflow (System sends SMS on defined trigger.), then it completes successfully and is visible to the correct actor(s) only.
- **NOT-003-AC02:** Given the error/edge condition, when Same failure-handling expectation as Email/WhatsApp -- never silently dropped., then the system responds as specified — no silent failure, no partial state.
- **NOT-003-AC03:** RBAC — an actor outside System cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## PAY-001 — Payment gateway integration

- **PAY-001-AC01:** Given FND-001., when the primary actor performs the main workflow (Checkout session created; webhook confirms payment.), then it completes successfully and is visible to the correct actor(s) only.
- **PAY-001-AC02:** Given the alternate path applies, when Manual/offline payment record (base)., then the system handles it without violating the main workflow's data integrity.
- **PAY-001-AC03:** Given the error/edge condition, when Unverified/failed webhook never marks a fee paid., then the system responds as specified — no silent failure, no partial state.
- **PAY-001-AC04:** RBAC — an actor outside System cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## LMS-001 — Native LMS module extensions

- **LMS-001-AC01:** Given the actor is authenticated with the correct role, when the primary actor performs the main workflow (-), then it completes successfully and is visible to the correct actor(s) only.
- **LMS-001-AC02:** RBAC — an actor outside Self cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).
- **LMS-001-AC03: NOT APPLICABLE YET** — feature is BLOCKED (PRD-LMS-001's actual feature boundary (content authoring? sequencing? quizzes? gradebooks? SCORM?) is explicitly undefined — cannot decompose into buildable AC without inventing scope.); no AC should be executed against code until unblocked.

## RPT-001 — Domestic/Employer reporting

- **RPT-001-AC01:** Given Underlying data exists (enrolment/attendance/placement features live)., when the primary actor performs the main workflow (Admin/Placement Team views reports.), then it completes successfully and is visible to the correct actor(s) only.
- **RPT-001-AC02:** Given the error/edge condition, when A report with no underlying data for the selected period shows an empty state, never a zero-filled fabrication., then the system responds as specified — no silent failure, no partial state.
- **RPT-001-AC03:** RBAC — an actor outside IT Admin, Placement Team cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## RPT-002 — Overseas reporting

- **RPT-002-AC01:** Given OVS-004; AGT-003., when the primary actor performs the main workflow (Overseas Admin/Counselor views application funnel by stage, agent commission report, and visa-status aging.), then it completes successfully and is visible to the correct actor(s) only.
- **RPT-002-AC02:** Given the error/edge condition, when A stage/status with zero applications shows a real zero, not an omitted row., then the system responds as specified — no silent failure, no partial state.
- **RPT-002-AC03:** RBAC — an actor outside Overseas Admin cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## SEC-001 — Approval-gate audit trail

- **SEC-001-AC01:** Given AGT-001, AGT-004., when the primary actor performs the main workflow (Every approval action writes an audit record (base codebase already has AuditLog + audit helper).), then it completes successfully and is visible to the correct actor(s) only.
- **SEC-001-AC02:** Given the error/edge condition, when An audit-log write failure must not silently allow the underlying privileged action to proceed unlogged -- fail closed, not open., then the system responds as specified — no silent failure, no partial state.
- **SEC-001-AC03:** RBAC — an actor outside System (write) / Overseas Admin (implicit) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## SEC-002 — GDPR consent capture and self-service export/delete

- **SEC-002-AC01:** Given User is authenticated and requesting their own data, or an Admin is acting on a verified request., when the primary actor performs the main workflow (User requests export/delete; system fulfills within a defined SLA (SLA itself open).), then it completes successfully and is visible to the correct actor(s) only.
- **SEC-002-AC02:** Given the error/edge condition, when Deletion respects legal/financial retention holds where applicable — retention periods still open., then the system responds as specified — no silent failure, no partial state.
- **SEC-002-AC03:** RBAC — an actor outside Self (request) / IT Admin (fulfill) cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OPS-001 — DigitalOcean deployment

- **OPS-001-AC01:** Given FND-001., when the primary actor performs the main workflow (App deployed and reachable on DigitalOcean infrastructure.), then it completes successfully and is visible to the correct actor(s) only.
- **OPS-001-AC02:** Given the error/edge condition, when A failed deployment does not silently leave production traffic pointed at a partially-updated instance., then the system responds as specified — no silent failure, no partial state.
- **OPS-001-AC03:** RBAC — an actor outside Engineering cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).

## OPS-002 — Database migration execution and seed-data decision

- **OPS-002-AC01:** Given OPS-001., when the primary actor performs the main workflow (Migrations run cleanly; seed-data decision made and executed.), then it completes successfully and is visible to the correct actor(s) only.
- **OPS-002-AC02:** Given the error/edge condition, when A failed migration does not leave the schema in a partially-applied state -- must be transactional/rollback-safe., then the system responds as specified — no silent failure, no partial state.
- **OPS-002-AC03:** RBAC — an actor outside Engineering cannot perform or view this feature's action/data, verified at the API layer (not just hidden in UI).