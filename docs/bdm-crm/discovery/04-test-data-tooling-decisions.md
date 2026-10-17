# 04 — Test data, capture tooling and decisions (BDM CRM, Overseas: Agent BDM, School BDM, BDM Manager)

> Evidence appendix for `docs/bdm-crm/documentation-analysis.md`. Read-only S1 discovery, 2026-10-17, main @ `6fee294d`.
> Nothing outside this file was changed. No docker or server was run. Seed and e2e passwords are **not** copied here: the
> seeded-account password is called "the seed password (DOCS_PASSWORD)" (the `PASSWORD` constant in `apps/api/app/seed.py`); the e2e
> password is the `E2E_PASSWORD` constant in `apps/web/tests/e2e/helpers/welcome.ts`.

Classification: every row is **as built in code on main @ 6fee294d** unless marked otherwise. Owner answers are cited by their
DEC-SCOPE code. The backlog's D1–D32 are `EXPLICIT_APPROVAL` (registered as `DEC-SCOPE-055`). **College BDM is out of scope** for
this manual; College rows below are listed only where they leak into Overseas screens.

---

## 1. Seed data

### 1.1 BDM demo accounts (`apps/api/app/seed.py` L861–871; `user()` helper L45–52)

`user()` gives every account the seed password (DOCS_PASSWORD) and `profile={"demo": true}`; accounts and profiles are created only
when missing, so re-seeding is idempotent. Profiles carry designation "Business Development Manager", department "Business
Development".

| Email | Name | Role | `bdm_type` | Division | Employee ID | Territory | Reports to | In scope |
|---|---|---|---|---|---|---|---|---|
| `bdm.manager@edusphere.local` | Sanjay BDM Manager | `bdm_manager` | — (no profile row, B6) | `global` | — | — | — | Yes (manager) |
| `bdm.agent@edusphere.local` | Rahul Agent BDM | `bdm` | `agent` | `overseas` | BDM-DEMO-001 | Hyderabad | Sanjay | **Yes** |
| `bdm.school@edusphere.local` | Kavya School BDM | `bdm` | `school` | `overseas` | BDM-DEMO-002 | Bengaluru | Sanjay | **Yes** |
| `bdm.college@edusphere.local` | Vivek College BDM | `bdm` | `college` | **`it`** | BDM-DEMO-003 | Chennai | Sanjay | No — but he is on Sanjay's team, so he appears on every Sanjay manager screen and in super-admin performance tables |

Other seeded accounts the Overseas BDM manual needs (`USERS` seed.py L17–29; L861–879):

| Email | Name | Role | Why it matters |
|---|---|---|---|
| `superadmin@edusphere.local` | Global Super Admin | `super_admin` | Only role that creates BDM managers (D10); creates any BDM; travel-approval fallback `/admin/bdm-travel-approvals` (T3/T8); reads all teams; BDM Performance / Master View; restores, reassigns; lifecycle (bdm-025) |
| `overseasadmin@edusphere.local` | Overseas Administrator | `overseas_admin` | Creates/edits/deactivates **Agent and School** BDMs at `/overseas/admin/bdms` (D10); resolves School and Agent onboarding requests (bdm-018/019); converts BDM leads (bdm-017 L1). **No access** to BDM organizations (C7) |
| `telecaller.overseas@edusphere.local` | Imran Overseas Telecaller | `telecaller` (overseas) | Files "Agent meeting" / "School meeting" requests to BDMs (tel-019) |
| `student.overseas@edusphere.local` | Ananya Sharma | `overseas_student` | The only seeded Overseas student — target for a BDM-lead conversion link (bdm-017 L2; one lead per student, L9) |
| `agent@edusphere.local` | Global Admissions Agent | `agent` (Master of "EduSphere Partner Agency", status **active**, seed.py L124–142) | Existing agency that Overseas Admin can **link** to a BDM Agent organization (bdm-019 A1) → live Agent stages + agent-performance panel show real seeded figures |
| `itadmin@edusphere.local` | IT Division Administrator | `it_admin` | Creates College BDMs only — out of scope |

### 1.2 Seeded BDM business data

| Data | Seeded? | Notes |
|---|---|---|
| BDM organizations, contacts, pipeline events | **No** | `seed.py` never touches `BdmOrganization*`; codes `ORG-000001…` start from the sequence |
| Appointments, meeting reports, tasks/follow-ups, activities | **No** | |
| Trips, expenses | **No** | |
| MoUs | **No** | |
| Daily reports, targets | **No** | |
| Meeting requests (tel-019) | **No** | |
| Onboarding requests | **No** | |
| Partner records usable by links | **Yes** | School "Sunrise Public School" (Hyderabad, Telangana, tier **platinum**, `tier_valid_until` = seed date + 365, random `school_code`, seed.py L643–650) with seeded school students, career/psychometric/test-prep records (L780–830) → bdm-020 School activity panel and bdm-016 "Active Schools" have real numbers once linked. Agency "EduSphere Partner Agency" (active) → bdm-019/022 panels |
| Seeded BDM profiles' age | — | Profiles get `created_at` = seed time. On a stack seeded the same day, bdm-023 **AL-7 "Daily report not submitted"** lists nobody (R6: a BDM whose profile is newer than yesterday is not listed) and the team daily-report grid shows "—" for earlier days (bdm-015 R8) |

**Consequence:** every BDM screen is empty on a fresh seed. All data must be created by the capture specs, in the dependency order of §7.

---

## 2. Capture tooling — reuse the telecaller analysis

The shared tooling is already documented in
`origin/docs/telecaller-crm-user-guide:docs/telecaller-crm/discovery/04-test-data-tooling-decisions.md` **§2.1–§2.5**
(`playwright.docs.config.ts` settings, `shoot.ts` exports, the school spec pattern, `check-doc-links.mjs`, the docs-stack recipe).
Those findings hold on main @ 6fee294d (`shoot.ts` is unchanged on both branches: only `SCHOOL_ROOT`; `signIn` hard-codes
`/overseas/login`). Only the BDM-specific deltas follow.

### 2.1 BDM-specific deltas

