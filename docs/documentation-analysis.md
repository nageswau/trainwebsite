# EduSphere Agent CRM — Documentation Analysis (Phase 1)

| | |
|---|---|
| Status | Phase 1 complete — discovery from source code only. **No browser verification yet.** |
| Prepared | 2026-10-05 (master planning session) |
| Code baseline | committed `main` **`e376c25c`** (owner decision 2026-10-05). Uncommitted working-tree edits are ignored; see §1.4. |
| Scope | **Agent CRM only** (owner decision 2026-10-05): agency registration/sign-in, the whole Agent Portal (`/overseas/agent/*`, Master and Staff), and the Overseas/Super Admin screens that manage agencies (Agents approvals, Agent network, Agent deposits, Commissions). |
| Out of scope | IT division, School division, BDM CRM, other Overseas roles (student, counselor, university rep) except where an agent workflow touches them. |
| Method | Graphify graph (refreshed to `e376c25c`, 16,418 nodes) for orientation → source reading at HEAD with file:line evidence → this report. |
| Authority | This file describes **as-built behaviour** for user documentation. It is not a requirement, decision or approval record (see `CLAUDE.md`). Where code and derived docs (specs, backlog, QA notes) differ, code wins. |

Legend used throughout: **M** = agency Master, **S** = agency Staff, **OA** = Overseas Admin, **SA** = Super Admin,
**Own** = only students assigned to the staff member and their records, **RO** = read-only,
**VERIFICATION REQUIRED** = cannot be confirmed from code; must be confirmed in the browser before it is documented.

---

## 1. Application Overview

### 1.1 What the Agent CRM is
EduSphere is a multi-division education platform (IT training, Overseas education, Schools). The **Agent CRM** is the
Overseas-division workspace for **education agencies** (recruitment partners). An agency registers, is approved by
EduSphere's Overseas Admin, and then manages its own students (with or without an EduSphere login), university
shortlists, applications, offers, deposits, visa cases, enrollments, documents, tasks, notifications, commissions and
reports. An agency has one to three **Masters** (owners/managers) and any number of **Staff** logins; Staff see only the
students assigned to them.

### 1.2 Technology (verified)
| Layer | Technology | Evidence |
|---|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript | `apps/web/package.json` |
| Backend | FastAPI (Python), SQLAlchemy async, Alembic migrations | `apps/api/app/main.py`, `apps/api/alembic/` |
| Database | PostgreSQL | `docker-compose.yml` |
| Background jobs | Celery worker + beat on Redis | `apps/api/app/worker.py`, compose services `worker`, `beat` |
| File storage | S3 when `AWS_S3_BUCKET` is set (presigned URLs, 900 s), otherwise local `LOCAL_UPLOAD_DIR` served at `/local-files` | `apps/api/app/services/storage.py` |
| Payments | Razorpay Checkout + signed webhook | `apps/web/lib/razorpayCheckout.ts`, `apps/api/app/api/payments.py:241-280` |
| Browser tests | Playwright 1.62.1 (Chromium installed) | `apps/web/package.json`, `%LOCALAPPDATA%/ms-playwright` |
| API proxy | The web app forwards `/api/*` to the API (`apps/web/app/api/[...path]/route.ts`); all API paths are under `/api/v1` | `apps/api/app/main.py:75-76` |

### 1.3 Authentication (verified)
- Sign-in at **`/overseas/login`** → `POST /api/v1/auth/login`. Session is a cookie (`edusphere_access`); unauthenticated
  requests to `/overseas/agent/*` and `/overseas/admin/*` are redirected to `/overseas/login?next=…` by
  `apps/web/middleware.ts`. Super Admin signs in at `/admin/login`.
- After sign-in the user lands on the role dashboard: `agent` → `/overseas/agent/dashboard`, `overseas_admin` →
  `/overseas/admin/dashboard`, `super_admin` → `/admin` (`apps/web/lib/navigation.ts:18-44`).
- Self-registration for agencies at `/overseas/register` (`POST /auth/register`) creates a **pending** agency whose
  registrant is Master `M001` (`apps/api/app/api/auth.py:113-143`).
- Forgot / reset password (30-minute link) and first-time "Set your password" invitations for new Masters/Staff
  (72-hour link) both use `/overseas/reset-password?token=…` (`auth.py:218-260`, `services/provisioning.py:37,66-70`).
- Change password at `/account/password` (`auth.py:294-314`), with attempt throttling.
- **Agency-state gate** (`apps/api/app/core/rbac.py:83-103`): pending, rejected or suspended agencies, and deactivated
  members, **can sign in** but every Agent Portal page shows an **"Access unavailable"** card with a reason.
- No MFA was found.

### 1.4 Baseline note — uncommitted edits
The working tree differs from `e376c25c` in 4 relevant files; **none changes any label or message text**:
| File | Change | Effect on docs |
|---|---|---|
| `apps/web/components/AgentPerformancePanel.tsx` | "Figures as of …" timestamp format | Screenshot of Staff Performance will differ if this ships |
| `apps/web/components/AgentNetworkRecords.tsx`, `AgentOrgDetailPanel.tsx` | Date formatting in viewer time zone | Date format in Agent network screenshots may differ |
| `apps/api/app/models.py` | New index + unique `school_code`; **no migration seen** | None for users |

