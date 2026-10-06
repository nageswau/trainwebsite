# EduSphere School CRM — Documentation Analysis (Phase 1)

| | |
|---|---|
| Status | Phase 1 complete. Discovery is from source code only; **nothing has been checked in a browser yet.** |
| Prepared | 2026-10-05 (master planning session S1) |
| Code baseline | committed `main` **`ce1f07c2`** (branch `docs/school-crm-user-guide`). The working tree only had graphify output changes, which are not product code. |
| Scope | **School CRM** (owner decision 2026-10-05): every `/school/*` portal (School Coordinator, Principal, Teacher, Parent, Academic Team, Career Counselor, Psychometric Team), invite acceptance and account access for those roles, plus the Overseas Admin / Super Admin screens that manage schools (Schools, School Staff, School Applications, School Transfers, Activity Feedback, School Analytics). |
| Out of scope | BDM CRM (where a school is only a prospect organisation), Agent CRM (documented separately in `docs/documentation-*.md`), IT division, other Overseas roles. Exception: the Overseas Counselor's **School Applications** screen, which is the same School CRM feature as the admin one. |
| Location | Everything for this set lives under `docs/school-crm/` (owner decision). The top-level `docs/documentation-*.md`, `docs/user-manual/` etc. belong to the Agent CRM set and must not be touched. |
| Method | Graphify graph (`graphify-out/graph.json`, 21,423 nodes) for orientation → four parallel source-discovery passes at HEAD with file:line evidence → this report. |
| Evidence appendices | `discovery/01-account-principal-teacher-parent.md`, `discovery/02-coordinator.md`, `discovery/03-specialists-360-portfolio.md`, `discovery/04-admin-school-management.md`. They hold the field-by-field detail: every label, message, endpoint and file:line. This report summarises them and does not repeat them. |
| Authority | This file describes **as-built behaviour** for user documentation. It is not a requirement, decision or approval record (see `CLAUDE.md`). Where code and derived docs (ROLE_NAVIGATION, SCREEN_CATALOG, specs, backlog) differ, code wins and the difference is recorded in §12. |

Legend: **CO** = School Coordinator, **PR** = Principal, **TE** = Teacher (school-side), **PA** = Parent (school-side),
**AT** = Academic Team, **CC** = Career Counselor, **PT** = Psychometric Team, **OA** = Overseas Admin, **SA** = Super Admin,
**OC** = Overseas Counselor. **School roles** = CO/PR/TE/PA. **Service roles** = AT/CC/PT.
**VERIFICATION REQUIRED** = cannot be confirmed from code; it must be seen in the browser before it is documented.

---

## 1. Application Overview

### 1.1 What the School CRM is
The School CRM is the part of EduSphere that serves **partner schools**.
- An Overseas Admin creates a partner school with a **partnership tier** (Bronze, Silver, Gold or Platinum). This also creates the school's **School Coordinator** account.
- The Coordinator runs the school's side of the system:
  - keeps the student roster (students have no login of their own)
  - invites the Principal, Teachers and Parents
  - schedules EduSphere activities and records attendance and feedback
  - promotes students at the start of a new academic year
  - asks for student transfers between schools
- EduSphere's own specialists work on the students of the schools in their **portfolio**:
  - The **Academic Team** enters results, which go through Draft → Verified → Published, and runs test preparation and language classes.
  - The **Career Counselor** keeps counselling records, career preferences, skills batches and funding cases.
  - The **Psychometric Team** assigns assessments and records their results.
- Principals, Teachers and Parents mostly read. The exceptions:
  - Teachers take daily class attendance.
  - Teachers can edit the Digital Portfolio of the students assigned to them.
- Every role sees a shared **Student 360° view**, filtered to that role, and a **Digital Portfolio**.
- What a school may use is limited by its tier. The limit is enforced on the server and shown on an **Entitlements** page.

### 1.2 Technology (verified)
| Layer | Evidence |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, `apps/web` (`apps/web/package.json`) |
| Backend | FastAPI, SQLAlchemy 2 (async), Alembic, `apps/api` (`apps/api/requirements.txt`). Every router is mounted under `/api/v1` (`apps/api/app/main.py:79-80`) |
| Database | PostgreSQL (docker compose) |
| Browser tooling present | Playwright `^1.62.1` (`apps/web/package.json`). The documentation capture config `apps/web/playwright.docs.config.ts` and helpers `apps/web/tests/doc-capture/shoot.ts` already exist from the Agent CRM set. |

### 1.3 Authentication (verified, details in appendix 01 §1.10)
- **Login page.** All seven school-side roles are created with `division="overseas"`, so **every school user signs in at `/overseas/login`**. There is no separate school login page, and the page's text only talks about overseas users (§12.2).
- **Session tokens.** The JWT uses HS256. It is held in two HttpOnly, SameSite=Lax cookies: `edusphere_access` (60 min) and `edusphere_refresh` (14 days) (`apps/api/app/api/auth.py:89-94`). Every API call goes through `get_current_user` (`apps/api/app/api/deps.py:41-58`).
- **Session length.** The web app never calls `/auth/refresh`. A session therefore probably ends about 60 minutes after sign-in. **VERIFICATION REQUIRED.**
- **Route protection.** `/school/*` and `/account/*` are **not** covered by `apps/web/middleware.ts`. A signed-out visitor is not redirected. Each page calls the API itself and shows an **"Access unavailable"** card with a **"Return to login"** link.
- **How accounts are created:**
  - **Coordinators** and the **service roles** (AT, CC, PT) are created by an Overseas Admin. They get a 72-hour welcome / set-password link that opens `/overseas/reset-password?token=…`.
  - **Principal, Teacher and Parent** accounts are invited by the Coordinator. The invite link is valid for 7 days and opens `/school/invite/{token}/accept`.
  - A Parent can also be linked automatically when the Coordinator enters the parent's email on a student record.
- **Authorization.** Role checks are written inline in each route (`user.role`). `apps/api/app/core/rbac.py:40-49` declares school permission strings, but the school routes do not use them. The school is always taken from the server-side `profile.school_id` (school roles), from staff assignments (service roles) or from parent links (parents). It is never taken from the request.

### 1.4 Partnership tiers (cross-cutting)
Tiers are cumulative: Bronze < Silver < Gold < Platinum (`apps/api/app/api/schools.py:978-1020`).

**Services by tier:**

| Tier | Adds these services |
|---|---|
| Bronze | Career seminar, Student career awareness session, Parent orientation, Psychometric test, Soft skills |
| Silver | Individual counselling, Digital skills |
| Gold | Application support, Scholarship assistance, IELTS coaching, SAT coaching, Foreign language classes, Digital portfolio creation |
| Platinum | Dedicated EduSphere counselor, Monthly campus visits, Internships, Visa support, Loan assistance, Alumni network, Parent help desk |

**Enforcement** happens on the server only, in `require_school_entitlement` (`schools.py:1122-1149`). A refused action returns HTTP 403 with one of three messages:
- "This school has no active partnership tier."
- "This school's partnership expired on DD Mon YYYY."
- "This school's {Tier} partnership does not include {Service} (requires {MinTier} or higher)."