| Item | Needed for BDM | Why / evidence |
|---|---|---|
| `shoot.ts` root | Add `export const BDM_ROOT = path.resolve(__dirname, "../../../../docs/bdm-crm/screenshots")`; pass `{ root: BDM_ROOT }` | Default root is the Agent CRM set. The telecaller effort also has to add `TELECALLER_ROOT` → **same 3 lines of `shoot.ts` touched by both branches; merge whichever lands second** |
| `signIn` portal | Agent/School BDMs: `signIn(page, email, kind, /\/bdm\/my-day/)` works as-is (`/overseas/login`, B9). **BDM manager must use `/admin/login`** → landing `/bdm/manager/dashboard` (B1; e2e `waitForURL("**/bdm/manager/dashboard")`). Super admin: `/admin/login` → `/admin`. Overseas Admin: `/overseas/login` → `/overseas/admin/dashboard`. Overseas telecaller: `/overseas/login` → `/telecaller/dashboard` | Add a `portal` parameter (`"overseas" | "it" | "admin"`) to `signIn`, or an `adminSignIn` helper — same change the telecaller set needs; coordinate one implementation |
| Login form selectors | `#login-email`, `#login-password`, button "Sign in securely" | All BDM e2e specs |
| Signed-out chooser | `/bdm/sign-in` ("College BDM" → `/it/login?next=…`, Agent/School → `/overseas/login`); signed-out `/bdm/manager/*` → `/admin/login?next=…` | bdm-001 B9; e2e bdm-001 L63–65 |
| Set-password links | Admin-created accounts get a 72-hour link `FRONTEND_URL/<segment>/reset-password?token=…`; segment `admin` for `bdm_manager`, `overseas` for Agent/School BDMs (`services/provisioning.py` L66–75). In `ENVIRONMENT=development` `POST /admin/users` also returns `development_welcome_token` | `mailLink()`'s default pattern matches both; or activate with the token (e2e `activateWithToken`) |
| Hand-off file | `DOCS_BDM_FILE` (JSON: account emails/ids, `ORG-…`, `APT-…`, `TRV-…`, MoU ids, `MRQ-…` codes) | Mirrors `DOCS_SCHOOL_FILE` / `DOCS_TEL_FILE` |
| Spec folder | `apps/web/tests/doc-capture/bdm/bdm-sN-*.capture.ts` | Mirrors `school/sch-sN-*` |
| Link check | `node docs/tooling/check-doc-links.mjs docs/bdm-crm` → manual must use `user-manual/`, `admin-manual/`, `role-guides/`, `faq.md`, `troubleshooting.md`, `screenshot-index.md` | telecaller §2.4 |
| Test files | One small **PDF** (MoU document) and optionally one **PNG/JPEG**; written to `os.tmpdir()` by the spec | §6 |

### 2.2 `bdmdocs` stack

Recipe = telecaller §2.5 with these values:

| Item | Value | Why |
|---|---|---|
| Worktree | `.claude/worktrees/bdm-docs` (main @ 6fee294d) | |
| Project | `docker compose -p bdmdocs -f docker-compose.yml -f docker-compose.docs.yml up -d --build` | Never without the Mailpit file; never the Caddy override |
| `docker-compose.docs.yml` (untracked) | `mailpit` ports `127.0.0.1:8028:8025` | 8025 agentdocs, 8026 schooldocs, 8027 teldocs |
| `.env` (untracked copy) | `WEB_PORT=3040`, `API_PORT=8040`, `FRONTEND_URL=http://localhost:3040`, `ENVIRONMENT=development`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, empty SMTP user/password, `SMTP_FROM_EMAIL=no-reply@edusphere.local`, `EMAIL_WEBHOOK_URL=` empty | `send_bdm_reminder_email` returns `not_configured` without `SMTP_HOST` **and** `SMTP_FROM_EMAIL` (`services/mailer.py` L371); welcome links must point at :3040 |
| Seed | `docker compose -p bdmdocs … exec api python -m app.seed` | |
| Capture env | `DOCS_BASE_URL=http://localhost:3040`, `DOCS_MAILPIT_URL=http://localhost:8028`, `DOCS_PASSWORD`, random `DOCS_TEST_PASSWORD`, `DOCS_BDM_FILE` | Session scratchpad only |
| **Worker** | must run | Welcome / set-password emails and reminder emails go through the ENH-014 delivery queue |
| **Beat** | must run | `bdm012-reminders` every **300 s** → `send_bdm_reminders_task` (`worker.py` L220). Without beat there are no "Appointment reminder", "Appointment in 1 hour", "Travel reminder", "Follow-up due today"/"Task due today", "MoU follow-up", "MoU renewal due" notifications or emails |
| Lifecycle | User controls docker (memory): start / seed / reset need the user's OK | |

---

## 3. Existing BDM tests

### 3.1 Web e2e specs (`apps/web/tests/e2e/`, 27 files, 2 885 lines)

All create **throwaway accounts through the real admin API** (super admin signs in at `/admin/login`, `POST /api/v1/admin/users`,
then `activateWithToken`), then mix API data set-up with UI steps. Useful as recipes; none uses the seeded BDMs except tel-019's
routing check.

| Spec | Lines | Flow worth reusing for capture |
|---|---|---|
| bdm-001-bdm-profile | 132 | Create manager + BDM; sign-in chooser; manager forgot-password inside `/admin`; `/bdm/profile` |
| bdm-002-organization-crm | 127 | Create organization in the UI (`?created=1`), contacts, duplicate warning, archive / restore, manager reassign |
| bdm-003-type-profiles | 106 | Agent / School profile fields; type change refused while profile data exists |
| bdm-004-pipeline | 98 | Stage moves, backward note, Lost + Revive, stage history |
| bdm-005-mou | 125 | MoU create / status moves / document upload / Signed advances pipeline / Expired |
| bdm-006-appointments | 103 | Book (`/bdm/appointments/new?organization=…`), confirm, reschedule, cancel; overlap warning |
| bdm-007-meeting-reports | 94 | Complete with outcome + meeting report; follow-up created |
| bdm-008-follow-ups | 87 | Manual follow-up / task, complete, cancel with reason; tabs |
| bdm-009-activities | 94 | Log call / WhatsApp / visit; day view; same-day edit/delete |
| bdm-010-travel | 192 | Draft → submit → manager approve → start → expenses → complete; reject → edit → resubmit |
| bdm-011-trip-itinerary | 105 | Link appointments to a trip; itinerary; travel report |
| bdm-012-reminders | 109 | **Real beat + worker**: book ~30 min ahead, wait for "Appointment in 1 hour" (timeout 480 s); deep links open dialogs |
| bdm-013-calendar | 90 | Day / week views (`/bdm/calendar?view=day&date=…`) |
| bdm-014-my-day | 112 | My Day tiles per type |
| bdm-015-daily-report | 95 | Submit report; manager grid + comment |
| bdm-016-targets | 96 | Manager sets targets (`PUT /bdm/manager/targets`), copy last month; BDM sees on My Day |
| bdm-017-lead-attribution | 92 | BDM adds lead; admin conversion link (`POST /admin/leads/{id}/conversion`) |
| bdm-018-school-handover | 95 | Request onboarding → Overseas Admin creates School (`POST /overseas-admin/schools` with `bdm_onboarding_request_id`) or links |
| bdm-019-agent-handover | 101 | Signed MoU → Request onboarding → Overseas Admin registers + approves agency → link by code (`…/link-agent`) |
| bdm-020-school-activity | 93 | Linked school → School activity panel |
| bdm-021-college-business | 96 | College only — skip |
| bdm-022-agent-performance | 111 | Linked agency → Agent performance panel |
| bdm-023-manager-dashboard | 100 | Tiles + alerts |
| bdm-024-performance | 115 | Performance by type → BDM → org; master view |
| bdm-025-deactivation | 105 | Deactivate with reassign / leave; hand over; manager deactivate |
| mgmt-020-bdm-dashboards | 71 | Management Command Center `/management/bdm` (partner / super admin) — cross-reference only |
| tel-019-meeting-requests | 141 | Telecaller files a request (`/telecaller/meeting-requests?filed=MRQ-…`); School BDM accepts; College BDM sees "College"/"Corporate" |