Browser sessions must run the stack built from `e376c25c` (not the working tree, and not the `bdm006`/`bdm009` worktree
stacks that are currently running).

---

## 2. Module Inventory

| # | Module | Code ID | Audience | AGN features | Primary route(s) |
|---|---|---|---|---|---|
| 1 | Account access | AUTH | Prospective agency, M, S | AGN-001, AGN-002 | `/overseas/register`, `/overseas/login`, `/overseas/forgot-password`, `/overseas/reset-password`, `/account/password`, `/account/profile` |
| 2 | Dashboard | DASH | M, S | AGN-018 | `/overseas/agent/dashboard` |
| 3 | Students | STU | M, S | AGN-004/005, 006, 007, 015 | `/overseas/agent/students` |
| 4 | Universities (agency database) | UNI | M (edit), S (view) | AGN-007 | `/overseas/agent/universities` |
| 5 | Applications (incl. offer, deposit, visa, enrollment) | APP | M, S (enrollment M only) | AGN-008, 010, 011, 012, 013 | `/overseas/agent/applications` |
| 6 | Documents | DOC | M, S | AGN-009 (+AGN-003) | `/overseas/agent/documents` |
| 7 | Tasks & follow-ups | TASK | M, S | AGN-016 | `/overseas/agent/tasks` |
| 8 | Notifications | NOTIF | M, S | AGN-017 | `/overseas/agent/notifications` |
| 9 | Commissions | COMM | M | AGN-014 (AGT-003) | `/overseas/agent/commissions` |
| 10 | Reports | RPT | M, S with permission | AGN-020, AGN-014 | `/overseas/agent/reports` |
| 11 | Team & staff | TEAM | M | AGN-001 (D9), 002, 003, 021 | `/overseas/agent/team` |
| 12 | Staff performance | PERF | M | AGN-019 | `/overseas/agent/performance` |
| 13 | Agency administration (admin side) | ADM | OA (act), SA (mostly read) | AGN-001 (D6/D7), 011, 014, 022, AGT-004 | `/overseas/admin/agents`, `/agent-network`, `/agent-network/{orgId}`, `/agent-deposits`, `/commissions` |

**Total: 13 modules.**

---

## 3. Feature Inventory

54 documentable features. IDs are the documentation IDs used in the plan and progress tracker.

| Doc ID | Module | Feature | Roles | AGN |
|---|---|---|---|---|
| DOC-AUTH-001 | AUTH | Register an agency | Visitor | AGN-001 |
| DOC-AUTH-002 | AUTH | Sign in and sign out | M, S | AGN-001/002 |
| DOC-AUTH-003 | AUTH | "Access unavailable" states (pending, rejected, suspended, deactivated) | M, S | AGN-001 D6 |
| DOC-AUTH-004 | AUTH | Forgot / reset password and first-time "Set your password" link | M, S | AGN-002 |
| DOC-AUTH-005 | AUTH | Change password | M, S | ENH-006 |
| DOC-AUTH-006 | AUTH | My profile (sidebar footer) | M, S | — (**code not yet reviewed**) |
| DOC-DASH-001 | DASH | Agency dashboard — Master view | M | AGN-018 |
| DOC-DASH-002 | DASH | Agency dashboard — Staff view | S | AGN-018 |
| DOC-STU-001 | STU | Find students (list, search, filter, pages) | M, S(Own) | AGN-004/005 |
| DOC-STU-002 | STU | Add a student (incl. duplicate warning) | M, S | AGN-004 |
| DOC-STU-003 | STU | View and edit a student record | M, S(Own) | AGN-004 |
| DOC-STU-004 | STU | Archive / unarchive a student | M | AGN-004 |
| DOC-STU-005 | STU | Assign a student to a staff member | M | AGN-004 |
| DOC-STU-006 | STU | Record counseling | M, S(Own) | AGN-006 |
| DOC-STU-007 | STU | Build a university shortlist | M, S(Own) | AGN-007 |
| DOC-STU-008 | STU | View a student's journey and history | M, S(Own) | AGN-015 |
| DOC-STU-009 | STU | Link an existing student account (legacy "Link student") | M, S | AGT-002 |
| DOC-UNI-001 | UNI | Manage the agency university list | M (CRUD), S (view) | AGN-007 |
| DOC-APP-001 | APP | View and filter applications | M, S(Own) | AGN-008 |
| DOC-APP-002 | APP | Create an application | M, S(Own) | AGN-008 |
| DOC-APP-003 | APP | Edit an application | M, S(Own) | AGN-008 |
| DOC-APP-004 | APP | Read the application detail page | M, S(Own) | AGN-008 |
| DOC-APP-005 | APP | Change application status / withdraw | M, S(Own) | AGN-008 |
| DOC-APP-006 | APP | Record or edit an offer | M, S(Own) | AGN-010 |
| DOC-APP-007 | APP | Record deposit terms and pay the deposit (Razorpay) | M, S(Own) | AGN-011 |
| DOC-APP-008 | APP | Run the visa case | M, S(Own) | AGN-012 |
| DOC-APP-009 | APP | Confirm enrollment | M | AGN-013 |
| DOC-DOC-001 | DOC | Browse documents (Pending / Uploaded) and download | M, S(Own) | AGN-009 |
| DOC-DOC-002 | DOC | Upload a document | M, S(Own) | AGN-009/010 |
| DOC-DOC-003 | DOC | Replace a document file | M, S(Own) | AGN-009 |
| DOC-DOC-004 | DOC | Review a document (verify / reject / request changes) | M; S verify-only with permission | AGN-009/003 |
| DOC-DOC-005 | DOC | Document history | M, S(Own) | AGN-009 |
| DOC-DOC-006 | DOC | Request an additional document and manage requests | M, S(Own) | AGN-009 |
| DOC-TASK-001 | TASK | View tasks and follow-ups | M, S(Own) | AGN-016 |
| DOC-TASK-002 | TASK | Add, edit, complete or cancel a task | M, S(Own) | AGN-016 |
| DOC-NOTIF-001 | NOTIF | Read notifications (and what triggers them) | M, S | AGN-017 |
| DOC-COMM-001 | COMM | View and claim commissions | M | AGN-014 |
| DOC-RPT-001 | RPT | Run agency reports (7 tabs, filters) | M; S with permission | AGN-020 |
| DOC-RPT-002 | RPT | Export a report to CSV | M; S with permission | AGN-020 |
| DOC-RPT-003 | RPT | Commission report tab | M | AGN-014 |
| DOC-TEAM-001 | TEAM | Invite or deactivate a Master | M | AGN-001 D9 |
| DOC-TEAM-002 | TEAM | Create a staff login | M | AGN-002 |
| DOC-TEAM-003 | TEAM | Edit, reset, deactivate, reactivate a staff member | M | AGN-002 |
| DOC-TEAM-004 | TEAM | Set staff permissions | M | AGN-003 |
| DOC-TEAM-005 | TEAM | View a staff member's activity | M | AGN-021 |
| DOC-PERF-001 | PERF | View staff performance (funnel by staff) | M | AGN-019 |
| DOC-ADM-001 | ADM | Approve, reject, suspend, reinstate agencies (Agents) | OA | AGN-001 D6/D7 |
| DOC-ADM-002 | ADM | Agent network list | OA, SA(RO) | AGN-022 |
| DOC-ADM-003 | ADM | Agency detail, money summary and read-only drill-down | OA, SA(RO) | AGN-022 |
| DOC-ADM-004 | ADM | Suspend / reinstate from the agency detail page | OA | AGN-022 |
| DOC-ADM-005 | ADM | Record deposit remittance and refund | OA | AGN-011 |
| DOC-ADM-006 | ADM | Set commission amounts and approve payouts | OA | AGT-003/004 |
| DOC-ADM-007 | ADM | Super Admin access to agency screens (what is read-only) | SA | — |
| DOC-ADM-008 | ADM | Resend a staff welcome / set-password link (Users) | OA | AGN-002 (**partly reviewed**) |