**The UI never hides an option the tier excludes.** The user can try the action and then sees the 403 text. There are two exceptions:
- The Portfolio Internships section shows "Internship tracking is part of the Platinum partnership…".
- Scorecards show "Not in plan".

**Downgrades and expiry:**
- Work started before a downgrade can still be finished ("grandfathered").
- After the partnership expires, nothing can be finished.

Feature-by-tier gating is listed in appendix 03 §0.4.

---

## 2. Module Inventory

| Code | Module | Users | Where documented | Screenshot folder |
|---|---|---|---|---|
| AUTH | Account access & navigation | all 7 school roles (+ OA/SA sign-in pointer) | `user-manual/account-access/` | `screenshots/account-access/` |
| DASH | Dashboards | each role | `user-manual/dashboards/` | `screenshots/dashboards/` |
| STU | Students & roster (incl. promotion) | CO (+ PR/TE read, PA PDF) | `user-manual/students/` | `screenshots/students/` |
| XFER | Student transfers (school side) | CO | `user-manual/transfers/` | `screenshots/transfers/` |
| ACT | Activities, attendance & feedback | CO, PR, TE | `user-manual/activities/` | `screenshots/activities/` |
| TEAM | Team & invitations | CO | `user-manual/team/` | `screenshots/team/` |
| RPT | Reports, analytics & global education | CO, PR | `user-manual/reports/` | `screenshots/reports/` |
| ENT | Partnership entitlements | CO, PR (reference for all) | `user-manual/entitlements/` | `screenshots/entitlements/` |
| NOTIF | Notifications | CO, PR, PA | `user-manual/notifications/` | `screenshots/notifications/` |
| PAR | Parent: child profile & progress | PA | `user-manual/parent/` | `screenshots/parent/` |
| ACAD | Academic Team work | AT | `user-manual/academic-team/` | `screenshots/academic-team/` |
| CAR | Career Counselor work (records, skills, funding) | CC | `user-manual/career-counselor/` | `screenshots/career-counselor/` |
| PSY | Psychometric Team work | PT | `user-manual/psychometric-team/` | `screenshots/psychometric-team/` |
| S360 | Student 360° view | all 7 roles | `user-manual/student-360/` | `screenshots/student-360/` |
| PORT | Digital Portfolio | CO, TE (assigned), AT write; others read | `user-manual/portfolio/` | `screenshots/portfolio/` |
| SADM | School administration | OA, SA, (OC for applications) | `admin-manual/` | `screenshots/admin-schools/` |

**16 modules.**

---

## 3. Feature Inventory

Each feature gets one Doc ID and one documentation file. "Appx" points to the evidence appendix section. All 86 features below are **code-reviewed at `ce1f07c2`; none are browser-verified**.