### 3.2 API test helpers (`apps/api/tests/bdm0NN_helpers.py`)

| File | Helpers | Note for capture |
|---|---|---|
| bdm001 | `make_user make_manager login bdm_payload create_bdm` | Payload shape for `POST /admin/users` |
| bdm002 / 003 | `make_bdm org_payload create_org` / `profile_org` | Organization + profile payloads |
| bdm004 / 005 | `move events` / `mou_url start change` | |
| bdm006 | `future appt_payload create_appt bdm_with_org move_to_past` | **`move_to_past` edits the DB directly** — not available to a browser capture; see §6.3 |
| bdm007–011 | `completed`, `create_task`, `add_activity`, `trip_body make_trip act`, `bdm_trip linked` | |
| bdm012 | `world appointment trip task mou run reminders deliveries` | Runs the reminder job in-process |
| bdm015 / 016 | `submit_url team_report_url …` / `school school_student career psychometric converted_lead enroll placement` | |
| bdm017–019 | `add_lead conversion` / `school_world pending_request` / `agent_world link_agent` | |
| bdm024 / 025 | `backdate_org …` / `deactivate history` | `backdate_*` also writes the DB directly |

### 3.3 API routes for data creation (all under `/api/v1`)

| Area | Endpoints |
|---|---|
| Provisioning | `POST /admin/users` (`role: bdm` + `bdm_profile{bdm_type, employee_id, reporting_manager_user_id, designation?, department?, territory?}` — no mobile column on `bdm_profiles` (B8 lists Mobile; `NEEDS_CONFIRMATION` where the create form takes it); `role: bdm_manager`, `division: global`, super admin only), `PATCH /admin/users/{id}`, `GET /admin/bdms?q=`, `GET /admin/bdm-managers?q=` |
| Lifecycle (bdm-025) | `GET /admin/bdms/{id}/portfolio`, `POST /admin/bdms/{id}/deactivate {mode: reassign\|leave, reassign_to}`, `POST /admin/bdms/{id}/handover {reassign_to}`, `POST /admin/bdm-managers/{id}/deactivate {reassign_to}` |
| Self / team | `GET /bdm/me`, `GET /bdm/manager/team?bdm_type=&q=` |
| Organizations | `GET/POST /bdm/organizations` (create needs `org_type`, `name`, `city`, `contacts[≥1, ≤20]`; duplicate → 409 `possible_duplicate`, resend acknowledged), `GET/PATCH /bdm/organizations/{id}` (`address`, `profile{…}`), `POST /{id}/archive\|restore\|assign`, `POST /{id}/contacts`, `PATCH/DELETE /{id}/contacts/{cid}` |
| Pipeline | `POST /bdm/organizations/{id}/stage {from_stage, to_stage, note?}`, `POST /{id}/lost {reason}`, `POST /{id}/revive {reason}`, `GET /{id}/stage-history`, `GET /bdm/pipeline` |
| MoU | `GET/POST/PATCH /bdm/organizations/{id}/mou`, `PUT /bdm/organizations/{id}/mou/document` (multipart `file`), `GET /bdm/mous`, `GET /bdm/mous/{id}/history`, `GET /bdm/mous/{id}/document` |
| Appointments | `GET/POST /bdm/appointments` (`organization_id, contact_id, starts_at, duration_minutes 15–720, appointment_type, location?, purpose?, remarks?, expected_leads?, expected_revenue?, trip_id?, confirm_overlap`), `GET/PATCH /{id}`, `POST /{id}/confirm\|reschedule\|cancel\|no-show\|complete`, `PATCH /{id}/report` |
| Follow-ups / tasks | `GET/POST /bdm/tasks`, `PATCH /bdm/tasks/{id}`, `POST /{id}/complete`, `POST /{id}/cancel` |
| Activities | `GET/POST /bdm/activities`, `PATCH/DELETE /bdm/activities/{id}`, `GET /bdm/organizations/{id}/activities`, `GET /bdm/manager/activities` |
| Leads | `GET/POST /bdm/organizations/{id}/leads`; admin `POST /admin/leads/{id}/conversion` |
| Travel | `GET/POST /bdm/trips`, `GET/PATCH /bdm/trips/{id}`, `POST /bdm/trips/{id}/submit\|withdraw\|start\|complete\|cancel`, `POST/PATCH/DELETE /bdm/trips/{id}/expenses[/{eid}]`, `GET /bdm/trips/{id}/report`; manager `GET /bdm/manager/trips`, `GET /bdm/manager/approvals`, `GET /bdm/manager/trips/{id}[/report]`, `POST /bdm/manager/trips/{id}/approve\|reject` |
| Calendar / My Day | `GET /bdm/calendar?date_from&date_to[&bdm_user_id]`, `GET /bdm/my-day` |
| Daily report | `GET /bdm/daily-reports/{date}`, `POST /bdm/daily-reports/{date}/submit`; manager `GET /bdm/manager/daily-reports`, `GET /bdm/manager/daily-reports/{bdm}/{date}`, `PUT …/comment` |
| Targets | `GET /bdm/targets`, `GET /bdm/manager/targets[/{bdm}]`, `PUT /bdm/manager/targets`, `POST /bdm/manager/targets/copy` |
| Onboarding | `POST /bdm/organizations/{id}/onboarding-request`; Overseas Admin `GET /overseas-admin/bdm-onboarding-requests?kind=`, `POST …/{rid}/reject`, `POST …/{rid}/link` (School ID), `POST …/{rid}/link-agent` (agency code), School create `POST /overseas-admin/schools` with `bdm_onboarding_request_id` |
| Panels | `GET /bdm/organizations/{id}/school-activity`, `GET /bdm/organizations/{id}/agent-performance` (`/business` is College) |
| Manager views | `GET /bdm/manager/dashboard`, `GET /bdm/manager/performance`, `GET /bdm/manager/performance/bdms/{id}`, `GET /bdm/manager/hierarchy` |
| Meeting requests | Telecaller `GET /telecaller/meeting-requests/options`, `POST /telecaller/meeting-requests`, `GET /telecaller/meeting-requests`; BDM `GET /bdm/meeting-requests[/{id}]`, `POST /{id}/accept` (body = an appointment create), `POST /{id}/decline {reason}` |