**Total: 54 features** (46 Agent Portal incl. account access, 8 admin-side; DOC-AUTH-006 and DOC-ADM-008 need a
code review before browser work).

---

## 4. User Role Inventory

The backend has a single role `agent` for every agency member; Master vs Staff comes from the agency membership
(`is_agent_staff`, `apps/api/app/core/rbac.py:106`). Staff have two optional switches (`STAFF_PERMISSIONS`,
`rbac.py:117`, both off by default).

| # | Persona (doc name) | Backend identity | Lands on | Sidebar label pill | Data scope |
|---|---|---|---|---|---|
| 1 | **Agency Master** | role `agent`, membership role `master` | `/overseas/agent/dashboard` | "Education Agent" | Whole agency |
| 2 | **Agency Staff** | role `agent`, membership role `staff` | `/overseas/agent/dashboard` | "Agency Staff" | Own (assigned students only) |
| 2a | Staff + *Verify documents* | `can_verify_documents = true` | — | — | Own; may mark documents **verified** only |
| 2b | Staff + *View reports* | `can_view_reports = true` | — | — | Own; Reports page (no staff/commission reports) |
| 3 | **Overseas Admin** | role `overseas_admin` | `/overseas/admin/dashboard` | — | All agencies (admin screens) |
| 4 | **Super Admin** | role `super_admin` | `/admin` | — | Only Agent network (list/detail) and Agent deposits open, read-only, by URL; Agents, Commissions and Applications show "Workspace not found" (corrected in S11; see DOC-ADM-007) |
| 5 | Visitor / prospective agency | not signed in | `/overseas/register` | — | Registration only |
| 6 | Blocked member (pending / rejected / suspended agency, deactivated member) | role `agent` | Access unavailable card | — | None |

**Total: 4 system personas** (Master, Staff, Overseas Admin, Super Admin) + 2 staff permission variants + 2 non-working
states (visitor, blocked).

---

## 5. Role Permission Matrix

Source: code review of `rbac.py`, `portal.py:30-40`, `agent_*.py` guards, `WorkflowPanel.tsx:352,428`.
Every agency API runs the agency-state gate first; Super Admin is **not** admitted to agency (Agent Portal) APIs
("This role cannot perform this operation", `agent_students.py:40-41`).