### AUTH — Account access & navigation (9)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-AUTH-001 | Sign in to the School portals (and where each role lands) | all 7 | 01 §1.2–1.3 |
| DOC-SCH-AUTH-002 | Accept a school invitation and set up your login | PR, TE, PA (invitee) | 01 §1.5 |
| DOC-SCH-AUTH-003 | Set your first password from a welcome link | CO, AT, CC, PT | 01 §1.1, §1.6; 04 §2, §5 |
| DOC-SCH-AUTH-004 | Forgot / reset your password | all 7 | 01 §1.6 |
| DOC-SCH-AUTH-005 | Change your password | all 7 | 01 §1.7 |
| DOC-SCH-AUTH-006 | My profile and notification settings | all 7 | 01 §1.8 |
| DOC-SCH-AUTH-007 | Sign out and session expiry | all 7 | 01 §1.9–1.10 |
| DOC-SCH-AUTH-008 | "Access unavailable" messages (signed out, wrong portal, deactivated, other school's student) | all 7 | 01 §1.11–1.12 |
| DOC-SCH-AUTH-009 | Find your way around: sidebar, role label, mobile menu | all 7 | 01 §1.4; 02 §0.2; 03 §0.2 |

### DASH — Dashboards (7)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-DASH-001 | Coordinator dashboard (20 KPI tiles, Your school, Upcoming activities, Results & guidance) | CO | 02 §1 |
| DOC-SCH-DASH-002 | Principal dashboard (School at a glance, Your school roster, Results & guidance) | PR | 01 §2.1 |
| DOC-SCH-DASH-003 | Teacher dashboard (Your students, Results & guidance) | TE | 01 §3.1 |
| DOC-SCH-DASH-004 | Parent dashboard: My children, Upcoming sessions, Important notifications (incl. children at several schools) | PA | 01 §4.1, §1.13 |
| DOC-SCH-DASH-005 | Academic Team dashboard: layout and sections | AT | 03 §1.1 |
| DOC-SCH-DASH-006 | Career Counselor dashboard: layout and sections | CC | 03 §2.1 |
| DOC-SCH-DASH-007 | Psychometric Team dashboard: layout and sections | PT | 03 §3.1 |

### STU — Students & roster (9)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-STU-001 | View the student roster | CO | 02 §2 |
| DOC-SCH-STU-002 | Add one student | CO | 02 §2 |
| DOC-SCH-STU-003 | Edit a student (incl. teacher assignment) | CO | 02 §2 |
| DOC-SCH-STU-004 | Link a parent to a student | CO | 02 §2 |
| DOC-SCH-STU-005 | Upload the roster in bulk (CSV) | CO | 02 §3 |
| DOC-SCH-STU-006 | Student profile and journey timeline (grade/transfer history, scorecard, funding cases) | CO, PR, TE | 02 §4; 01 §2.7, §3.3 |
| DOC-SCH-STU-007 | Add, replace or remove a student photo | CO | 02 §4 |
| DOC-SCH-STU-008 | Download a student progress report (PDF) | CO, PR, PA | 02 §4; 01 §2.7, §4.2 |
| DOC-SCH-STU-009 | Promote or hold back students for the new academic year | CO | 02 §7 |

### XFER — Student transfers (3)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-XFER-001 | Request a transfer out to another school | CO | 02 §6 |
| DOC-SCH-XFER-002 | Request a student from another school (by Student ID) | CO | 02 §6 |
| DOC-SCH-XFER-003 | Track and cancel transfer requests | CO | 02 §6 |

### ACT — Activities, attendance & feedback (5)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-ACT-001 | Schedule an activity | CO | 02 §8 |
| DOC-SCH-ACT-002 | Mark attendance for an activity | CO | 02 §8 |
| DOC-SCH-ACT-003 | Give feedback on a completed EduSphere activity | CO | 02 §9 |
| DOC-SCH-ACT-004 | View activity feedback | PR | 01 §2.4 |
| DOC-SCH-ACT-005 | Take daily class attendance | TE | 01 §3.2 |

### TEAM — Team & invitations (3)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-TEAM-001 | Invite a Principal, Teacher or Parent | CO | 02 §10 |
| DOC-SCH-TEAM-002 | View your team and pending invites | CO | 02 §10 |
| DOC-SCH-TEAM-003 | Deactivate or reactivate a team account | CO | 02 §10 |

### RPT — Reports, analytics & global education (6)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-RPT-001 | Download the school report (PDF) | CO, PR | 02 §11; 01 §2.2 |
| DOC-SCH-RPT-002 | School summary: metric tiles, students by grade, service delivery, activities & attendance | CO, PR | 02 §11; 01 §2.2 |
| DOC-SCH-RPT-003 | Grade-wise comparison | CO, PR | 02 §11; 01 §2.2 |
| DOC-SCH-RPT-004 | Student development, at-risk students and top performers | CO, PR | 02 §11; 01 §2.2 |
| DOC-SCH-RPT-005 | Student progress scorecards | CO, PR | 02 §11; 01 §2.2 |
| DOC-SCH-RPT-006 | Global education pipeline | CO, PR | 02 §12; 01 §2.3 |

### ENT — Partnership entitlements (2)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-ENT-001 | View your school's partnership entitlements | CO, PR | 02 §13; 01 §2.5 |
| DOC-SCH-ENT-002 | Partnership tiers explained (what each tier includes; "not included" messages) | reference for all roles | §1.4; 03 §0.4 |

### NOTIF — Notifications (2)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-NOTIF-001 | Notifications for school staff | CO, PR | 02 §14; 01 §2.6 |
| DOC-SCH-NOTIF-002 | Notifications for parents (what triggers them) | PA | 01 §4.4 |

### PAR — Parent (1)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-PAR-001 | Your child's profile and progress page | PA | 01 §4.2 |

### ACAD — Academic Team (7)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-ACAD-001 | Portfolio progress | AT | 03 §1.1.a |
| DOC-SCH-ACAD-002 | Upload a result as Draft | AT | 03 §1.1.c |
| DOC-SCH-ACAD-003 | Verify and publish results (two-person rule) | AT | 03 §1.1.b |
| DOC-SCH-ACAD-004 | Bulk entry: results (CSV) | AT | 03 §1.1.d |
| DOC-SCH-ACAD-005 | Test preparation (IELTS / SAT): start and record the score | AT | 03 §1.1.e |
| DOC-SCH-ACAD-006 | Foreign language classes: start and mark certified | AT | 03 §1.1.f |
| DOC-SCH-ACAD-007 | Bulk entry: test preparation and language classes (CSV) | AT | 03 §1.1.d |

### CAR — Career Counselor (11)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-CAR-001 | Add a career guidance / counselling record | CC | 03 §2.1.b |
| DOC-SCH-CAR-002 | Edit a record and move its status | CC | 03 §2.1.a–b |
| DOC-SCH-CAR-003 | Record a student's career preferences | CC | 03 §2.1.c |
| DOC-SCH-CAR-004 | Set a student's career goal (360° view) | CC | 03 §4.2 |
| DOC-SCH-CAR-005 | Find and create skills batches | CC | 03 §2.2 |
| DOC-SCH-CAR-006 | Edit, close or reopen a skills batch | CC | 03 §2.3 |
| DOC-SCH-CAR-007 | Enrol students and change enrolment status (complete, certify, withdraw) | CC | 03 §2.3 |
| DOC-SCH-CAR-008 | Add sessions and take batch attendance | CC | 03 §2.3 |
| DOC-SCH-CAR-009 | Add assessments and record scores | CC | 03 §2.3 |
| DOC-SCH-CAR-010 | Open a funding support case | CC | 03 §2.4 |
| DOC-SCH-CAR-011 | Move a funding case through its stages or close it | CC | 03 §2.4 |

### PSY — Psychometric Team (4)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-PSY-001 | Assign a psychometric assessment | PT | 03 §3.1.a |
| DOC-SCH-PSY-002 | Attach an assessment report | PT | 03 §3.1.a |
| DOC-SCH-PSY-003 | Record or edit assessment results | PT | 03 §3.1.a |
| DOC-SCH-PSY-004 | Bulk entry: assessments (CSV) | PT | 03 §1.1.d |

### S360 — Student 360° view (1)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-S360-001 | Student 360° view: the 16 tabs and what each role sees | all 7 | 03 §4.1–4.2 |

### PORT — Digital Portfolio (5)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-PORT-001 | Digital Portfolio overview and completion % | all 7 (read) | 03 §4.3 |
| DOC-SCH-PORT-002 | Add, edit or delete portfolio entries | CO, TE (assigned), AT | 03 §4.3 |
| DOC-SCH-PORT-003 | Record a Skill India certification | CO, TE (assigned), AT | 03 §4.3 |
| DOC-SCH-PORT-004 | Internship tracking and certificate upload (Platinum) | CO, TE (assigned), AT | 03 §4.3 |
| DOC-SCH-PORT-005 | Write the personal statement | CO, TE (assigned), AT | 03 §4.3 |

### SADM — School administration (admin manual) (11)
| Doc ID | Feature | Roles | Appx |
|---|---|---|---|
| DOC-SCH-SADM-001 | Partner Schools list | OA | 04 §1 |
| DOC-SCH-SADM-002 | Create a school and seed its Coordinator | OA | 04 §2 |
| DOC-SCH-SADM-003 | Edit a school profile and change its partnership tier | OA | 04 §3 |
| DOC-SCH-SADM-004 | Onboard several schools by CSV | OA | 04 §4 |
| DOC-SCH-SADM-005 | Create school staff accounts (Academic Team / Career Counselor / Psychometric Team) and their school portfolio | OA | 04 §5 |
| DOC-SCH-SADM-006 | Start an overseas application for a school student | OA, OC | 04 §6 |
| DOC-SCH-SADM-007 | Review school transfer requests (approve / reject) | OA, SA | 04 §7 |
| DOC-SCH-SADM-008 | School Analytics | OA, SA | 04 §8 |
| DOC-SCH-SADM-009 | Activity Feedback across schools | OA, SA | 04 §9 |
| DOC-SCH-SADM-010 | Re-send a set-password link to a school user (Users page) | OA | 04 §5 "Resending" (**code review PARTIAL**: the Users page is outside the discovery passes) |
| DOC-SCH-SADM-011 | Super Admin and the school screens (what Super Admin can and cannot open) | SA | 04 §0.6 |

**Total: 86 features.**

---

## 4. User Role Inventory

| Role (code) | UI label (role pill) | Count in scope | Created by | Scope of data | Landing page | Sidebar |
|---|---|---|---|---|---|---|
| School Coordinator (`school_coordinator`) | "School Coordinator" | primary admin of a school | OA (with the school) | own school, everything | `/school/coordinator/dashboard` | Dashboard · Students · Promotion · Transfers · Activities · Feedback · Team · Reports · Global Education · Entitlements · Notifications |
| Principal (`school_principal`) | "Principal" | read-only school leader | CO invite | own school, read | `/school/principal/dashboard` | Dashboard · Reports · Global Education · Feedback · Entitlements · Notifications |
| Teacher (`school_teacher`) | "Teacher" | class teacher | CO invite | students assigned to them | `/school/teacher/dashboard` | Dashboard · Attendance |
| Parent (`school_parent`) | "Parent" | guardian | CO invite, or a parent email on a student | linked children, at any school | `/school/parent/dashboard` | Dashboard · Notifications |
| Academic Team (`academic_team`) | "Academic Team" | EduSphere specialist | OA (School Staff) | students of the schools in their portfolio | `/school/academic-team/dashboard` | Dashboard |
| Career Counselor (`career_counselor`) | "Career Counselor" | EduSphere specialist | OA (School Staff) | portfolio schools | `/school/career-counselor/dashboard` | Dashboard · Skills · Funding |
| Psychometric Team (`psychometric_team`) | "Psychometric Team" | EduSphere specialist | OA (School Staff) | portfolio schools | `/school/psychometric-team/dashboard` | Dashboard |
| Overseas Admin (`overseas_admin`) | "Overseas Administrator" | platform admin | (seed / Users) | all schools | `/overseas/admin/dashboard` | … Schools · School Staff · School Applications · School Transfers · Activity Feedback · School Analytics … |
| Super Admin (`super_admin`) | "Super Administrator" | platform owner | (seed) | all, but see §5 notes | `/admin` | only **School Analytics** among the school items |
| Overseas Counselor (`counselor`) | "Counselor" | overseas counselor | (Overseas) | own applications | `/overseas/counselor/dashboard` | … School Applications … (only this school feature is in scope) |

**10 roles.** 7 are school-side roles; 3 manage the School CRM from the Overseas division (OA, SA, OC).

Invitees and visitors have no role until they accept an invite. They see only the invite-accept page and the login and reset pages.

**Demo accounts** in the seed, `apps/api/app/seed.py:613-690`:
- **School "Sunrise Public School"**, Platinum.
- **School roles:**
  - CO: `school.coordinator@edusphere.local`
  - PR: `school.principal@…`
  - TE: `school.teacher@…`
  - PA: `school.parent@…`
- **Service roles:**
  - AT: `school.academic1@…` and `school.academic2@…`
  - CC: `school.careercounselor@…`
  - PT: `school.psychometric@…`
- **Admins:** OA `overseasadmin@edusphere.local`, SA `superadmin@edusphere.local`.
- **Password:** the seed `PASSWORD` constant. It is never written into these docs.

---

## 5. Role Permission Matrix

The frontend guard and the API guard are listed separately because they differ (§12.2, item 1). **API** = what the server allows. **Page** = what the page itself checks. "—" = no access. **R** = read, **W** = write, **Own** = own school, **Asg** = assigned students only, **Ch** = own linked children only, **Pf** = portfolio schools only.

### 5.1 School portals
| Feature area | CO | PR | TE | PA | AT | CC | PT |
|---|---|---|---|---|---|---|---|
| Dashboard KPIs (`/school/dashboard`) | R Own | R Own | — | — | — | — | — |
| Roster list (`GET /school/students`) | R Own | R Own | R Asg | R Ch | — | — | — |
| Add / edit student, link parent, bulk upload | W Own | — | — | — | — | — | — |
| Student photo upload / remove | W Own | — (view) | — (view) | — (view) | — | — | — |
| Student profile, timeline, grade/transfer history | R Own | R Own | R Asg | R Ch | — | — | — |
| Progress report PDF | R Own | R Own | — | R Ch | — | — | — |
| Scorecard (per student) | R Own | R Own | — | — | — | — | — |
| Funding cases (read) | R Own | R Own | — ("not visible to teachers") | R Ch | R Pf | R/W Pf | — |
| Promotion | W Own | — | — | — | — | — | — |
| Transfers (request, track, cancel) | W Own | — | — | — | — | — | — |
| Activities: schedule, mark attendance | W Own | — | — | — | — | — | — |
| Activity feedback | W Own (submit once) | R Own | — | — | — | — | — |
| Daily class attendance | — | — | W Asg | — | — | — | — |
| Team: invite, activate / deactivate | W Own | — | — | — | — | — | — |
| Reports, analytics, scorecards grid, global education | R Own | R Own | — | — | — | — | — |
| Entitlements | R Own | R Own | — | — | — | — | — |
| Notifications (own) | R | R | R | R | (API yes, no page) | (API yes, no page) | (API yes, no page) |
| Published results / career / psychometric reads | R Own | R Own | R Asg | R Ch | (own dashboards) | | |
| Academic results: create, verify, publish (two-person rule) | — | — | — | — | W Pf | — | — |
| Test prep / language records | — | — | — | — | W Pf | — | — |
| Counselling records, career preferences, career goal | — | — | — | — | — | W Pf | — |
| Skills batches (enrol, sessions, scores) | — | — | — | — | — | W Pf | — |
| Funding cases (create / update) | — | — | — | — | — | W Pf | — |
| Psychometric assign / report / results | — | — | — | — | — | — | W Pf |
| Bulk CSV (results, test prep, language / assessments) | — | — | — | — | W Pf | — | W Pf |
| Student 360° view | R Own (16 tabs) | R Own (16) | R Asg (16) | R Ch (16) | R Pf (some Restricted) | R Pf (some Restricted) | R Pf (some Restricted) |
| Digital Portfolio | W Own | R | W Asg | R | W Pf | R | R |

Tier gating applies on top of this matrix for writes. Appendix 03 §0.4 lists each feature and the tier it needs.

### 5.2 Admin-side school management
| Screen / action | OA | SA | OC |
|---|---|---|---|
| Schools list, Create, Edit / tier, Bulk onboard (`/overseas/admin/schools`) | ✔ | API ✔, **page shows "Workspace not found"** | — |
| School Staff create (`/overseas/admin/school-staff`) | ✔ | API ✔, **page "Workspace not found"** | — |
| School Applications (`/overseas/admin/school-applications`) | ✔ | API ✔, **page "Workspace not found"** | ✔ (own: `/overseas/counselor/school-applications`) |
| School Transfers | ✔ | ✔ (typed URL; not in SA sidebar; shows the OA sidebar) | — |
| Activity Feedback | ✔ | ✔ (typed URL; shows the OA sidebar) | — |
| School Analytics | ✔ | ✔ (in SA sidebar) | — |
| Re-send set-password link (Users page) | ✔ | VERIFICATION REQUIRED | — |

### 5.3 Frontend-guard gaps
The API still enforces the data scope in every case below, so no data leaks. What goes wrong is the page wrapper.

Some pages have **no role check of their own**. When another school role opens one of them, the page renders with that portal's sidebar and role label, and shows the visitor's own data scope:
- Coordinator: Dashboard, Students, Bulk upload, Activities, Team, Entitlements, 360.
- Principal: Dashboard, Entitlements, Student page.
- Teacher: Dashboard, Student page.
- Parent: Dashboard, Child page, Notifications.
- All seven service-role and school-role 360° pages.
- All service-role pages except Funding.

For example, a Principal who opens `/school/parent/dashboard` sees every student in the school listed as "My children".

The guides document only each role's **own** URLs. These cases are listed for the product owner in §12.2.

---

## 6. Frontend Route Inventory (in scope)

### 6.1 Account access (shared)
| Route | Purpose | Auth |
|---|---|---|
| `/overseas/login` | Sign in (all school roles, OA) | public |
| `/overseas/forgot-password` | Request reset | public |
| `/overseas/reset-password?token=` | Reset password **and** first-time set-password (welcome link) | public (token) |
| `/school/invite/[token]/accept` | Accept a Coordinator invite (PR/TE/PA) | public (token) |
| `/account/password` | Change password | signed in |
| `/account/profile` | Profile + notification settings | signed in |

### 6.2 School portals (41 routes)
| Portal | Routes |
|---|---|
| Coordinator (14) | `dashboard`, `students`, `students/bulk-upload`, `students/[id]`, `students/[id]/360`, `promotion`, `transfers`, `activities`, `feedback`, `team`, `reports`, `global-education`, `entitlements`, `notifications` (prefix `/school/coordinator/`) |
| Principal (8) | `dashboard`, `reports`, `global-education`, `feedback`, `entitlements`, `notifications`, `students/[id]`, `students/[id]/360` (prefix `/school/principal/`) |
| Teacher (4) | `dashboard`, `attendance`, `students/[id]`, `students/[id]/360` |
| Parent (4) | `dashboard`, `notifications`, `children/[id]`, `children/[id]/360` |
| Academic Team (3) | `dashboard`, `students/[id]`, `students/[id]/360` |
| Career Counselor (5) | `dashboard`, `skills`, `skills/[id]`, `funding`, `students/[id]/360` |
| Psychometric Team (2) | `dashboard`, `students/[id]/360` |
| Invite (1) | `/school/invite/[token]/accept` (also in 6.1) |

### 6.3 Admin side (8)
| Route | Notes |
|---|---|
| `/overseas/admin/schools` | generic `[section]` page + Create / Edit / Bulk panels |
| `/overseas/admin/school-staff` | generic `[section]` page + staff create panel |
| `/overseas/admin/school-applications` | generic `[section]` page + application panel |
| `/overseas/counselor/school-applications` | the Counselor's version of the same panel |
| `/overseas/admin/school-transfers` | standalone page |
| `/overseas/admin/activity-feedback` | standalone page |
| `/overseas/admin/school-analytics` | standalone page |
| `/overseas/admin/users` | only for the re-send set-password action (SADM-010) |

**In-scope total: 54 routes** (5 shared account routes + 41 portal routes + 8 admin routes).

**Documented routes that do not exist:**
- `/school/coordinator/students/new` (SCR-SCH-004). The "Add one student" form is inline on the roster.
- `/school/academic-team/results/new` and `/results/[id]`.
- `/school/career-counselor/students/[id]/records`.
- `/school/psychometric-team/students/[id]/assessments`.

---

## 7. Backend API Mapping

All endpoints are under `/api/v1`. Counts are the decorated routes in each file at `ce1f07c2`.

| API group | File(s) | Endpoints | Used by |
|---|---|---|---|
| School core: roster, team, invites, dashboard, reports, entitlements, activities, results, career, psychometric, test prep, language, promotion, academic years (read), timeline, 360 sources | `apps/api/app/api/schools.py` | 47 | all school + service roles |
| Transfers (school side + admin decide) | `school_transfers.py` | 10 | CO, OA/SA |
| Analytics (school + cross-school) | `school_analytics.py` | 6 | CO, PR, OA/SA |
| Bulk entry CSV (results, test prep, language, assessments) | `school_bulk.py` | 8 | AT, PT |
| School onboarding CSV | `school_onboarding_bulk.py` | 2 | OA/SA |
| Activity feedback | `school_feedback.py` | 3 | CO, PR, OA/SA |
| Reports PDF | `school_reports.py` | 2 | CO, PR, PA |
| Global education | `school_global_education.py` | 1 | CO, PR |
| Daily attendance | `school_attendance.py` | 2 | TE |
| Skills batches | `school_skills.py` | 10 | CC |
| Funding cases | `school_funding.py` | 4 | CC (+ readers) |
| Student photo, career preferences | `school_student_profile.py` | 5 | CO, CC (+ readers) |
| Digital Portfolio + certificates | `portfolio.py`, `portfolio_certificates.py` | 5 + 3 | CO, TE, AT (+ readers) |
| Student 360° view + career goal | `student_360.py` | 2 | all 7 |
| Admin school mgmt: schools, tier preview, staff, portfolio add, academic years, school applications, lookups | `admin.py` (`/overseas-admin/*`) | 14 | OA/SA (+ OC for applications) |
| Pickers | `lookups.py` (`/lookups/schools`, `/lookups/school-students`) | 2 | OA, OC, SA |
| Generic admin workspace payload | `portal.py` (`/portal/overseas/admin/{section}`) | 1 | OA |
| Auth + account preferences | `auth.py`, `account.py` | ~10 | all |
| Notifications | `workflows.py` (`/workflows/notifications`, `…/{id}/read`) | 2 | all |
| Re-send welcome link | `/admin/users/{id}/welcome-links` | 1 | OA (SADM-010) |

**About 140 endpoints in scope across 20 API groups.**

**Endpoints with no UI** (they are not documented as user features):
- staff portfolio add
- staff list
- `school-students/lookup`
- admin transfer history
- academic years create / update / list
- roster upload batch status
- edit a Draft result
- test-prep mock scores
- language classes attended / score

### Integrations
| Integration | Where | Doc impact |
|---|---|---|
| SMTP mailer: invites and welcome links | `services/mailer.py`, `services/provisioning.py` | The success text changes when email is not configured ("share the link manually" / amber warning). The docs stack must route mail to a local Mailpit (see `docs/documentation-progress.md` stack row). |
| Generic email webhook: password reset | `services/integrations.py` | The reset email carries a token, not a link. VERIFICATION REQUIRED (§12.1). |
| Notification deliveries: email, plus WhatsApp / SMS when opted in | `queue_deliveries` | Parents and staff get in-app notices. Which other channels are enabled depends on the environment: VERIFICATION REQUIRED. |
| File storage: student photos (JPEG / PNG ≤ 2 MB), internship certificates (PDF / JPEG / PNG ≤ 5 MB) | `school_student_profile.py`, `portfolio_certificates.py` | Upload limits are documented. Image metadata is stripped. |
| PDF generation: school report, progress report | `school_reports.py` | Download steps. |

---

## 8. Feature-to-Route Mapping

| Doc ID(s) | Route(s) | Main endpoints |
|---|---|---|
| AUTH-001 | `/overseas/login` | `POST /auth/login` |
| AUTH-002 | `/school/invite/[token]/accept` | `POST /school/invites/{token}/accept` |
| AUTH-003, AUTH-004 | `/overseas/reset-password`, `/overseas/forgot-password` | `POST /auth/reset-password`, `/auth/forgot-password` |
| AUTH-005, AUTH-006 | `/account/password`, `/account/profile` | `POST /auth/change-password`, `PATCH /auth/me`, `GET/PUT /account/notification-preferences` |
| AUTH-007..009 | every portal page | `POST /auth/logout`, `GET /auth/me` |
| DASH-001 | `/school/coordinator/dashboard` | `GET /school/dashboard`, `/school/results`, `/school/career-records`, `/school/psychometric-records` |
| DASH-002 | `/school/principal/dashboard` | same + `GET /school/students` |
| DASH-003 | `/school/teacher/dashboard` | `GET /school/students` + 3 reader lists |
| DASH-004 | `/school/parent/dashboard` | `GET /school/students`, `/school/students/{id}/overview`, `/workflows/notifications` |
| DASH-005 / 006 / 007 | `/school/{academic-team|career-counselor|psychometric-team}/dashboard` | see ACAD / CAR / PSY |
| STU-001..004 | `/school/coordinator/students` | `GET/POST /school/students`, `PATCH /school/students/{id}`, `POST …/{id}/parents`, `GET /school/team` |
| STU-005 | `/school/coordinator/students/bulk-upload` | `GET /school/students/roster-template`, `POST /school/students/bulk-upload` |
| STU-006 | `/school/{coordinator|principal|teacher}/students/[id]` | `GET /school/students/{id}`, `…/timeline`, `…/grade-history`, `…/transfer-history`, `…/scorecard`, `…/funding-records` |
| STU-007 | `/school/coordinator/students/[id]` | `GET/PUT/DELETE /school/students/{id}/photo` |
| STU-008 | student page / child page | `GET /school/students/{id}/progress-report` |
| STU-009 | `/school/coordinator/promotion` | `GET /school/academic-years/active`, `POST /school/students/promotions` |
| XFER-001 | `/school/coordinator/students/[id]` (Request a transfer) | `GET /school/transfer-destinations`, `POST /school/students/{id}/transfer-requests` |
| XFER-002, 003 | `/school/coordinator/transfers` | `POST /school/transfer-requests/incoming`, `GET /school/transfer-requests`, `POST …/{id}/cancel` |
| ACT-001, 002 | `/school/coordinator/activities` | `GET/POST /school/activities`, `POST /school/activities/{id}/attendance` |
| ACT-003 | `/school/coordinator/feedback` | `GET /school/activity-feedback`, `POST /school/activities/{id}/feedback` |
| ACT-004 | `/school/principal/feedback` | `GET /school/activity-feedback` |
| ACT-005 | `/school/teacher/attendance` | `GET/PUT /school/attendance` |
| TEAM-001..003 | `/school/coordinator/team` | `GET /school/team`, `POST /school/team/invites`, `PATCH /school/team/accounts/{id}` |
| RPT-001 | `…/reports` | `GET /school/reports/school-summary` |
| RPT-002 | `…/reports` | `GET /school/reports` |
| RPT-003..005 | `…/reports` | `GET /school/analytics/grade-performance`, `…/student-development`, `…/scorecards` |
| RPT-006 | `…/global-education` | `GET /school/global-education/pipeline` |
| ENT-001 | `…/entitlements` | `GET /school/entitlements` |
| NOTIF-001, 002 | `…/notifications` (+ parent dashboard card) | `GET /workflows/notifications`, `PATCH …/{id}/read` |
| PAR-001 | `/school/parent/children/[id]` | overview, timeline, grade-history, transfer-history, portfolio, funding-records, progress-report, photo |
| ACAD-001..007 | `/school/academic-team/dashboard` | `/school/academic-team/progress`, `…/results` (+ verify / publish), `…/test-prep-records`, `…/language-records`, bulk templates / uploads |
| CAR-001..003 | `/school/career-counselor/dashboard` | `/school/career-counselor/records`, `/school/students/{id}/career-preferences` |
| CAR-004 | `/school/career-counselor/students/[id]/360` | `PATCH /school/students/{id}/career-goal` |
| CAR-005..009 | `/school/career-counselor/skills`, `skills/[id]` | `/school/career-counselor/skill-batches`, `…/enrollments`, `…/sessions`, `…/attendance`, `…/assessments`, `…/scores` |
| CAR-010, 011 | `/school/career-counselor/funding` | `/school/career-counselor/funding-records`, `POST/PATCH /school/funding-records` |
| PSY-001..004 | `/school/psychometric-team/dashboard` | `/school/psychometric-team/records`, bulk template / upload |
| S360-001 | `…/students/[id]/360`, `/school/parent/children/[id]/360` | `GET /school/students/{id}/360-view` |
| PORT-001..005 | `/school/academic-team/students/[id]`, coordinator / teacher / principal student pages, parent child page | `/school/students/{id}/portfolio` (+ entries, personal-statement, certificate) |
| SADM-001..004 | `/overseas/admin/schools` | `GET /portal/overseas/admin/schools`, `POST/GET /overseas-admin/schools`, `…/lookup`, `…/tier-change-preview`, `PATCH …/{id}`, bulk template / upload |
| SADM-005 | `/overseas/admin/school-staff` | `POST /overseas-admin/school-staff` |
| SADM-006 | `/overseas/admin/school-applications`, `/overseas/counselor/school-applications` | `/lookups/schools`, `/lookups/school-students`, `POST /overseas-admin/school-students/{id}/applications`, `GET /overseas-admin/school-applications` |
| SADM-007 | `/overseas/admin/school-transfers` | `GET /overseas-admin/school-transfer-requests`, `…/approve`, `…/reject` |
| SADM-008 | `/overseas/admin/school-analytics` | `/overseas-admin/analytics/summary`, `/analytics/schools` |
| SADM-009 | `/overseas/admin/activity-feedback` | `/overseas-admin/school-activity-feedback` |
| SADM-010 | `/overseas/admin/users` | `POST /admin/users/{id}/welcome-links` |
| SADM-011 | the three generic pages as SA | `GET /portal/overseas/admin/{section}` → 404 |

---

## 9. Major User Workflows

These end-to-end paths cross features and roles. Each module session follows them to create its data.

1. **Onboard a partner school.**
   1. OA creates the school with a tier (SADM-002, or SADM-004 by CSV).
   2. The Coordinator receives a welcome email and sets a password (AUTH-003).
   3. The Coordinator signs in (AUTH-001) and lands on the dashboard (DASH-001).
2. **Build the school.**
   1. CO adds students one at a time or by CSV (STU-002 / STU-005).
   2. CO assigns teachers (STU-003).
   3. CO invites the Principal, Teachers and Parents (TEAM-001), or enters a parent email on a student (STU-002, STU-004).
   4. Each invitee accepts (AUTH-002) and lands on their own dashboard.
3. **Staff the school with EduSphere specialists.**
   1. OA creates AT / CC / PT accounts with the school in their portfolio (SADM-005).
   2. They set their passwords (AUTH-003).
   3. They now see the school's students (DASH-005..007).
4. **Academic result cycle.**
   1. AT member 1 uploads a Draft (ACAD-002, or ACAD-004 by CSV).
   2. AT member 2 verifies it, and a member other than the uploader publishes it (ACAD-003).
   3. The parent is notified (NOTIF-002).
   4. The result shows for the school roles and the parent (PAR-001, S360-001, RPT-004).
5. **Career guidance cycle.**
   1. CC records a guidance session, Not Started → Scheduled → Completed → Follow-up Required (CAR-001 / CAR-002).
   2. CC records career preferences (CAR-003) and sets the career goal (CAR-004).
   3. PT assigns an assessment (PSY-001), attaches the report (PSY-002) and records results (PSY-003).
   4. The parent is notified. The 360° view and the scorecards update.
6. **Skills programme.** CC creates a batch → enrols students → adds sessions and takes attendance → adds assessments and scores → completes or certifies → closes the batch (CAR-005..009).
7. **Activities.** CO schedules a typed activity; parents are notified (ACT-001) → after it takes place, CO marks attendance (ACT-002) and gives feedback (ACT-003) → PR reads the feedback (ACT-004) → OA reads it across schools (SADM-009).
8. **Daily attendance.** TE opens Attendance → marks Present / Absent / Late / Excused → saves (ACT-005) → the parent sees the counts (DASH-004 / PAR-001).
9. **Transfer a student.** The losing CO requests an outgoing transfer (XFER-001), or the gaining CO requests an incoming one (XFER-002) → OA approves or rejects (SADM-007) → both COs and the parents are notified (NOTIF) → the student appears at the new school.
10. **Year rollover.** The academic year is activated, which is API / seed only (§12.1) → CO promotes or holds back students (STU-009) → the grade history updates (STU-006).
11. **Partnership change.** OA upgrades or downgrades the tier (SADM-003) → CO and PR are notified (NOTIF-001) → the Entitlements page changes (ENT-001) → gated actions now succeed or are refused (ENT-002).
12. **Overseas pathway.** OA or OC starts an application for a school student, which needs Gold or higher (SADM-006) → the parent is notified → the Global Education funnel and the 360° view update (RPT-006, S360-001).
13. **Funding support.** CC opens a case (CAR-010) → moves it Required → … → Completed, or closes it with a reason (CAR-011) → CO, PR and the parent see it on the student page (STU-006 / PAR-001).

---

## 10. Required Screenshots

Viewport 1440 × 900, Chromium, light theme. Files go in `docs/school-crm/screenshots/<module>/NN-<feature>-<step>.png`. Estimates come from the discovery passes after removing duplicates:

| Module | Est. shots | Must include |
|---|---|---|
| account-access | 18 | login (masked), invalid credentials, invite accept + used-invite error, set-password, forgot / reset, change password + wrong current, profile + notification settings, access-unavailable (signed out / wrong role / deactivated), sidebar + mobile menu |
| dashboards | 12 | each of 7 dashboards; coordinator KPI board; parent multi-school grouping |
| students | 20 | roster, add form, add success (invite sent), roll-number conflict, edit, link parent + error, bulk template + column reference + mixed result, student page sections, photo upload, progress report, promotion list / confirm / result |
| transfers | 7 | outgoing form + pending state, incoming form + neutral success, list filters, cancel |
| activities | 12 | schedule form, tier-denied, mark attendance, feedback list / form / submitted / duplicate, principal read view, teacher attendance unmarked / saved / future-date / leave prompt |
| team | 6 | team list, invite form, invite sent, pending invites, deactivate |
| reports | 10 | download PDF, tiles, by-grade, grade comparison, student development + thresholds, scorecards grid + filter, global education funnel + list |
| entitlements | 3 | Platinum list, no-tier message, a tier-denied error example |
| notifications | 4 | staff list, tier-change notice, parent table, parent dashboard card |
| parent | 5 | child overview, results / activities, funding / grade / transfer history, 360 entry |
| academic-team | 16 | progress, results with uploader view, upload form / success, verify, publish, bulk (expanded + report), test prep start / score, language start / certify |
| career-counselor | 21 | records, add record (each status), edit / 409, preferences, career goal, skills list / filters / create, batch header / close, enrol, certify confirm, session attendance, scores, closed read-only, funding list / add / stage / close / finished |
| psychometric-team | 7 | dashboard, assign, attach report, results form + validation, bulk |
| student-360 | 6 | tab list (school role), restricted tab (service role), examination results, career guidance, Edusphere programs, mobile tab list |
| portfolio | 10 | overview %, add entry, Skill India form + validation, internship tracking, certificate upload, personal statement, delete confirm, Platinum-only notice |
| admin-schools | 30 | sidebar, schools table, create (empty / filled / success / amber / 409), edit lookup / form / upgrade / downgrade confirm / no changes / not found, bulk (panel / reference / mixed / file error), staff (table / form / success), applications (pick / form / success / tier denied), transfers (queue / warnings / approve / reject / filter / empty), analytics (KPIs / table / search), feedback (list / filter), SA "Workspace not found" |
| **Total** | **≈ 187** | |

---

## 11. Required Test Data

The seed covers one Platinum school with every role. **Everything else must be created through the UI during the module sessions**, recorded in each session, and named `Docs …` / `*@example.test`. Never use real customer data.

| # | Data | Needed for | Created in |
|---|---|---|---|
| D1 | Seed: Sunrise Public School (Platinum), CO / PR / TE / PA, AT×2, CC, PT, students Aarav, Isha (both linked to the parent), Kabir, Priya, Rohan; seeded results / career / psychometric records | most features | `python -m app.seed` (owner) |
| D2 | **Docs Bronze School** (Bronze), **Docs No-Tier School** (no tier), **Docs Renewal School** (Gold, valid until about +30 days), **Docs Expired School** (valid until yesterday) | tier-denied messages, analytics flags, entitlements | SADM-002 / 003 / 004 (S3) |
| D3 | A bulk onboarding CSV with 2 good rows plus a duplicate coordinator email, a bad tier and a duplicate name + city | SADM-004 | S3 (fixture under the session scratchpad; only the screenshot is committed) |
| D4 | New staff: AT, CC and PT with a 2-school portfolio; one account with an empty portfolio | SADM-005, empty-portfolio states | S3 |
| D5 | Grade 8–12 students (≥ 2 per grade), one with no grade level, one with a label that does not match its level; a roll-number clash; a student created today | KPIs, promotion, scorecards, attendance edge cases | S4 |
| D6 | Roster CSV with mixed valid / invalid rows | STU-005 | S4 |
| D7 | Invites: PR, TE and PA pending; one accepted; one expired (needs a DB time shift, or else documented as VERIFICATION REQUIRED); an inactive teacher | TEAM, AUTH-002 / 008 | S4 |
| D8 | Activities: future typed, past typed (feedback awaiting / submitted), past untyped; attendance marks | ACT, RPT-002, SADM-009 | S5 (past dates: the scheduling form accepts them) |
| D9 | Daily attendance across several days for the teacher's class | ACT-005, PAR-001 | S5 |
| D10 | An **active academic year** that differs from the students' year | STU-009 | **owner / API only** (§12.1, U3) |
| D11 | Transfer requests: pending out, pending in, approved, rejected with a note, cancelled; a pending request to a school with no staff portfolio; a student with a pending parent invite | XFER, SADM-007 | S6 |
| D12 | Results in Draft / Verified / Published (two AT accounts), with marks below 40 % and at or above 85 %; test prep and language records; bulk CSVs for each target | ACAD, RPT-004 | S7 |
| D13 | Portfolio entries in every section; a Skill India certification; a completed internship plus a sample PDF ≤ 5 MB and a > 5 MB file | PORT | S7 |
| D14 | Career records in every status; career preferences; career goal; skills batches (Soft open, Digital closed); enrolments in every status; sessions; assessments; funding cases at different stages + one closed | CAR | S8 |
| D15 | Psychometric assessments: assigned, report attached, results recorded; bulk CSV | PSY | S9 |
| D16 | Overseas applications for school students at several stages + a visa case (Global Education funnel); one university in the public list | SADM-006, RPT-006 | S9 (stages beyond `enquiry` may need the Overseas Counselor's application screens, which are out of scope; record how) |
| D17 | A parent linked to children at two schools | DASH-004 | S6 (second-school coordinator links the existing parent email) |
| D18 | Tier upgrade then downgrade on a Docs school (notifications) | SADM-003, NOTIF-001 | S3 / S10 |

**Email.** Invites and welcome links must be readable without real mail. Run the docs stack with the Mailpit override as in the Agent CRM docs stack. `shoot.ts` `mailLink()` only matches `reset-password` links, so S2 must add a matcher for `/school/invite/<token>/accept`.

---

## 12. Unknown Workflows Requiring Browser Verification

### 12.1 Cannot be confirmed from code
| # | Item | Affects | Plan |
|---|---|---|---|
| U1 | Session length: the web app never calls `/auth/refresh`. Does a session really end at 60 min, and what does the user see? | AUTH-007 | S2: verify (shorten the token lifetime only if the owner agrees; otherwise document as VERIFICATION REQUIRED) |
| U2 | The reset email goes through the generic webhook with a raw token, not a link. Does a real user ever get a clickable link? | AUTH-004 | S2: check Mailpit / webhook. Owner question if no link arrives |
| U3 | How the **active academic year** is created in production. There is no admin UI; the API and seed exist | STU-009 | S1 → owner (question asked at the end of S1); S6 needs an active year |
| U4 | What `/school/coordinator/students/new` displays (likely "[object Object]") | STU-001 (note only) | S4 |
| U5 | Messages for over-length full name (> 160), Grade / Class (> 60 via CSV), activity title (> 200), single-entry result fields, malformed date of birth: probably a generic 500 | STU-002 / 005, ACT-001, ACAD-002 | S4, S5, S7: try once; document what is shown |
| U6 | Exact browser-native validation bubbles for `required` / `type=email` fields | many | Use the Chromium wording as captured; say "your browser asks you to fill in this field" rather than quoting it |
| U7 | Exact Pydantic 422 wording on admin forms (e.g. "String should have at most 200 characters") | SADM-002 / 004 | S3 |
| U8 | Parent notifications never marked read: the "new" badges and the "{n} unread" count never clear | NOTIF-002, DASH-004 | S10 |
| U9 | The "Upcoming session" notification time is built from UTC, so it may show UTC instead of IST | NOTIF-002, ACT-001 | S5 |
| U10 | Which delivery channels (email / WhatsApp / SMS) are active in the docs environment | NOTIF | S2 (stack config) |
| U11 | Super Admin "Workspace not found" on Schools / School Staff / School Applications | SADM-011 | S3 |
| U12 | The Users page re-send set-password action for school users (not covered by discovery) | SADM-010 | S3: code-review the Users panel, then verify |
| U13 | Template example row ("Jane Doe") is imported as a real student if left in | STU-005 | S4 |
| U14 | Teacher portfolio editing: section list and server errors as seen by a Teacher | PORT-002 | S7 |
| U15 | Stages beyond `enquiry` for school-linked overseas applications (what moves the funnel) | RPT-006, D16 | S9 |
| U16 | The 360° view on mobile widths: tab list behaviour | S360-001 | S9 (one 390 px shot, noted in the index) |

### 12.2 As-built behaviour the product owner should know about
These are documented **as they are, not changed**. The docs describe the real behaviour and add Tips or Common Errors where users will hit them.

1. **Frontend role guards are inconsistent** (§5.3). Other school roles can open many pages, which then render under the wrong portal label. The API still limits the data.
2. **Super Admin is blocked** from Schools, School Staff and School Applications ("Workspace not found"), although the panels and APIs allow the role. Transfers and Activity Feedback open for SA but show the Overseas Admin sidebar and label.
3. **Staff portfolios cannot be changed after the account is created.** There is no add UI and no remove API, although the help text says "can be left empty and filled in later".
4. **There is no academic-year admin UI.** Promotion depends on an active year.
5. The login page talks only about overseas users, lists no school demo accounts, and is the only way in for school users. Sidebar "Sign out" goes to the site home page, not the login page.
6. **Roster:**
   - no search, filter, sort or pagination
   - the Parent column shows only pending invites, never linked parents
   - parent links cannot be viewed or removed
   - no delete or archive
   - the student page shows neither the teacher nor the parents
7. **Team invites:**
   - pending invites cannot be resent or revoked, and "share the link manually" appears without a link
   - a parent who accepts an invite sent from the Team page does not appear on the Team list until linked to a student
   - one account-wide `active` flag means deactivating a parent from one school blocks them at every school
8. **Activities:**
   - cannot be edited, cancelled or deleted
   - past dates are accepted
   - the type is not shown in the list
   - the attendance card always opens with everyone ticked present and overwrites the saved marks
9. **Tier gating happens only on the server:**
   - gated options are not hidden
   - Entitlements does not warn about an expired partnership
   - changing only "Valid until" sends no notification
   - Create school has no "Valid until" field, although bulk onboarding does
   - single Create allows a duplicate school name and city, which bulk onboarding rejects
10. **Counting differences:**
    - the dashboard "Applications in Progress" and "Offers Received" tiles count applications, while the tiles next to them count students
    - the Reports "Career guidance" ring counts any career record, while the KPI counts only completed guidance sessions
11. `GET /school/reports` returns the dashboard payload; the old report code after its `return` never runs.
12. **Academic Team:**
    - the single-entry result form does not check marks ranges, duplicates or field lengths (bulk CSV does)
    - results are not tier-gated
    - a Draft cannot be edited from the UI
    - result status history is stored but never shown
    - status codes appear in raw lowercase (`draft`, `in_progress`, `assigned`)
13. Psychometric "Attach report" takes a free-text URL, not a file upload, and cannot be changed afterwards. Skill India certifications have no file upload; only completed internships do.
14. The Digital Portfolio "Career guidance" list shows raw record-type codes.
15. Skills: a portfolio school with no students cannot get a batch.
16. Admin generic tables show:
    - a raw UUID "reference" column
    - lowercase tier and role values
    - ISO timestamps

    The School Applications page shows the same applications twice, and its subtitle says "by Student ID" while the form uses a school-then-student picker.
17. Docs drift: ROLE_NAVIGATION / SCREEN_CATALOG list five routes that do not exist (§6).