### 3.4 Web routes (screen inventory)

| Role | Routes |
|---|---|
| BDM (nav order, `BDM_NAV`) | My Day `/bdm/my-day` · Calendar `/bdm/calendar` · Organizations `/bdm/organizations` (`/new`, `/[id]`) · Pipeline `/bdm/pipeline` · MoUs `/bdm/mous` · Appointments `/bdm/appointments` (`/new`, `/[id]`) · Follow-ups `/bdm/follow-ups` · Requests `/bdm/meeting-requests` (`/[id]`) · Activities `/bdm/activities` · Daily report `/bdm/daily-report` · Travel `/bdm/travel` (`/new`, `/[id]`, `/[id]/report`) · Profile `/bdm/profile` · Notifications `/bdm/notifications` · `/bdm/universities/[id]` (upc-004 link) |
| BDM Manager (`BDM_MANAGER_NAV`) | Dashboard · Performance (`/[type]`, `/bdms/[id]`) · Master view `/bdm/manager/hierarchy` · Team · Organizations (`/[id]`) · Pipeline · MoUs · Appointments (`/[id]`) · Requests · Follow-ups · Calendar · Activities · Daily reports (`/[bdmId]`) · Targets (`/[bdmId]`) · Approvals · trips `/bdm/manager/trips/[id]` (`/report`) · Notifications |
| Super admin | `/admin/bdms`, `/admin/bdm-travel-approvals`, `/bdm/manager/dashboard`, `/bdm/manager/performance` ("BDM Performance"), `/bdm/manager/hierarchy` ("BDM Master View"), `/management/bdm` (mgmt-020) |
| Overseas Admin | `/overseas/admin/bdms`, `/overseas/admin/schools` (School onboarding requests), `/overseas/admin/agents` ("Agent onboarding requests" region), admin lead list (conversion) |
| Telecaller | `/telecaller/meeting-requests` ("BDM requests") |

---

## 4. Decisions and backlog (`docs/delivery/BDM_CRM_BACKLOG.md` bdm-001…025; `docs/decisions/PRODUCT_DECISION_REGISTER.md`)

All 25 items are **merged on main** (PR merges in `git log main`; migrations `0061…0098` present). "Overseas" = relevance for Agent
/ School BDMs and the manager.