| Feature | Master | Staff | Staff + Verify docs | Staff + View reports | Overseas Admin | Super Admin | Blocked agent |
|---|---|---|---|---|---|---|---|
| Dashboard | Agency | Own (no Commission, no staff table) | Own | Own | — | — | No |
| Students: view, add, edit | Yes | Own (new student auto-assigned to self) | Own | Own | RO via Agent network | RO via Agent network | No |
| Students: archive, assign | Yes | No | No | No | — | — | No |
| Counseling, shortlist, journey | Yes | Own | Own | Own | — | — | No |
| Universities: view | Yes | Yes | Yes | Yes | — | — | No |
| Universities: add/edit/delete | Yes | No | No | No | — | — | No |
| Applications: create/edit/status/withdraw | Yes | Own | Own | Own | RO via Agent network | RO via Agent network | No |
| Offer, deposit terms + payment, visa | Yes | Own | Own | Own | Visa via counselor/admin routes | — | No |
| Confirm enrollment | Yes | No ("An agency Master confirms enrollment.") | No | No | — | — | No |
| Documents: upload, replace, request | Yes | Own | Own | Own | — | — | No |
| Documents: verify | Yes | No | Own, verify only | No | Yes (shared route) | Yes (API) | No |
| Documents: reject / changes required | Yes (reason required) | No | No | No | Yes | Yes (API) | No |
| Tasks | Yes | Own | Own | Own | — | — | No |
| Notifications | Own | Own | Own | Own | own only | own only | VERIFICATION REQUIRED |
| Commissions: view, claim | Yes | No (hidden; 403) | No | No | Table + set amount + approve payout | No page (Workspace not found); API allows actions — corrected in S11 | No |
| Reports + CSV | Yes | No (hidden; 403) | No | Own scope; no "Staff performance"/"Commission" tabs | — | — | No |
| Staff performance | Yes | No | No | No | — | — | No |
| Team, staff permissions, staff activity | Yes | No (hidden; 403) | No | No | — | — | No |
| Approve / reject / suspend / reinstate agency | — | — | — | — | Yes | Agents page unavailable; network detail hides buttons; **API allows** — corrected in S11 | — |
| Agent network list + detail | — | — | — | — | Yes | Yes (RO) | — |
| Deposit remittance / refund | — | — | — | — | Yes | No (list RO; API refuses) | — |

Notes for documentation (as-built behaviour, not defects to fix here):
- (Corrected in S11) The Agents and Commissions pages fail for Super Admin ("Workspace not found") and the network detail hides Suspend, but the API accepts these actions
  (`admin.py:1147-1149`, `workflows.py:120`). User docs describe the **UI**; the gap is reported in §12.
- Staff with no permission who type a Master-only URL see "Only an agency Master can open this page" or the
  reports refusal "Your agency Master hasn't given you access to reports".

---

## 6. Frontend Route Inventory (in scope)

| # | Route | Rendered by | Roles | Module |
|---|---|---|---|---|
| 1 | `/overseas/register` | `RegisterForm.tsx` | Visitor | AUTH |
| 2 | `/overseas/login` | `app/overseas/login/page.tsx`, `LoginForm.tsx` | All | AUTH |
| 3 | `/overseas/forgot-password` | `ForgotPasswordForm.tsx` | All | AUTH |
| 4 | `/overseas/reset-password?token=` | `ResetPasswordForm.tsx` | All (also first-time set-password) | AUTH |
| 5 | `/account/password` | `ChangePasswordForm.tsx` | Signed-in | AUTH |
| 6 | `/account/profile` | VERIFICATION REQUIRED | Signed-in | AUTH |
| 7 | `/overseas/agent/dashboard` | `PortalPage.tsx` → `AgentDashboardPanel.tsx` | M, S | DASH |
| 8 | `/overseas/agent/students` (`?new=1`, `?q=&archived=1&page=`) | `AgentStudentsSection/Panel.tsx` (+ detail panel inline) | M, S | STU |
| 9 | `/overseas/agent/universities` | `AgentUniversitiesPanel.tsx` | M, S | UNI |
| 10 | `/overseas/agent/applications` (`?status=all\|draft\|submitted\|offer\|visa\|enrolled\|withdrawn`) | `AgentApplicationsSection/Panel.tsx` (+ detail inline) | M, S | APP |
| 11 | `/overseas/agent/documents` (`?view=pending\|uploaded\|additional`) | `AgentDocumentsSection/Panel.tsx`, `AgentDocumentRequestsPanel.tsx` | M, S | DOC |
| 12 | `/overseas/agent/tasks` (`?view=open\|overdue\|done\|cancelled\|all`) | `AgentTasksSection/Panel.tsx` | M, S | TASK |
| 13 | `/overseas/agent/notifications` | `AgentNotificationsSection.tsx` | M, S | NOTIF |
| 14 | `/overseas/agent/commissions` | generic `PortalSection` + `WorkflowPanel` | M | COMM |
| 15 | `/overseas/agent/reports` (`?report=&from=&to=&…`) | `AgentReportsPanel.tsx`, `AgentCommissionReportPanel.tsx` | M, S+perm | RPT |
| 16 | `/overseas/agent/performance` (`?from=&to=`) | `AgentPerformanceSection/Panel.tsx` | M | PERF |
| 17 | `/overseas/agent/team` | `AgentTeamPanel.tsx`, `AgentStaffPanel.tsx` | M | TEAM |
| 18 | `/overseas/admin/agents` (`?tab=&page=&q=`) | generic table + `AgentApprovalPanel.tsx` | OA (SA table only) | ADM |
| 19 | `/overseas/admin/agent-network` | `AgentNetworkPanel.tsx` | OA, SA | ADM |
| 20 | `/overseas/admin/agent-network/{orgId}` | `AgentOrgDetailPanel.tsx`, `AgentNetworkRecords.tsx` | OA, SA | ADM |
| 21 | `/overseas/admin/agent-deposits` | `AdminAgentDepositsPanel.tsx`, `AdminDepositActionForm.tsx` | OA (SA RO) | ADM |
| 22 | `/overseas/admin/commissions` | generic table + `WorkflowPanel` forms | OA (SA table only) | ADM |