| Item | Title | DEC-SCOPE | Merged | Key owner answers (short) | Overseas |
|---|---|---|---|---|---|
| bdm-001 | Roles, BDM profile, provisioning | 055 | PR #45 | One `bdm` role + type; division derived; super admin creates managers, Overseas Admin Agent/School BDMs (D10); manager signs in at `/admin` (B1); type fixed (B7); required type + Employee ID + manager (B8); picker shows manager email (B10); manager password reset inside `/admin` (B11) | Yes |
| bdm-002 | Organization CRM core | 060 | PR #50 | ≥1 contact, last can't be deleted (C1); manager reads team + reassigns same type (C2); any of 7 types, owned by creator's type (C3); `ORG-000123` (C4); archive by BDM, restore by manager/super admin (C5); no Overseas/IT Admin access (C7); duplicate warns incl. archived (C8); Name + City required (C13); archived read-only (C15) | Yes |
| bdm-003 | Type-specific profiles | 065 | PR #55 | Profile follows `org_type` (university → College fields) (P1); address for all (P3); type change 409 while old profile has data (P4); grades Nursery–12 (P7); commission placeholder only (P10) | Yes |
| bdm-004 | Pipelines + stage history | 071 | PR #62 | Assigned BDM + super admin move; manager read-only (S1); live stages 422 "Awaiting handover" (S3); Agent status derived (S4); Lost = flag + reason, revive returns to stage (S5); backward needs note, stale → 409 (S6) | Yes |
| bdm-005 | MoU tracking | 078 | PR #77 | All types (M1); free moves, Expired derived (M2); PDF/JPEG/PNG one current file (M4); Signed advances pipeline forward-only (M5); renewal = new row when Expired/Rejected (M6); 20 uploads/h (M8); Expired accepts corrections not status (M9) | Yes |
| bdm-006 | Appointments | 068 | PR #58 | Transitions + terminal states; complete/no-show only after start; cancel/no-show need reason (A2); only assigned BDM manages (A3); archived org blocks new (A4); overlap 409 confirmable (A6); future start (A7); Agent outcome list vs common list (A8) | Yes |
| bdm-007 | Outcome + meeting report | 070 | PR #60 | One follow-up per appointment (R1); author edits same IST day (R2); "Reschedule" → "Book the next meeting" (R4); outcome + discussion required (R6) | Yes |
| bdm-008 | Follow-ups and tasks | 075 | PR #71 | Report follow-ups complete-only (F2); manual items due today or later, cancel needs reason (F3); manager reads (F4); archive cancels open items (F6); 200/day | Yes |
| bdm-009 | Activity log | 069 | PR #59 | Assigned BDM logs (V1); 6 channels (V2); ≤7 IST days back, edit/delete same day only (V4); direction for call/WhatsApp/email (V6); hard delete (V8); 200/day (V10) | Yes |
| bdm-010 | Travel requests, approval, expenses | 063 | PR #53 | One From/To per trip (T1); manager resolved at decision time (T2); super admin only while manager inactive (T3/T8); expenses only once approved (T5); `TRV-000123` (T6); **no receipt upload** (T7); withdraw / resubmit (T9); travel date ≤30 days back, ≤31-day trip, start/complete from travel date (T14); Notifications nav (T15) | Yes |
| bdm-011 | Trip ↔ appointment, itinerary, report | 092 | PR #89 | Actual leads from completed linked meetings (L1); link only open appointments to own planned trip (L2); expected leads/revenue = BDM estimates (D16); actual revenue "Not tracked yet" | Yes |
| bdm-012 | Reminder engine | 102 | PR #116 | dedupe key; beat 300 s; times IST (R3); same-day catch-up (R4); owner at fire time, never managers (R6); in-app + email (R8); deep links never change data (R10) | Yes |
| bdm-013 | Calendar | 079 | PR #78 | ≤31-day range (K2); manager picks one team BDM (K3); seminars badged (K5); week Mon–Sun (K7) | Yes |
| bdm-014 | My Day + type dashboard | 097 | PR #108 | `bdm` only; manager redirected to dashboard (K10); T-A6 agents awaiting onboarding **not tracked** (K5); MoU follow-ups tile not tracked (K6) | Yes |
| bdm-015 | Daily activity report | 099 | PR #111 | 11 counts per type (R1); submit today or ≤7 days back (R3); submit locks that day's activities (R5); no resubmit (R6); manager comment ≤1000 (R7); team grid 7 days (R8) | Yes |
| bdm-016 | Monthly targets | 103 | PR #117 | Fixed KPI catalogue (Agent 13, School 15) (R1); current + 12 months ahead; past only super admin (R3); 0–100 000 (R4); copy last month (R8) | Yes |
| bdm-017 | Lead attribution + conversion link | 072 | PR #63 | Division admin converts (L1); link to an active student of the division (L2); BDM enters name/email/phone/interest/note (L5); same-email warn per org (L8) | Yes |
| bdm-018 | School onboarding handover | 085 | PR #87 | BDM derived from link (H1); per-step live stages (H2); admin creates or links by School ID (H3); `edusphere_bdm` read-only legacy (H4) | **School** |
| bdm-019 | Agent onboarding handover | 107 | PR #123 | Admin links existing agency by code or rejects (A1); needs Agreement Signed (A2); live stages (A3); commission not shown (A6); in-app notices (A8); unlink out of scope (A10) | **Agent** |
| bdm-020 | School activity tracking | 089 | PR #95 | School module's own figures (A1); profile completion "Not tracked" (A2) | **School** |
| bdm-021 | College business tracking | 086 | PR #88 | College only | **No** |
| bdm-022 | Agent performance drill-down | 110 | PR #128 | Agency funnel counts; revenue not tracked (B5); unlinked "Not onboarded yet" (B7); suspended flagged (B8) | **Agent** |
| bdm-023 | Manager dashboard + alerts | 108 | PR #125 | Manager team / super admin all + manager filter (R1/R2); AL-7 = yesterday (R6); AL-4 ≥5 days (R7); 10 items + "View all" (R8); no target progress (R10) | Yes |
| bdm-024 | Performance + master dashboard | 113 | PR #133 | Period default this month, ≤366 days (P2); current type/manager applies (P3); drill type → BDM → org/trip (P8); master view live (P10); value chains (P11); nav labels (P12) | Yes (College rows visible) |
| bdm-025 | Deactivation, handover, manager change | 082 | PR #79 | Not-started trips cancelled (L2); `mode=leave` keeps work (L3); super-admin bulk move of a manager's BDMs (L4); reactivation = login only | Yes |
| tel-019 | BDM meeting requests | 098 | PR #109 | Name a BDM or the type's pool, first accept wins (MR1); decline reason, final (MR2); manager sees team + pool (MR3); no withdraw (MR4) | Yes |
| upc-004 | BDM university-org link | 124 | PR #158 | University orgs can link to the master university record (UD7–UD10) | Yes (University org type) |
| mgmt-020 | Management BDM figures | 201 | PR #259 | Partner / super admin company-wide figures | Cross-ref only |

### 4.1 Not built — do not document as features

| Topic | Status / source |
|---|---|
| Receipt upload on trip expenses | Not built (T7, owner 2026-10-03) |
| Reimbursement payout, GPS check-in, maps, CSV export, lead import, communication to organization contacts | Not in source (backlog §1 "Not in the source") / D29 |
| External calendar sync | Internal only (D20) |
| Appointment **mode** (Online/Phone/In person) on BDM appointments | No column; only free-text Location. Mode exists on **meeting requests** only |
| Courses Interested as a programme multi-select | Deferred (P9); free text |
| Agent commission on BDM screens | `NEEDS_CONFIRMATION` (P10, bdm-019 A6, bdm-022 B5) |
| Unlinking an onboarded School/Agent | Out of scope (bdm-019 A10) |
| Agents awaiting onboarding tile (T-A6), New / Active agents on targets and daily report | "Not tracked" labels (bdm-014 K5; `bdm_metrics.TARGET_METRICS` and `DAILY_METRICS` still return the "agent onboarding links arrive with the agent onboarding handover" note on main) — document as "Not tracked", not as numbers |
| Agent / School revenue | "Not tracked" (D17) |
| Meeting-request withdraw; telecaller-manager view of requests | MR4 / MR3 |
| Target progress on the manager dashboard | R10 |
| MoU follow-up tasks (`source='mou'`) | Reserved, nothing creates them (K6) |

---

## 5. Product glossary (exact values)

### 5.1 BDM types and organization types

| Key | Label | Where |
|---|---|---|
| `agent` / `school` / `college` | Agent / School / College | `services/bdm.py` `BDM_TYPES`; division `agent`/`school` → `overseas`, `college` → `it` |
| Org types `college university agent school corporate training_institute other` | College, University, Agent, School, Corporate, Training Institute, Other | `BDM_ORG_TYPES`; `lib/bdmOrganizations.ts ORG_TYPE_LABEL` |
| Profile group | agent → Agent fields (Country, Territory, Source, Number of staff); school → School (Board, School type, Lowest grade, Highest grade); college **and university** → College (University / affiliation, College type, Courses); others common only | `BDM_PROFILE_GROUP/FIELDS`; `PROFILE_LABEL` |
| Source | `referral website event cold_call walk_in other` → Referral, Website, Event, Cold call, Walk-in, Other | `SOURCE_LABEL` |
| Board | `CBSE ICSE State IB Other` → CBSE, ICSE, **State board**, IB, Other | `BOARD_LABEL` |
| School type | Private, Government, Aided, International, Other | |
| Grades | −2 Nursery, −1 LKG, 0 UKG, 1–12 | `GRADES` |
| Contact roles | `principal dean hod placement_officer counselor management owner other` → Principal, Dean, HOD, Placement Officer, Counselor, Management, Owner, Other. Suggested first: Agent → Owner; School → Principal, Management, Counselor | `BDM_CONTACT_ROLES`; `CONTACT_ROLE_LABEL`, `SUGGESTED_ROLES` |
| Commission text | "Commission: Available after onboarding" / linked: "Commission: Not shown to BDMs (awaiting a decision)" | `COMMISSION_NOTE` |

### 5.2 Pipelines (`apps/api/app/bdm_stages.py`; manual stages = `BDM_MANUAL_STAGES`)

| # | Agent key → label (kind) | School key → label (kind) |
|---|---|---|
| 1 | `prospect` Agent Prospect (manual) | `prospect` School Prospect (manual) |
| 2 | `contacted` Contacted (manual) | `contacted` Contacted (manual) |
| 3 | `meeting_scheduled` Meeting Scheduled (manual) | `meeting` Meeting (manual) |
| 4 | `meeting_completed` Meeting Completed (manual) | `presentation` Presentation (manual) |
| 5 | `interested` Interested (manual) | `proposal` Proposal (manual) |
| 6 | `proposal_agreement` Proposal / Agreement (manual) | `negotiation` Negotiation (manual) |
| 7 | `agreement_signed` Agreement Signed (manual) | `mou` MoU (manual) |
| 8 | `agent_onboarding` Agent Onboarding (live) | `signed` Signed (manual) |
| 9 | `master_login_created` Master Login Created (live) | `school_onboarding` School Onboarding (live) |
| 10 | `staff_logins_created` Staff Logins Created (live) | `users_created` Teachers / Parents / Students Created (live) |
| 11 | `active_agent` Active Agent (live) | `career_guidance` Career Guidance (live) |
| 12 | `students` Students (volume) | `psychometric` Psychometric (live) |
| 13 | `applications` Applications (volume) | `profile_building` Student Profile Building (live) |
| 14 | `enrollments` Enrollments (volume) | `university_planning` University Planning (live) |

- `BDM_MANUAL_STAGES` — agent: `prospect, contacted, meeting_scheduled, meeting_completed, interested, proposal_agreement, agreement_signed`; school: `prospect, contacted, meeting, presentation, proposal, negotiation, mou, signed`.
- Agent status (derived, S4/A5): Prospect, Contacted, Meeting, Interested, Agreement, Onboarding, Active, Inactive.
- MoU Signed advances to: agent `agreement_signed`, school `signed` (`MOU_SIGNED_STAGE`).
- **Lost reasons: free text** (≤500, line breaks allowed; `BdmPipelineReason`), not an enum; revive also takes a free-text reason. Pipeline event kinds `move lost revived`.

### 5.3 Appointments (`models.py` L3218–3248; `lib/bdmAppointments.ts`)

| Item | Values |
|---|---|
| Statuses | `scheduled` Scheduled, `confirmed` Confirmed, `rescheduled` Rescheduled, `completed` Completed, `cancelled` Cancelled, `no_show` No show. Open = scheduled/confirmed/rescheduled |
| Common types (all BDMs) | College Meeting, Agent Meeting, School Meeting, MoU Discussion, Student / Institution Meeting, Seminar / Workshop, Corporate Meeting, Other |
| + Agent types | New Agent Presentation, Product Training, Agreement Discussion, Performance Review, Agent Onboarding, Agent Visit, Commission Discussion, Business Review |
| + School types | Principal Meeting, Management Meeting, Career Guidance Presentation, Psychometric Presentation, Student Profile Building Presentation, Parent Orientation, Teacher Orientation, Seminar, Workshop, Renewal Meeting |
| Outcomes — Agent BDM | Interested, Agreement Required, Product Training Required, Follow-up, Documents Required, Onboarding Required, Active Business Expected, Not Interested |
| Outcomes — School (and College) BDM | Interested, MoU Discussion Required, Student Leads Expected, Course Promotion Interested, Follow-up Required, Commercial Discussion, Not Interested, Reschedule, Other |
| Meeting report fields | Outcome + Discussion (required); Requirements, Opportunity, Next action, Responsible person (≤200), Next follow-up date (optional) |
| Durations | 15, 30, 45, 60, 90, 120, 180, 240, 360, 480, 720 min (API 15–720) |
| Codes | `APT-000123` (`bdm_appointment_code_seq`) |
| Mode | **None** on BDM appointments (free-text Location only) |

### 5.4 Follow-ups, activities, leads

| Item | Values |
|---|---|
| Task kinds | `follow_up` Follow-up, `task` Task |
| Task sources | `appointment_outcome`, `mou` (reserved), `manual` |
| Task statuses | `open`, `done`, `cancelled` |
| Follow-up tabs | Today, Overdue, Upcoming, Done, Cancelled; counts by the 7 org types + "No organization" |
| Activity channels | Call, WhatsApp, Email, Visit, Meeting, Other |
| Direction (call/WhatsApp/email only) | `outbound` **Outgoing**, `inbound` **Incoming** |
| Lead fields | Student name, Email, Phone (opt), Interest, Note (opt); `source='bdm'` on `enquiries` |

### 5.5 Travel (`models.py` L2877–2932; `lib/bdmTravel.ts`)

| Item | Values |
|---|---|
| Modes | Flight, Train, Bus, Car, Cab, **Local travel** (`local`) |
| Approval status | Draft, Submitted, Approved, Rejected |
| Travel status | Planned, In progress, Completed, Cancelled (in_progress/completed require Approved) |
| Actions | submit, withdraw, start, complete, cancel (BDM); approve, reject + reason (manager) |
| Fields | Travel date, Return date, From, To, Purpose, Mode of travel, Accommodation required, Estimated cost (₹), Remarks |
| Expense categories | Travel, Stay, Food, Local, Other — INR amount > 0, date, optional note (≤500); actual cost = sum |
| Codes | `TRV-000123` |