Context-only routes (no feature of their own): `/overseas/admin/dashboard`, `/admin` (Super Admin home),
`/admin/users?role=agent` (DOC-ADM-008), `/overseas/universities` (catalogue link from Universities).
**Total: 22 in-scope page routes**, plus ~15 URL query views (filters/tabs) on those pages.

Agent sidebar (`navigation.ts:117-140`):
- **Master:** Dashboard · Students · Universities · Applications (All applications, Draft, Submitted, Offer received,
  Visa, Enrolled, Withdrawn) · Documents (Pending, Uploaded, Additional) · Tasks & Follow-ups · Notifications (unread
  badge) · Commissions · Reports · Staff Performance · Team. Footer: Change password · My profile · Sign out.
- **Staff:** same minus Team, Commissions, Staff Performance; Reports only with *View reports*; "Students" becomes
  **My Students** (All, Add).

---

## 7. Backend API Mapping

All under `/api/v1`. **12 router files, 85 endpoints** used by this scope (78 agent-dedicated + 7 shared).

| API group | Router file | Prefix | Endpoints | Auth | Used by |
|---|---|---|---|---|---|
| Auth | `api/auth.py` | `/auth` | register, login, logout, me, forgot/reset/change password | Public (register, login, forgot, reset); signed-in (others) | AUTH |
| Agency students | `api/agent_students.py` | `/workflows/overseas/agent/crm/students` | 10 | Gate; S Own; archive/unarchive/assign M | STU |
| Universities + shortlist | `api/agent_shortlist.py` | `/workflows/overseas/agent/crm` | 8 | Gate; university writes M | UNI, STU-007 |
| Applications (incl. offer, visa, enrollment) | `api/agent_applications.py` | `/workflows/overseas/agent/crm/applications` | 9 | Gate; S Own; enrollment M | APP |
| Deposits (agency) | `api/agent_deposits.py` | `/workflows/overseas/agent/crm/applications` | 3 | Gate; S Own | APP-007 |
| Deposits (admin) | `api/agent_deposits.py` (admin_router) | `/overseas-admin/deposits` | 3 | OA list; remit/refund **OA only** | ADM-005 |
| Documents + requests | `api/agent_documents.py` | `/workflows/overseas/agent/crm` | 7 | Gate; S Own; throttled | DOC |
| Tasks | `api/agent_tasks.py` | `/workflows/overseas/agent/crm/tasks` | 4 | Gate; S Own | TASK |
| Dashboard | `api/agent_dashboard.py` | `/workflows/overseas/agent/crm` | 1 | Gate | DASH |
| Performance | `api/agent_performance.py` | `/workflows/overseas/agent/crm` | 1 | M | PERF |
| Reports | `api/agent_reports.py` | `/workflows/overseas/agent/crm/reports` | 2 (`/{kind}`, `/{kind}.csv`) | Gate + *View reports*; `staff` kind M; CSV 30/10 min | RPT |
| Team & staff | `api/agent_team.py` | `/workflows/overseas/agent/team` | 12 | M | TEAM |
| Agency admin | `api/admin.py` (agents_router) | `/overseas-admin` | 9 | OA (+SA by API) | ADM |
| Workflows (agent) | `api/workflows.py` | `/workflows/overseas/agent/*` | 8 (link student, commissions list/report/csv/claim/create/patch) | agent M / OA | STU-009, COMM, RPT-003, ADM-006 |
| Shared workflows | `api/workflows.py` | `/workflows` | 5 (applications, document upload/download/verify, notifications) | role-dependent | DOC, NOTIF |
| Portal payloads | `api/portal.py` | `/portal/{division}/{role}/{section}` | 1 | role match + agency gate | page shells |
| Payments | `api/payments.py` | `/payments` | verify + **public webhook** | signed-in / **HMAC signature** | APP-007 |

Public / non-session endpoints in scope: `POST /auth/register`, `POST /auth/login`, forgot/reset password, and
`POST /payments/webhooks/razorpay` (no session; authenticated by `x-razorpay-signature` HMAC against
`RAZORPAY_WEBHOOK_SECRET`; idempotent on `x-razorpay-event-id`). Webhook semantics are correct (signature, not session).

### Integrations
| Integration | State | Notes for docs |
|---|---|---|
| Razorpay deposit payments | Implemented; **mode depends on configured keys** (`RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET`) | No keys → "Online payment is unavailable right now. Nothing has been charged." Test vs live: VERIFICATION REQUIRED |
| Email (invites, set-password, reset) | Implemented via `EMAIL_WEBHOOK_URL` (`services/integrations.py:23-29`) | Failure messages exist ("…the email was not delivered…") |
| In-app notifications + daily reminders | Implemented; Celery beat `agn017-daily-reminders` at 02:30 UTC = 08:00 IST | Needs `worker` + `beat` running |
| File storage | S3 or local; PDF/JPEG/PNG; default max 20 MB (`max_upload_bytes`) | Production limit VERIFICATION REQUIRED |
| Audit log | Agency transitions, network drill-down reads (fail-closed), deposit remit/refund, report exports, document verify | Not shown to agencies |
| Throttles | Uploads 500/agency/24 h; document requests 200/24 h; applications 200/24 h; payment attempts 10/deposit/h; CSV 30/user/10 min; invites 10/24 h; staff create/reset 20/24 h | Document as error messages |