### 5.6 Daily report, MoU, onboarding, meeting requests, targets

| Item | Values |
|---|---|
| Daily report states | not submitted (live preview) → **submitted** (snapshot, locks that day's activities); manager comment optional; manager grid: Submitted / Missing / "—" |
| Agent daily rows (11) | Calls made, Agents contacted, Meetings, New prospects, New agents (*not tracked*), Agreements, Agent training, Follow-ups, Student leads generated, Applications generated (*not tracked*), Enrollments generated (*not tracked*) |
| School daily rows (11) | Schools contacted, Calls, Meetings, School visits, Presentations, Proposals, MoUs, Follow-ups, Students generated, Career guidance sessions, Psychometric sessions |
| MoU statuses | Prospect, Discussion Started, Proposal Sent, Under Negotiation, Draft Shared, Signed, Active, Expired (derived), Rejected. Signed/Active need signed date; Active needs validity window; valid-until ≥ valid-from. Event kinds `created status updated document renewed` |
| Onboarding requests | kind `school` / `agent`; status `pending` / `completed` / `rejected`; resolution `created` / `linked`. School needs MoU Signed or Active; Agent needs stage Agreement Signed |
| Meeting request types | College, Agent, School, Corporate (Corporate → College BDMs); Overseas manual: **Agent → agent BDMs, School → school BDMs** |
| Meeting request statuses | `pending`, `accepted` (creates an appointment), `declined` (reason, final). Code `MRQ-000123`. Mode: Online, Phone, In person. Proposed time future, ≤1 year |
| Target KPIs — Agent (13) | New Agent Leads, Agent Meetings, New Agents (*nt*), Agreements Signed, Active Agents (*nt*), Agent Students (*nt*), Applications (*nt*), Enrollments (*nt*), College Meetings, New Colleges, Appointments, MoUs, Student Leads |
| Target KPIs — School (15) | Schools Contacted, School Meetings, Presentations, Proposals, MoUs, Active Schools, Students Onboarded, Career Guidance, Psychometric Tests, College Meetings, Agent Meetings, New Colleges, New Agents (*nt*), Appointments, Student Leads |
| Manager dashboard | Tiles T-M01…08 (Total BDMs, Today's / Upcoming Appointments, BDMs Travelling, Trips This Month, Meetings Completed, MoUs in Progress, MoUs Signed); alerts AL-1 Appointment not confirmed (≤24 h), AL-2 Travel approval pending, AL-3 Follow-up overdue, AL-4 MoU pending ≥5 days, AL-5 Appointment completed today, AL-6 Outcome missing, AL-7 Daily report not submitted (yesterday) |

### 5.7 Notifications (titles as built)

| Title | Recipient | Channel | Source |
|---|---|---|---|
| Travel approval needed | Reporting manager (or every active super admin if manager inactive, T11) | in-app | `api/bdm_travel.py` L74 |
| Trip approved / Trip not approved | BDM | in-app | L134 |
| School onboarding requested / Agent onboarding requested | Overseas Admins (→ `/overseas/admin/schools` / `/agents`) | in-app | `api/bdm_onboarding.py` L43 |
| School onboarded / Agent onboarded / "… not approved" | Assigned BDM | in-app | `services/bdm_onboarding.outcome_notice` |
| Work handed over to you | Receiving BDM | in-app (+ default channels) | `services/bdm_lifecycle.py` L119 |
| "N BDM(s) now report(s) to you" | Replacement manager | | L166 |
| Appointment reminder (09:00 day before) / Appointment in 1 hour / Travel reminder / Follow-up due today / Task due today / MoU follow-up / MoU renewal due | Owner BDM | in-app + **email** | `services/bdm_reminders.py` |
| (none) | Meeting requests send no notifications | — | tel-019 |

---

## 6. Upload limits and test files

| Upload | Rule | Test file needed |
|---|---|---|
| MoU document (`PUT /bdm/organizations/{id}/mou/document`) | Type by **bytes**: PDF (`%PDF-`), JPEG, PNG only (else 415); size ≤ `MAX_UPLOAD_BYTES` (default **20 MB**, `core/config.py` L56; `.env` may override — check the bdmdocs `.env`); empty → 422; image metadata stripped; one current file, replace keeps the old object; **20 uploads per user per rolling hour** → 429; current MoU must exist | `docs-mou-agreement.pdf` (1–2 pages, fictional "Docs" partner names) |
| Trip receipts | **No upload** (T7) | none |
| Anything else in BDM | No other upload | — |

---

## 7. Recommended capture sessions

### 7.1 Accounts (recommendation, see Q1)

| Account (created in S2) | Role | Type | Manager | Why |
|---|---|---|---|---|
| Docs BDM Manager | `bdm_manager` | — | — | Overseas-only team, so manager screens contain no College rows |
| Docs Agent BDM 1 (Hyderabad) | `bdm` | agent | Docs BDM Manager | Main Agent walkthrough |
| Docs Agent BDM 2 (Kochi) | `bdm` | agent | Docs BDM Manager | Target for manager reassign (C2) and bdm-025 handover (same module required) |
| Docs School BDM (Bengaluru) | `bdm` | school | Docs BDM Manager | Main School walkthrough |
| Seeded Rahul / Kavya / Sanjay | | | | Login and "demo accounts" only; or Overseas Admin edit/list screens |

### 7.2 Session breakdown (ordered by data dependency)

| S | Title | Actors | Creates / captures | Depends on |
|---|---|---|---|---|
| S2 | Admin provisioning & sign-in | super admin, Overseas Admin, new accounts | Manager via `/admin/bdms` (super admin); Agent ×2 + School BDM via `/overseas/admin/bdms` (manager picker with email, B10); welcome mail in Mailpit → set password (`/admin/reset-password` for manager, `/overseas/reset-password` for BDMs); `/bdm/sign-in` chooser; first My Day (empty) and manager dashboard (empty); `/bdm/profile` | fresh seed |
| S3 | Organizations & profiles | Agent BDM 1, School BDM | Agent orgs (e.g. 3: one to onboard, one to lose, one Corporate/University extra), School orgs (e.g. 3 incl. one for Sunrise link); contacts (roles), profile fields, address; duplicate warning; archive/restore (restore = manager) | S2 |
| S4 | Pipeline | Agent BDM 1, School BDM | Stage moves, backward with note, Lost + Revive, stage history, `/bdm/pipeline` board + whole-module toggle | S3 |
| S5 | Appointments, outcomes, follow-ups, activities, leads | both BDMs | Book (future), confirm, reschedule, cancel, overlap warning; **batch of appointments ~3 min ahead → wait → complete with meeting report / mark no-show** (A2); one past-start left without report (feeds AL-6); follow-ups from reports + manual tasks (due today → reminder); activities back-dated over the last 7 days; BDM leads; calendar day/week | S3 (S4 for realistic stages) |
| S6 | Travel + approvals | Agent BDM 1, manager | Trip today (Hyderabad → Vijayawada style but Overseas cities), submit → manager approve → link today's appointments (L2) → start → expenses (4 categories) → complete → travel report; second trip tomorrow (approved, planned → "Travel reminder"); third trip rejected → edit → resubmit; withdraw | S5 (appointments to link) |
| S7 | Daily reports | both BDMs, manager | Submit **yesterday** (from back-dated activities) and other past days ≤7; leave today unsubmitted until S11; manager grid + comment | S5, S6 |
| S8 | MoUs + onboarding handover | BDMs, Overseas Admin | MoU create → statuses → upload PDF → Signed (pipeline advances) → Active with window; one MoU with `valid_until` in the past (Expired → renewal row); one Active with `valid_until` = today + 30 (renewal reminder fires today); School: request onboarding → Overseas Admin **links Sunrise Public School by School ID** (live stages + School activity panel); Agent: request at Agreement Signed → Overseas Admin **links "EduSphere Partner Agency" by code** (live Agent stages + Agent performance panel); one rejected request; lead conversion by Overseas Admin to Ananya | S4 (stage), S3 |
| S9 | Meeting requests from a telecaller | Imran (overseas telecaller), BDMs, manager | "Agent meeting" to the pool, "School meeting" naming Docs School BDM; BDM accepts (books appointment on own org) / declines with reason; manager read-only Requests view | S3 (BDM org to book against) |
| S10 | Notifications & reminders | BDMs | Wait ≥1 beat run (≤5 min): Appointment reminder / in 1 hour, Travel reminder, Follow-up due today, MoU renewal due; Notifications page + unread badge; reminder email in Mailpit; deep link `?action=confirm` | S5, S6, S8 (beat + worker running) |
| S11 | Manager oversight, targets, performance | manager, super admin | Targets for current month (+ next), copy last month (empty unless a past month was set by super admin); manager dashboard tiles + alerts; team, organizations, pipeline, MoUs, appointments, follow-ups, calendar (pick BDM), activities; Performance by type → BDM → org; Master view; super admin `/admin/bdm-travel-approvals` (empty unless a manager is inactive); finally submit today's report | S2–S10 |
| S12 | Lifecycle (last) | Overseas Admin / super admin | Portfolio view; deactivate Agent BDM 2 with **reassign** to Agent BDM 1 (or hand over after `leave`); "Work handed over to you" notice; manager bulk move (super admin, "BDM managers" card) — only if a second manager is created; reactivation | everything (destructive) |

### 7.3 Time-dependent behaviours

| Behaviour | Rule | Capture approach |
|---|---|---|
| Appointment create / reschedule | Start must be in the future (A7) | Book ahead |
| Complete / no-show | Only after the start time (A2) | Book a batch ~2–3 min ahead, wait once, then complete; there is no browser-side back-dating (`move_to_past` is a DB helper) |
| Meeting report edit | Same IST day only (R2) | Capture edits in the same session |
| Activities | ≤7 IST days back; edit/delete same day; locked by a submitted report | Back-date to spread over the week; log before submitting |
| Daily report | Today or ≤7 days back; future 422; no resubmit | Submit past days in S7, today in S11 |
| Follow-ups / tasks | Due today or later; "Overdue" and AL-3 need a day to pass | Overdue tab / AL-3 empty on a one-day capture (Q4) |
| Trips | Travel date ≤30 days back; start/complete only from the travel date (IST); expenses only after approval | Use today for the full lifecycle; tomorrow for reminder |
| MoU AL-4 / "MoU follow-up" reminder | `status_changed_at` ≥5 days | **Not reproducible** without waiting (server sets the time) |
| MoU Expired | `valid_until` before today | Enter a past window |
| MoU renewal reminder | 09:00 IST on `valid_until − 30`, same-day catch-up | `valid_until` = today + 30 |
| Day-before reminders | 09:00 IST day before, catch-up later the same day | Appointment/trip tomorrow, captured after 09:00 IST |
| Hour-before reminder | Up to the start | Appointment ~30–55 min ahead |
| AL-7 / daily grid | Profiles newer than yesterday not listed / "—" | Docs accounts created the same day never show AL-7 (Q4) |
| Targets | Current + 12 months ahead; past = super admin only; future month "Month not started" | |
| Performance / dashboard | IST month, DB clock | Run all sessions inside one IST month |

## 8. Open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | Use the seeded team (Sanjay manages Vivek, a **College** BDM) or create an Overseas-only "Docs" team for screenshots? | Create the Docs team (§7.1); seeded accounts only for sign-in references |
| Q2 | Super-admin Performance / Master view always include a College row — crop, mask, or accept with a note? | Accept with a one-line note ("College BDMs are covered elsewhere") |
| Q3 | Link the seeded Sunrise Public School and EduSphere Partner Agency (real figures) or create fresh partners (zero figures)? | Link the seeded ones; note in the manual that figures come from the partner records |
| Q4 | Time-bound states (Overdue follow-ups, AL-3, AL-4, AL-7, MoU follow-up reminder) — capture on a second day, use DB back-dating on the docs stack only, or describe without screenshots? | Describe without screenshots unless the owner approves a second-day pass; no DB edits |
| Q5 | Agent "New agents" / "Active agents" (targets, daily report) and T-A6 still show "Not tracked" although bdm-019 is merged — document as built? | Yes, as built ("Not tracked"); flag to the owner as a possible follow-up |
| Q6 | Include University organizations (upc-004 link) and `/management/bdm` (mgmt-020) in this manual? | University link: short section; mgmt-020: cross-reference only |
| Q7 | `shoot.ts` changes (`BDM_ROOT`, portal-aware `signIn`) collide with the telecaller branch's `TELECALLER_ROOT` / admin sign-in | Land one shared `signIn(portal)` change first; the other branch rebases |