---

## 8. Feature-to-Route Mapping

| Doc ID | Route / navigation path | API |
|---|---|---|
| AUTH-001 | `/overseas/login` → "Create an account" → `/overseas/register` | `POST /auth/register` |
| AUTH-002 | `/overseas/login`; sidebar footer → Sign out | `POST /auth/login`, `/auth/logout` |
| AUTH-003 | Any `/overseas/agent/*` page when blocked | any agency API (403 gate) |
| AUTH-004 | Login → "Forgot your password?" → `/overseas/forgot-password`; email link → `/overseas/reset-password` | `POST /auth/forgot-password`, `/auth/reset-password` |
| AUTH-005 | Sidebar footer → Change password → `/account/password` | `POST /auth/change-password` |
| AUTH-006 | Sidebar footer → My profile → `/account/profile` | VERIFICATION REQUIRED |
| DASH-001/002 | Sidebar → Dashboard | `GET …/crm/dashboard` |
| STU-001 | Sidebar → Students (Staff: My Students → All) | `GET …/crm/students` |
| STU-002 | Students → Add student (Staff: My Students → Add) | `POST …/crm/students` |
| STU-003 | Students → card → View → Edit | `GET/PATCH …/crm/students/{id}` |
| STU-004 | Students → card → Archive / Unarchive | `POST …/{id}/archive\|unarchive` |
| STU-005 | Students → card → Assign | `POST …/{id}/assign` |
| STU-006 | Student detail → Counseling → Record counseling | `PUT …/{id}/counseling` |
| STU-007 | Student detail → University shortlist → Add university to shortlist | `…/{id}/shortlist` (4) |
| STU-008 | Student detail → Journey; History → Show history | `GET …/{id}/journey`, `/timeline` |
| STU-009 | Students → Actions → Link student | `POST /workflows/overseas/agent/students` |
| UNI-001 | Sidebar → Universities | `…/crm/universities` (4) |
| APP-001 | Sidebar → Applications → filter sub-link | `GET …/crm/applications` |
| APP-002 | Applications → Create application | `POST …/crm/applications` |
| APP-003 | Applications → card → View → Edit | `PATCH …/applications/{id}` |
| APP-004 | Applications → card → View | `GET …/applications/{id}` |
| APP-005 | Application detail → Change status / Withdraw application | `POST …/{id}/status` |
| APP-006 | Application detail → Offer → Record offer | `PUT …/{id}/offer` |
| APP-007 | Application detail → Deposit → Record deposit / Pay deposit | `PUT …/{id}/deposit`, `POST …/deposit/checkout`, `POST /payments/{id}/verify`, `GET …/deposit/receipt` |
| APP-008 | Application detail → Visa → Start visa case | `POST/PATCH …/{id}/visa` |
| APP-009 | Application detail → Enrollment → Enroll student | `PUT …/{id}/enrollment` |
| DOC-001 | Sidebar → Documents → Pending / Uploaded | `GET …/crm/documents`, `GET /workflows/overseas/documents/{id}/download` |
| DOC-002 | Documents → Upload document | `POST …/crm/documents` |
| DOC-003 | Documents → card → Replace file | `PUT …/documents/{id}/file` |
| DOC-004 | Documents → card → Review | `PATCH /workflows/overseas/documents/{id}/verify` |
| DOC-005 | Documents → card → History | `GET …/documents/{id}/history` |
| DOC-006 | Documents → Request a document; Documents → Additional | `…/document-requests` (3) |
| TASK-001/002 | Sidebar → Tasks & Follow-ups; also student detail → Tasks | `…/crm/tasks` (4) |
| NOTIF-001 | Sidebar → Notifications (badge); top-bar badge | `GET /workflows/notifications`, `/unread-count`, `PATCH /{id}/read` |
| COMM-001 | Sidebar → Commissions | `GET /portal/overseas/agent/commissions`, `POST …/commissions/{id}/claim` |
| RPT-001/002 | Sidebar → Reports → tab → Apply → Download CSV | `GET …/reports/{kind}[.csv]` |
| RPT-003 | Reports → Commission tab | `GET /workflows/overseas/agent/commissions/report[.csv]` |
| TEAM-001..005 | Sidebar → Team | `/workflows/overseas/agent/team/*` |
| PERF-001 | Sidebar → Staff Performance; Dashboard → View staff performance | `GET …/crm/performance` |
| ADM-001 | Overseas Admin sidebar → Agents | `GET /overseas-admin/agent-orgs`, `POST …/{id}/{action}` |
| ADM-002 | Overseas Admin sidebar → Agent network | `GET /overseas-admin/agent-orgs` |
| ADM-003/004 | Agent network → agency name | `GET /overseas-admin/agent-orgs/{id}[/students\|/applications]`, `POST …/suspend\|reinstate` |
| ADM-005 | Overseas Admin sidebar → Agent deposits | `/overseas-admin/deposits` (3) |
| ADM-006 | Overseas Admin sidebar → Commissions | `PATCH /workflows/overseas/agent/commissions/{id}`, `POST /overseas-admin/commissions/{id}/approve-payout` |
| ADM-007 | Super Admin types `/overseas/admin/agent-network`, `/agent-network/{id}`, `/agent-deposits` (others: Workspace not found) | as above |
| ADM-008 | Admin → Users (role agent) → resend link | `admin.py:218,544` — VERIFICATION REQUIRED |

---

## 9. Major User Workflows

1. **Agency onboarding:** visitor registers (AUTH-001) → sees "pending approval" (AUTH-003) → Overseas Admin approves
   (ADM-001) → Master signs in (AUTH-002) → dashboard (DASH-001).
2. **Building the team:** Master creates staff (TEAM-002) → staff receive "Set your password" email (AUTH-004) →
   Master sets permissions (TEAM-004) → Master assigns students (STU-005) → Master reviews activity/performance
   (TEAM-005, PERF-001).
3. **Student to application (the core pipeline):** add student (STU-002) → counseling (STU-006) → shortlist (STU-007)
   → documents (DOC-002, DOC-006) → create application (APP-002) → move stages (APP-005) → record offer (APP-006) →
   deposit (APP-007) → visa case (APP-008) → confirm enrollment (APP-009) → journey shows every step (STU-008).
4. **Document control:** upload (DOC-002) → review: Staff verify (with permission) or Master verify/reject/request
   changes (DOC-004) → replace file after rejection (DOC-003) → history (DOC-005).
5. **Deposit money flow:** agency records terms and pays through Razorpay (APP-007) → Overseas Admin records
   remittance to the university or a refund (ADM-005) → agency sees Remitted/Refunded.
6. **Commission flow:** Master confirms enrollment → system creates an *estimated* commission (APP-009) → Overseas
   Admin sets the amount → *eligible* (ADM-006) → Master claims (COMM-001) → a different Overseas Admin approves
   payout → *paid* (ADM-006) → commission report (RPT-003).
7. **Daily follow-up:** notifications and 08:00 IST deadline/overdue reminders (NOTIF-001) → tasks (TASK-001/002).
8. **Agency governance:** Overseas Admin monitors (ADM-002/003), suspends (ADM-004) → every member sees "Your agency's
   account is suspended" (AUTH-003) → reinstate.

---

## 10. Required Screenshots

Estimated **~180 screenshots** (per-feature counts in `docs/documentation-plan.md`). By module:

| Module | Est. | Key states |
|---|---|---|
| AUTH | 18 | register (agent selected), duplicate email, pending card, suspended card, login errors, reset flow, change password |
| DASH | 4 | Master with data, Staff, empty agency |
| STU | 28 | Master vs Staff list, add form + validation + duplicate warning, detail, assign, counseling, shortlist, journey/history |
| UNI | 5 | Master list, Staff view, add form, in-use error |
| APP | 37 | each filter view, create, edit, detail, withdraw confirm, offer, deposit states incl. Razorpay test checkout, visa stages + gate error, enrollment confirm |
| DOC | 16 | pending/uploaded/additional views, upload form, file-type error, Master review vs Staff verify, history |
| TASK | 6 | open, overdue badge, form with past-time hint, cancel confirm |
| NOTIF | 3 | unread list, badge, empty |
| COMM | 2 | table, claim success |
| RPT | 11 | 7 tabs + commission tab, filters, Staff view, no-permission card |
| TEAM | 15 | team list, invite, limit reached, staff list badges, permissions form, activity |
| PERF | 4 | default, filtered, single-staff funnel, Staff refusal |
| ADM | 29 | approval tabs, suspend confirm, network list, detail with two currencies, drill-down tabs, deposit forms, commission forms, Super Admin read-only views |

Screenshot rules that this codebase makes non-trivial:
- **The login page shows the demo password in plain text** when `ENVIRONMENT` is not `production`
  (`apps/web/app/overseas/login/page.tsx:12`). Login screenshots must use Playwright `mask` on that box or run the web
  container with `ENVIRONMENT=production`. Never type real passwords into captured fields (mask password inputs).
- Use 1440 × 900, light theme, the stack at `e376c25c`, and test personas only (`*@edusphere.local` / test domains).
- Dates and "as of" timestamps change every run; capture once per session and note the capture date in the index.

---

## 11. Required Test Data

Environment (the owner starts Docker themselves): `docker compose up -d --build` from the repo root at `e376c25c`
(services `postgres`, `redis`, `api` :8000, `worker`, `beat`, `web` :3000), then
`docker compose exec api python -m app.seed`. Passwords are defined in `apps/api/app/seed.py:14` and are **never**
written into documentation.

**Seeded already:** `superadmin@edusphere.local` (SA), `overseasadmin@edusphere.local` (OA),
`agent@edusphere.local` (active Master of "EduSphere Partner Agency"), `student.overseas@edusphere.local` (linked
student with a login), `counselor@edusphere.local`. Seeded agent records: 1 legacy application (`university_review`),
1 commission INR 15,000 `eligible`, 3 documents (2 verified, 1 pending), 1 visa case `not_started`.

**Must be created (through the UI where it is itself a documented workflow):**
| # | Data | Created in | Needed by |
|---|---|---|---|
| 1 | Pending, rejected, suspended agencies (+ a second active agency) | AUTH-001 + ADM-001 | AUTH-003, ADM-001..004 |
| 2 | Staff A (no permissions), Staff B (*Verify documents*), Staff C (*View reports*), one deactivated staff | TEAM-002..004 | Staff views of every module |
| 3 | A second Master (invite) | TEAM-001 | TEAM-001, 3-Master limit |
| 4 | No-login students, some assigned to A/B, one archived; >20 students for paging | STU-002/004/005 | STU, pagination |
| 5 | Agency universities; shortlist entries | UNI-001, STU-007 | UNI, STU-007 |
| 6 | Applications in every filter group incl. withdrawn; deadlines today / tomorrow / in 3 days | APP-002/005 | APP-001, NOTIF reminders |
| 7 | Offer (conditional with offer letter) | APP-006, DOC-002 | APP-006 |
| 8 | Deposits: not required, awaiting payment, **paid**, remitted, refunded | APP-007, ADM-005 | APP-007, ADM-005 — **paid needs Razorpay test keys** |
| 9 | Visa case through to a decision; a checklist gate failure | APP-008 | APP-008 |
| 10 | Enrolled application → estimated commission; eligible, claimed, paid commissions | APP-009, ADM-006, COMM-001 | COMM, RPT-003 — **second Overseas Admin needed** for payout of manual commissions |
| 11 | Documents: pending, verified, rejected (reason), changes required; open + cancelled request | DOC-002/004/006 | DOC |
| 12 | Tasks: open, overdue, done, cancelled | TASK-002 | TASK |
| 13 | Notifications incl. daily reminders | automatic | NOTIF — reminder job runs 08:00 IST; triggering it on demand: VERIFICATION REQUIRED (owner approval needed) |

Missing accounts that the owner must approve creating: a **second Overseas Admin** (for commission payout
separation) and the Staff/agency personas above.

---

## 12. Unknown Workflows Requiring Browser Verification

### 12.1 Cannot be confirmed from code
| # | Item | Feature |
|---|---|---|
| U1 | What `/account/profile` shows and allows for agents | AUTH-006 |
| U2 | Whether a pending/suspended agent can open `/account/password` | AUTH-005 |
| U3 | Deactivated staff: "Invalid credentials" at sign-in vs "Your Master account is deactivated" card | AUTH-003 |
| U4 | Exact validation text on the register form (browser `required`/`type=email` may fire first) | AUTH-001 |
| U5 | Visual layout of dashboard tiles; empty text of the open-applications table | DASH |
| U6 | Network-error wording of the student form (`NOT_COMPLETED` constant) | STU-002 |
| U7 | Shortlist: is the same university refused twice for one student? | STU-007 |
| U8 | Linked-student picker search behaviour (min characters) | APP-002 |
| U9 | Razorpay test checkout, webhook timing, receipt PDF | APP-007 |
| U10 | Whether students with a login are told about document requests | DOC-006 |
| U11 | Documents page has no student filter control (API supports one) | DOC-001 |
| U12 | When the Staff sidebar picks up a changed *View reports* permission on an open page | TEAM-004 |
| U13 | Team page shows Masters twice (portal table + Actions card) — how it looks | TEAM-001 |
| U14 | Daily reminders actually fire in the test stack; local time format | NOTIF-001 |
| U15 | Super Admin rendering of `/overseas/admin/agents` and `/commissions` (table only?) | ADM-007 |
| U16 | Whether `/overseas/admin/applications` includes agency applications | ADM-007 |
| U17 | Resend welcome link from `/admin/users?role=agent` | ADM-008 |
| U18 | Commission "claim" form asks for the raw commission id; table shows raw status values | COMM-001 |
| U19 | Mobile card layouts (`data-label`) for network tables — only if responsive docs are wanted | ADM-002 |

### 12.2 As-built behaviour the product owner should know about (documented as-is, not changed)
1. A **rejected** agency sees the same text as a pending one ("Agent registration is pending approval"); no reason is shown.
2. (Corrected in S11) Deactivated staff are refused at sign-in ("Invalid credentials") or, if signed in, told "Your account was deactivated by your agency…"; the "Your Master account is deactivated" card is effectively unreachable.
3. Agencies get **no email or notification** when approved, rejected or suspended.
4. Super Admin: the Agents and Commissions pages are unavailable (Workspace not found) and the network detail hides Suspend, but the **API accepts the actions** (`admin.py:1147`, `workflows.py:120`).
5. `POST /workflows/overseas/agent/commissions` (manual commission create) has **no UI**.
6. (Corrected in S11 — not an issue) The agency dashboard shows each currency separately (`lib/agentDashboard.ts` formatMoney).
11. (Found in S11) A Master can claim an **estimated** commission (amount 0); the claim locks the amount (`workflows.py:2574`, `:2620`), so a ₹0 payout can be approved.
7. Commission CSV export is not audited or throttled, unlike other report exports.
8. Students "Assigned to" filter offers only Anyone/Unassigned in the UI.
9. "All applications" excludes withdrawn applications (only the Withdrawn filter shows them).
10. A task's "Assigned to" is the student's assignee; tasks have no assignee of their own.

These go into the review report and are raised with the owner; user docs describe them neutrally where users meet them.
