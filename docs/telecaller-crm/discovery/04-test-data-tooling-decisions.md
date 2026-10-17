# 04 — Test data, capture tooling and decisions (Telecaller CRM, Overseas)

> Evidence appendix for `docs/telecaller-crm/documentation-analysis.md`. Read-only S1 discovery, 2026-10-17, main @ `6fee294d`.
> Nothing outside this file was changed. No docker or server was run. Seed and e2e passwords are **not** copied here: the
> seeded-account password is called "the seed password (DOCS_PASSWORD)"; it is the `PASSWORD` constant in `apps/api/app/seed.py`.

Classification: every row below is **as built in code on main @ 6fee294d** unless marked otherwise. Owner answers are cited by their
DEC-SCOPE code. The backlog's T1–T29 are `EXPLICIT_APPROVAL` (backlog §3.1, registered as `DEC-SCOPE-073`).

---

## 1. Seed data

### 1.1 Telecaller-related demo accounts (`apps/api/app/seed.py` L861–879; `user()` helper L45–52)

The `user()` helper gives every account the seed password (DOCS_PASSWORD) and `profile={"demo": true}`. Accounts are only created when
the email is missing, so a re-seed is idempotent.

| Email | Name | Role | Division / team | Employee ID | Reports to |
|---|---|---|---|---|---|
| `telecaller.manager@edusphere.local` | Lakshmi Telecaller Manager | `telecaller_manager` | `global` | — | — |
| `telecaller.it@edusphere.local` | Pooja IT Telecaller | `telecaller` | `it` | TEL-DEMO-001 | Lakshmi |
| `telecaller.overseas@edusphere.local` | **Imran Overseas Telecaller** | `telecaller` | **`overseas`** | TEL-DEMO-002 | Lakshmi |

Other seeded accounts the Overseas telecaller manual needs (`USERS`, seed.py L17–29, and L861–870):

| Email | Name | Role | Division | Why it matters for the Telecaller CRM |
|---|---|---|---|---|
| `superadmin@edusphere.local` | Global Super Admin | `super_admin` | global | Creates telecaller managers; read-only on telecaller work (DEC-SCOPE-115 PM2) |
| `overseasadmin@edusphere.local` | Overseas Administrator | `overseas_admin` | overseas | Creates/deactivates Overseas telecallers (T21, DEC-SCOPE-104 LC1); `/overseas/admin/leads`, telecaller performance/reports |
| `counselor@edusphere.local` | Ritika Counselor | `counselor` | overseas | The **only seeded Overseas counselor**: appointment booking (tel-016 AP4) and handover target (tel-018) |
| `bdm.manager@edusphere.local` | Sanjay BDM Manager | `bdm_manager` | global | Reads BDM meeting requests (MR3) |
| `bdm.agent@edusphere.local` | Rahul Agent BDM | `bdm` (type agent) | overseas | Accepts "Agent meeting" requests (tel-019) |
| `bdm.school@edusphere.local` | Kavya School BDM | `bdm` (type school) | overseas | Accepts "School meeting" requests |
| `bdm.college@edusphere.local` | Vivek College BDM | `bdm` (type college) | **it** | Accepts "College" and "Corporate meeting" requests (T26); request routing is by BDM type, not division |
| `itadmin@edusphere.local` | IT Division Administrator | `it_admin` | it | IT counterpart only; out of the Overseas manual |
| `student.overseas@edusphere.local` | Ananya Sharma | `overseas_student` | overseas | Candidate for a counselor's student link (tel-018); has a seeded application |

No **IT counselor** is seeded (`counselor@` is overseas). No second Overseas telecaller is seeded.

### 1.2 Seeded telecaller business data

| Data | Where seeded | Overseas | IT | Notes |
|---|---|---|---|---|
| Leads (`enquiries`) | seed.py L519–546 (only if the table is empty) | **1**: "Demo Overseas Lead", `overseaslead@example.com`, `+919999000002`, subject "Masters in UK", source `website`, status `contacted` | 1: "Demo IT Lead", status `new` | No owner (unassigned), no product, no campaign. Lead ID comes from the DB default `LD-000001…`. Seeded with a direct insert, so it never went through distribution |
| Products (`tel_products`) | migration `0076_tel_catalogue` (always runs, idempotent) | **9**: UK, USA, Canada, Australia, New Zealand, Germany, Japan, South Korea, Dubai (group `overseas`, team `overseas`) | 5 (Digital Marketing, SAP, Cyber Security, Python Full Stack, Java) + Job Assistance, Career Change (`other` → it) | Career Guidance and General Enquiry are `other` with team **none**, so they go to the unassigned queue (T18) |
| Campaigns (`tel_campaigns`) | none | 0 | 0 | Must be created (manager UI or `POST /api/v1/telecaller/campaigns`) |
| Scripts (`tel_scripts`) | migration `0083_tel_content` | **0** | 1: "Cyber Security standard script" (7 steps) | Overseas lead detail shows **no script** until one is created for an Overseas product (C3: max one active per product) |
| Message templates | migration `0083_tel_content` | 9 WhatsApp + 7 email, **all generic (no product)**, so they apply to Overseas too | same | Overseas-flavoured kinds: WhatsApp `overseas_destination`, `document_request`; email `overseas_information`, `university_information` |
| Brochures / fee PDFs (`tel_assets`) | none | 0 | 0 | Need a PDF to upload (kinds `brochure`, `fee`); served signed-out under `/public/telecaller-assets/*` |
| Targets (`tel_targets`) | none | 0 | 0 | Team defaults + per-telecaller overrides, effective tomorrow or later (G2) |
| Distribution rules | none | 0 | 0 | With no rules, website leads round-robin across active telecallers of the team (DI2) |
| Alert settings (`tel_settings`) | migration `0099_tel_settings` | `not_contacted_hours` 24, `hot_pending_hours` 4 | same | Manager-editable, 1–168 h |
| Calls, follow-ups, appointments, messages, qualifications, imports, meeting requests | none | 0 | 0 | All must be created by the capture specs |

**Consequence for capture:** on a fresh seed, Imran is the only active Overseas telecaller, so every Overseas website enquiry created
during capture is **auto-assigned to Imran** by round robin (DEC-SCOPE-087 DI2) until other Overseas telecallers exist. Dashboards,
reports and performance pages are empty until calls/follow-ups/appointments are logged. Calls may be back-dated up to **7 days**
(`lead_calls` imports `BACKDATE_DAYS = 7` from `bdm_activities.py`), which lets a spec spread activity over several IST days; follow-ups
must be due in the future (`DUE_PAST`).

---

## 2. Capture tooling

### 2.1 `apps/web/playwright.docs.config.ts`

| Setting | Value |
|---|---|
| testDir / testMatch | `./tests/doc-capture`, `**/*.capture.ts` |
| workers / retries / timeout | 1 / 0 / 60 s (specs raise it with `test.setTimeout`) |
| outputDir | `test-results/doc-capture` |
| baseURL | `DOCS_BASE_URL` or `http://localhost:3000` |
| viewport / DPR / scheme | 1440×900, 1, light |
| locale / timezone | `en-IN`, `Asia/Kolkata` |
| actionTimeout | 15 s |
| Run | `npx playwright test -c playwright.docs.config.ts <spec>` from `apps/web` (prefix `MSYS_NO_PATHCONV=1` in Git Bash) |

### 2.2 `apps/web/tests/doc-capture/shoot.ts` exports

| Export | Signature | Behaviour |
|---|---|---|
| `SCHOOL_ROOT` | `string` | `docs/school-crm/screenshots`. Default root is `docs/screenshots` (Agent CRM). **A `TELECALLER_ROOT` = `docs/telecaller-crm/screenshots` must be added** |
| `shoot` | `(page, module, file, opts?: { mask?: Locator[]; fullPage?: boolean; root?: string; center?: Locator; element?: Locator })` | Writes `<root>/<module>/<file>`. Always masks `input[type=password]`, the "Demo accounts" card and "Development only" text. Waits for networkidle (≤10 s). `center` scrolls an element to mid-viewport; `element` grows the viewport and captures just that element |
| `noPrefetch` | `(target: BrowserContext \| Page)` | Aborts Next.js router-prefetch requests (they stall screenshots on Docker Desktop) |
| `password` | `(kind: "seed" \| "test" = "seed") => string` | Reads `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`; throws if unset |
| `toTop` | `(locator, offset = 80)` | Instant scroll so the element sits under the sticky header |
| `signIn` | `(page, email, kind = "seed", landing = /\/overseas\/(agent\|admin)\//)` | **Hard-codes `/overseas/login`**. Works for the Overseas telecaller (pass `landing: /\/telecaller\/dashboard/`) and counselor; **does not work for the telecaller manager or super admin's `/admin/login`** — the school spec gets away with super admin only because `/overseas/login` accepts it. A portal parameter (or an `adminSignIn`) is needed |
| `mailCount` | `(to) => Promise<number>` | Mailpit search count at `DOCS_MAILPIT_URL` (default `http://localhost:8025`) |
| `mailLink` | `(to, after = 0, pattern = /…reset-password\?token=…/) => Promise<string>` | Polls Mailpit (40×500 ms) for the newest matching link among messages newer than `after`; returns path+query |
| `inviteLink` | `(to, after = 0)` | School invite pattern; not needed here |

### 2.3 School spec pattern (`tests/doc-capture/school/sch-s2-admin.capture.ts`, 221 lines)

| Aspect | How it is done |
|---|---|
| Structure | One `test(...)` per session, `test.setTimeout(420_000)`; module constants (`ADM`, `opts = { root: SCHOOL_ROOT }`), fixture objects (`SCHOOLS`, `STAFF`) with `Docs …` names and `@example.test` emails |
| Login | `signIn(page, email, "seed", landingRegex)` from shoot.ts in a fresh `browser.newContext()` with `noPrefetch(ctx)`; anonymous page for the login-page shot |
| Data creation | **Through the UI** (fill form → click → wait for the success text → `say()` logs `role=alert/status` text as `VERIFY …`). API used only for reads that the UI needs (`a.request.get(".../bulk-template")`); CSV files written to `os.tmpdir()` |
| Hand-off | Writes JSON (codes, names, emails) to `DOCS_SCHOOL_FILE`; later specs read and extend it |
| Env vars | `DOCS_BASE_URL`, `DOCS_PASSWORD` (seed), `DOCS_TEST_PASSWORD` (accounts the docs create), `DOCS_MAILPIT_URL`, `DOCS_SCHOOL_FILE` |
| Precondition | "Needs a freshly seeded DB"; reruns = reset stack → reseed → rerun S2 then later specs (snapshots via pg_dump in the session scratchpad) |

Equivalent for this set: `tests/doc-capture/telecaller/tel-sN-*.capture.ts`, `DOCS_TEL_FILE` hand-off JSON, root `TELECALLER_ROOT`.

### 2.4 `docs/tooling/check-doc-links.mjs`

`node docs/tooling/check-doc-links.mjs [root]` (repo root). No root → Agent CRM set. With a root it walks
`<root>/user-manual`, `<root>/admin-manual`, `<root>/role-guides` and `<root>/{faq,troubleshooting,screenshot-index}.md` and fails on a
missing link/image target. Run as `node docs/tooling/check-doc-links.mjs docs/telecaller-crm` — so the manual must use that folder layout.

### 2.5 Docs stack (school precedent → `teldocs`)

Precedent (untracked, in `.claude/worktrees/school-docs/`):

- `docker-compose.docs.yml` adds only `mailpit` (`axllent/mailpit:latest`, ports `127.0.0.1:8026:8025`).
- Started as `docker compose -p schooldocs -f docker-compose.yml -f docker-compose.docs.yml` — the explicit `-f` list matters because
  `docker-compose.override.yml` (Caddy on 80/443) is otherwise auto-merged.
- `.env` keys present (values not copied): `APP_NAME ENVIRONMENT LOG_LEVEL SECRET_KEY ACCESS_TOKEN_MINUTES REFRESH_TOKEN_DAYS DATABASE_URL
  REDIS_URL FRONTEND_URL COOKIE_SECURE AUTO_CREATE_SCHEMA EMAIL_ENABLED SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD AWS_REGION
  LOCAL_UPLOAD_DIR CRM_WEBHOOK_URL WHATSAPP_WEBHOOK_URL SMS_WEBHOOK_URL EMAIL_WEBHOOK_URL INBOUND_EMAIL_WEBHOOK_SECRET GOOGLE_* ZOHO_*
  MAX_UPLOAD_BYTES ALLOWED_UPLOAD_TYPES RAZORPAY_* API_PORT WEB_PORT SMTP_USE_TLS SMTP_USER SMTP_FROM_EMAIL`.
- Non-secret values relevant to the stack: `ENVIRONMENT=development`, `FRONTEND_URL=http://localhost:3020`, `SMTP_HOST=mailpit`,
  `SMTP_PORT=1025`, `EMAIL_WEBHOOK_URL=` (empty), `API_PORT=8020`, `WEB_PORT=3020`, `SMTP_FROM_EMAIL=no-reply@edusphere.local`.

How `docker-compose.yml` (tel-docs worktree) wires it: `api` publishes `${API_PORT:-8000}:8000`, runs `alembic upgrade head` then uvicorn;
`web` publishes `${WEB_PORT:-3000}:3000` with `BACKEND_INTERNAL_URL=http://api:8000`, `NEXT_PUBLIC_API_BASE=/api/v1` (relative, so the
browser always calls the web origin — no public API URL to change) and `ENVIRONMENT=${ENVIRONMENT:-production}`; `worker` and `beat`
(Celery) share `.env`. Project name (`-p`) isolates volumes.

Changes for a `teldocs` stack (web 3030 / api 8030 / Mailpit 127.0.0.1:8027):

| Item | Value | Why |
|---|---|---|
| Worktree | `.claude/worktrees/tel-docs` (this one) | |
| `docker-compose.docs.yml` (untracked) | mailpit ports `127.0.0.1:8027:8025` | 8025 = agentdocs, 8026 = schooldocs |
| Command | `docker compose -p teldocs -f docker-compose.yml -f docker-compose.docs.yml up -d --build` | Never without the Mailpit file (repo `.env` has real SMTP); never the override |
| `.env` (untracked copy of repo `.env`) | `WEB_PORT=3030`, `API_PORT=8030`, `FRONTEND_URL=http://localhost:3030` | Welcome/reset links point at the docs web |
| | `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, empty SMTP user/password | Local catch-all |
| | `SMTP_FROM_EMAIL=no-reply@edusphere.local` | Without it "email is not configured"; tel-014 builds From = `"<telecaller> via EduSphere" <SMTP_FROM_EMAIL>` (EM1) |
| | `ENVIRONMENT=development` | Admin create returns `development_welcome_token`; demo-accounts card shows (shoot masks it) |
| | `EMAIL_WEBHOOK_URL=` empty | Reset emails otherwise go to a webhook |
| Seed | `docker compose -p teldocs … exec api python -m app.seed` | |
| Capture env | `DOCS_BASE_URL=http://localhost:3030`, `DOCS_MAILPIT_URL=http://localhost:8027`, `DOCS_PASSWORD`, random `DOCS_TEST_PASSWORD`, `DOCS_TEL_FILE` | Session scratchpad only |
| Worker + beat | must run | tel-014 emails are queued → sent by the worker; tel-020 time-based alerts run every 900 s from beat (`tel020-alerts`) |

Per memory, the user controls the docker lifecycle: the stack start/seed/reset needs the user's OK.

---

## 3. Existing telecaller tests

### 3.1 Web e2e specs (`apps/web/tests/e2e/tel-001…tel-026-*.spec.ts`, 26 files, 2 960 lines)

Common setup pattern: sign in as super admin via `POST /api/v1/auth/login`; create a throwaway `telecaller_manager` and `telecaller` with
`POST /api/v1/admin/users` (`telecaller_profile: {team, employee_id, reporting_manager_user_id}`); create leads with
`POST /api/v1/public/enquiries`; assign with `POST /api/v1/telecaller/leads/assign`; log out; set passwords with
`activateWithToken(request, body.development_welcome_token)` (`tests/e2e/helpers/welcome.ts`: `POST /api/v1/auth/reset-password`);
then sign in at `/<portal>/login`. Most specs use team **it**; only tel-009 signs in at `/overseas/login`.

| Spec | Data/API it creates | UI pages visited | Reusable for docs |
|---|---|---|---|
| tel-001 roles | admin/users ×2 | `/admin/telecallers`, `/telecaller/profile`, `/telecaller/manager/team`, `/admin/reset-password?token=` | provisioning + activation flow; manager lands on `/telecaller/manager/team` |
| tel-002 catalogue | campaigns | `/telecaller/manager/products` | campaign create body |
| tel-003 lead record | public/enquiries | `/it/admin/leads` | admin lead list |
| tel-004 pipeline | public/enquiries, `POST …/leads/{id}/stage` | `/it/admin/leads` | stage moves + reasons |
| tel-005 intake | `POST /telecaller/leads`, public/enquiries | `/telecaller/leads/new` | manual lead + duplicate panel |
| tel-006 import | campaigns, `/telecaller/imports` | `/telecaller/manager/imports` | CSV import |
| tel-007 distribution | leads/assign, leads/assigned | `/telecaller/manager/assignment?view=assigned` | bulk assign |
| tel-008 workspace | `PATCH /telecaller/leads/{id}` | `/telecaller/leads/{id}`, `/telecaller/manager/leads?priority=hot` | priority |
| tel-009 qualification | `POST /telecaller/leads` (group by product) | `/overseas/login`, `/telecaller/leads/{id}` | **Overseas qualification form** |
| tel-010 calls | `POST …/leads/{id}/calls`, calls/day-counts | lead detail, `/telecaller/follow-ups?day=` | log-call form selectors (Outcome, Minutes, Seconds, Follow-up due/reason, Next action) |
| tel-011 follow-ups | `…/follow-ups`, `…/stage` | `/telecaller/follow-ups`, `/telecaller/manager/follow-ups` | |
| tel-012 content | templates | `/telecaller/manager/templates`, scripts, brochures | |
| tel-013 WhatsApp | templates, `…/messages` | lead detail (telecaller + manager) | |
| tel-014 email | `POST /telecaller/leads`, `…/messages`; Mailpit chaos API | lead detail | needs Mailpit |
| tel-015 timeline | lead + several `POST …/leads/{id}/<path>` | `/telecaller/leads/{id}`, `/it/counselor/leads/{id}`, admin History | |
| tel-016 appointments | lead + stage | lead detail | booking form |
| tel-017 IT counselor | public/enquiries, `PATCH /admin/leads/{id}` | `/it/counselor/*`, `/overseas/counselor/dashboard` | IT only |
| tel-018 handover | lead, PATCH | lead detail, `/it/counselor/leads` | handover / return / link |
| tel-019 meeting requests | `POST /bdm/organizations` | `/telecaller/meeting-requests(/new)`, `/bdm/meeting-requests` | |
| tel-020 alerts | `PUT /telecaller/settings/it` | `/telecaller/notifications` | |
| tel-021 dashboard | calls | `/telecaller/dashboard`, `/telecaller/manager/team/{id}/activity` | |
| tel-022 targets | `POST /telecaller/targets` | `/telecaller/manager/targets` | |
| tel-023 performance | calls | `/telecaller/manager/performance`, `/it/admin/telecaller-performance` | |
| tel-024 reports | products, campaigns, leads, calls | `/it/admin/telecaller-reports?report=…` | report kinds `source`, `campaign`, `handover`, … |
| tel-025 lifecycle | `POST /admin/telecaller-managers/{id}/deactivate`, `PATCH /admin/users/{id}` | `/admin/telecallers?q=` | deactivate + reassign |
| tel-026 matrix | admin/users | many (403/404 checks) | none (tests only) |

### 3.2 API test helpers (`apps/api/tests/tel0NN_helpers.py`)

These mostly write rows straight to the DB (pytest fixtures), so they are **not** directly usable from Playwright; their value is the
payload shapes and URLs.

| Helper | Functions | Endpoints / payloads |
|---|---|---|
| tel001 | `make_tl_manager`, `tel_payload`, `create_telecaller`, `sign_in_as_created` | `POST /api/v1/admin/users` `{role:"telecaller", email, full_name, phone, telecaller_profile:{team, employee_id, reporting_manager_user_id}}` |
| tel004 | `stage_url`, `history_url`, `make_telecaller`, `lead` | `/telecaller/leads/{id}/stage`, `/{telecaller\|admin}/leads/{id}/stage-history` |
| tel007 | `product`, `rule`, `lead`, `only_eligible` | `/telecaller/distribution-rules`, `/leads/unassigned`, `/leads/assigned`, `/leads/assign` |
| tel012 | `as_role`, `product` | content library |
| tel016 | `book`, `setup`, `body`, `make_counselor`, `student_appointment` | `POST /telecaller/leads/{id}/appointments`, `GET …/appointment-options`, `POST /lead-appointments/{id}/{confirm\|complete\|no-show\|cancel\|reschedule}`, `GET /counselor/appointments` |
| tel018 | `handover`, `make_student`, `enrol`, `apply_overseas` | `POST /telecaller/leads/{id}/handover`, `/counselor/leads` (+ `/return`, `/link-suggestions`, `/student-link`) |
| tel019 | `file_request`, `bdm_with_org`, `accept_body` | `/telecaller/meeting-requests`, `/bdm/meeting-requests/{id}/{accept\|decline}` |
| tel025 | `team`, `follow_up`, `lead_appt`, `call`, `rule_for` | `/admin/telecallers`, `/admin/telecaller-managers` |
| tel026 | `world` (full fixture) | matrix |

### 3.3 API route inventory for data creation (from `apps/api/app/api/telecaller*.py`, `lead_*.py`, `bdm_meeting_requests.py`, `admin.py`, `public.py`; all under `/api/v1`)

| Area | Routes |
|---|---|
| Provisioning/lifecycle | `POST /admin/users`; `GET /admin/telecallers/{id}/open-work`; `POST /admin/telecallers/{id}/{deactivate\|handover\|move-team}`; `POST /admin/telecaller-managers/{id}/deactivate` |
| Self | `GET /telecaller/me`, `PATCH /telecaller/profile`, `GET /telecaller/manager/team` |
| Leads | `GET/POST /telecaller/leads`, `GET /telecaller/leads/duplicate-check`, `POST /telecaller/leads/{id}/enquiries`, `GET/PATCH /telecaller/leads/{id}`, `GET …/timeline`, `GET/PUT …/qualification`, `POST …/stage`, `GET …/stage-history`; public `POST /public/enquiries` |
| Admin leads | `GET /admin/leads`, `PATCH /admin/leads/{id}`, `POST/DELETE /admin/leads/{id}/conversion`, `GET …/stage-history`, `GET …/timeline` |
| Catalogue | `GET/POST /telecaller/products`, `PATCH …/{id}`; `GET/POST /telecaller/campaigns`, `PATCH …/{id}` |
| Content | scripts, templates (+ `/{id}/preview`), assets (+ `/{id}/link`) — GET/POST/PATCH under `/telecaller` |
| Distribution | `GET/POST /telecaller/distribution-rules`, `PATCH/DELETE …/{id}`; `GET /telecaller/leads/{unassigned\|assigned}`; `POST /telecaller/leads/assign` |
| Import | `GET /telecaller/imports/template`, `POST/GET /telecaller/imports`, `GET …/{batch_id}` |
| Calls | `GET /telecaller/calls/day-counts`, `GET/POST /telecaller/leads/{id}/calls`, `PATCH/DELETE /telecaller/calls/{id}` |
| Follow-ups | `GET /telecaller/follow-ups`, `GET/POST /telecaller/leads/{id}/follow-ups`, `PATCH /telecaller/follow-ups/{id}`, `POST …/{complete\|cancel}` |
| Messages | `GET /telecaller/leads/{id}/render`, `GET/POST …/messages`, `DELETE /telecaller/messages/{id}` |
| Appointments | see tel016 row |
| Handover | see tel018 row |
| Meeting requests | `GET /telecaller/meeting-requests/options`, `GET/POST /telecaller/meeting-requests`; BDM `GET /bdm/meeting-requests(/{id})`, `POST …/{accept\|decline}` |
| Dashboard/metrics | `GET /telecaller/dashboard`, `GET /telecaller/activity`, `GET /telecaller/manager/performance(.csv)` |
| Targets / settings / reports | `POST/GET /telecaller/targets`, `GET …/effective`; `GET /telecaller/settings`, `PUT /telecaller/settings/{team}`; `GET /telecaller/reports/{kind}(.csv)` |

### 3.4 Web routes (for the screen inventory)

| Persona | Sign-in → landing | Pages |
|---|---|---|
| Overseas telecaller | `/overseas/login` → `/telecaller/dashboard` (signed-out `/telecaller/*` → `/telecaller/sign-in` chooser) | Dashboard, My Leads (`/telecaller/leads`, `/new`, `/{id}`), Follow-ups, BDM requests (`/telecaller/meeting-requests`, `/new`), Notifications, Profile (+ shared Management Tasks nav item) |
| Telecaller manager | `/admin/login` → `/telecaller/manager/team` | Team (+ `/team/{id}/activity`), Leads (+ `/new`, `/{id}`), Follow-ups, Lead assignment, Distribution rules, Lead import, Targets, Performance, Reports, Alert settings, Products, Campaigns, Scripts, Templates, Brochures |
| Overseas admin | `/overseas/login` → `/overseas/admin/…` | `/overseas/admin/telecallers`, `/telecaller-performance`, `/telecaller-reports`, `leads` |
| Super admin | `/admin/login` → `/admin` | `/admin/telecallers` (managers + telecallers), `/admin/telecaller-performance`, `/admin/telecaller-reports` |
| Overseas counselor | `/overseas/login` → `/overseas/counselor/dashboard` | `leads` (+ `/leads/{id}`), `appointments` |
| BDM | BDM portal | `/bdm/meeting-requests` |

---

## 4. Decisions and backlog (`docs/delivery/TELECALLER_CRM_BACKLOG.md`, `docs/decisions/PRODUCT_DECISION_REGISTER.md`)

All 26 items are **merged to main** (backlog item status lines L189–L1098).

| Item | Title | DEC-SCOPE | Merged | Owner answers (short) | Overseas? |
|---|---|---|---|---|---|
| tel-001 | Roles, profile, provisioning, sign-in, shell | 073 (T1–T29) | PR #68 @e73dfa60 (0075) | T21: super_admin creates both roles, division admins create their team's telecallers, set-password email; manager global at `/admin/login`; T22 one team; T23 direct reports | Yes |
| tel-002 | Product catalogue + campaigns | 074 | PR #69 @c80180be (0076) | P1 readers/writers; P2 team = group, only `other` picks team; P3 start required; P4 independent deactivation | Yes (9 products) |
| tel-003 | Lead record, Lead ID, admin list | 077 | PR #75 @10fce82e (0078) | L1 `LD-000001`; L2 unknown source → `other`; L3 `+91` normalisation | Yes |
| tel-004 | Pipeline + stage history | 081 | PR #81 @69829a59 (0081) | PL1 legacy mapping; PL2 assigned → first-call-pending → contacted by calls; PL3 No Response manual; PL4 link → Application/Enrollment | Yes |
| tel-005 | Manual lead, duplicates, website intake | 088 | PR #92 @014168b2 (0086) | I1 email optional on manual lead; I2 creator keeps it; I3 public reply never leaks; I5 anyone adds enquiry to existing lead; I6 manager's lead distributed | Yes |
| tel-006 | CSV import per campaign | 091 | PR #96 @126b454b (0087) | IM1 one campaign per upload, per-row report, ≤1 MB / 500 rows | Yes |
| tel-007 | Distribution, round robin, unassigned queue | 087 | PR #90 @595025e4 (0085) | DI1 active account only; DI2 website/BDM leads distributed on intake (product → city → round robin); DI3 rules per direct report; DI4 one Lead assignment page | Yes |
| tel-008 | Lead workspace, priority | 084 | PR #85 @b76c92f7 | W1 priority change audited; D6 script panel | Yes |
| tel-009 | Qualification form | 093 | PR #98 @d328a705 (0089) | QF1 product only in Lead details; QF2 selects + free text; QF3 counselor read in tel-018 | Yes (overseas section) |
| tel-010 | Call logging | 096 | PR #106 @7e3ab62a (0092) | CL1 outcomes; CL2 no call on closed lead; CL3 Duplicate Lead recorded only (merge deferred); CL4 edit/delete same IST day by caller | Yes |
| tel-011 | Follow-ups | 094 | PR #100 @8f9f1676 (0090) | F1 overdue = past due, call never completes; F2 only lead's telecaller writes; F3 move with lead; F4 closed → cancelled | Yes |
| tel-012 | Scripts, templates, brochures | 083 | PR #83 @50838192 (0083) | C1 library; C2 preview with sample values; C3 ordered steps, one active per product; C4 generic seed per kind | Yes (no Overseas script seeded) |
| tel-013 | WhatsApp click-to-chat + log | 100 | PR #112 @a0b5ee31 (0095) | WA1 full text kept; WA2 lead's telecaller before handover; WA3 same-day delete by sender; WA4 template optional | Yes |
| tel-014 | Email to lead (SMTP) | 106 | PR #120 @becb70c5 (0097) | EM1 "<telecaller> via EduSphere", Reply-To telecaller; EM2 never deleted; EM3 100/day → 429; EM4 template optional | Yes (needs Mailpit) |
| tel-015 | Lead timeline | 114 | PR #134 @c97b8a8c | TM1 admin History toggle; TM2 200-char excerpts; TM3 downstream milestones after link | Yes |
| tel-016 | Counselor appointments for leads | 095 | PR #103 @92946a8a (0091) | AP1 clash → 409, fixed 60 min; AP2 counselor acts, telecaller reschedules/cancels; AP3 no-show/cancel → Follow-up; AP4 any active counselor of division; AP15 close cancels | Yes (Career / Overseas / University counselling) |
| tel-017 | Counselor in IT division | 076 | PR #73 @675762d3 | C1 Dashboard + My Leads only | **No** (IT only) |
| tel-018 | Handover, return, student link, conversion | 101 | PR #114 @f37ebea8 | HO1 admin or counselor unlinks; HO2 only admin unlinks Converted; HO3 Converted = OverseasApplication `enrolled` (or IT Enrollment `active`); HO4 handover rules | Yes |
| tel-019 | BDM meeting requests | 098 | PR #109 @f8f599ee (0093) | MR1 named BDM or type pool, first accept wins; MR2 decline final; MR3 bdm_manager/super_admin read; MR4 no withdraw | Yes (agent/school BDMs) |
| tel-020 | Alerts & notifications | 111 | PR #129 @d6097548 (0099) | AL1 24 h / 4 h; AL2 per alert in-app + email; AL3 no quiet hours; AL4 timings; AL13 shared mark-read | Yes |
| tel-021 | Dashboard + daily activity | 105 | PR #118 @89e1c4eb | DB1 not-contacted threshold (now team setting); DB2 conversion credit = telecaller at first conversion | Yes |
| tel-022 | Daily + monthly targets | 080 | PR #80 @a38955d5 (0080) | G1 no working-day calendar; G2 manager picks effective date (future only); G3 any manager sets team defaults, overrides for direct reports; G4 "My targets" card | Yes |
| tel-023 | Manager performance comparison | 112 | PR #131 @2059b26d | PF1 manager / division admin / super_admin; PF2 leads that became theirs; PF3 credit to whoever did it; PF4 Total row, sort, ≤366 days | Yes |
| tel-024 | Management reports + CSV | 109 | PR #126 @6d85b4d7 | RP1 activity in range; RP2 still converted; RP3 funnel columns; RP4 handover = currently with counselor | Yes |
| tel-025 | Deactivation, team move, bulk reassign | 104 | PR #122 @692ffa78 | LC1 admins only (team move = super_admin); LC2 open work; LC3 target telecaller or team queue; LC4 reactivation allowed | Yes |
| tel-026 | §22 permission matrix sweep | 115 | PR #137 @42b95e24 | PM1–PM5: 106 routes × 11 roles, no gap; super_admin read-only on telecaller work | Reference only (no screens) |

### 4.1 Not built — do not document as features

| Not built | Source |
|---|---|
| Telephony/dialer, automatic call capture (calls are manual + `tel:` link) | T7; Appendix A L1384 |
| Ad-platform lead APIs (Facebook/Google lead forms) | T15 |
| Lead deletion, campaign spend, SMS to leads | backlog §1 "Not in the source" |
| Lead self-service / lead logins | backlog §1 |
| Counselor availability/slot management (only a clash check) | backlog §1, AP1 |
| Duplicate-lead **merge** (Duplicate Lead is a recorded outcome only) | CL3 |
| Automatic No Response after N attempts | PL3 |
| WhatsApp Business API, delivery status, consent model (wa.me click-to-chat only) | T8 |
| Email reply tracking | EM1 |
| Lead consent capture and retention period (open, PRD_OPEN_ITEMS row 85) | WA1 / tel-014 status line |
| Withdrawing a BDM meeting request; telecaller-manager view of requests | MR4, MR3 |
| Quiet hours / digests for alerts | AL2, AL3 |
| Working-day calendar for daily targets | G1 |
| Downstream Counselor/Application-Executive/Visa CRMs (only read live after link) | T4 |
| "Last contact" in the duplicate panel | tel-005/010/013 status lines |

---

## 5. Product glossary (exact values)

### 5.1 Lead stages (`apps/api/app/lead_stages.py`; UI shows `status_label`)

| Open stage key | Label | How it is reached |
|---|---|---|
| `new` | New Lead | creation |
| `assigned` | Assigned | event `assigned` (from new) |
| `first_call_pending` | First Call Pending | event `call_unconnected` (busy/no answer/switched off) from new/assigned |
| `contacted` | Contacted | event `call_connected` from new/assigned/first_call_pending |
| `qualified` | Qualified | manual (telecaller) |
| `interested` | Interested | manual |
| `follow_up` | Follow-up | manual; also reopen target, `appointment_released`, `returned`, `student_unlinked` |
| `counselling_scheduled` | Counselling Scheduled | `appointment_booked` |
| `counselling_completed` | Counselling Completed | `appointment_completed` |
| `application_enrollment` | Application/Enrollment | `student_linked` (manual moves stop here) |
| `converted` | Converted | computed `converted` event (never selectable) |

| Closed outcome key | Label |
|---|---|
| `not_interested` | Not Interested |
| `not_eligible` | Not Eligible |
| `wrong_number` | Wrong Number |
| `no_response` | No Response |
| `lost` | Lost |

Closing needs a reason ("Add a reason for closing the lead"); only a manager reopens (to Follow-up, with a reason).

### 5.2 Priority (`LEAD_PRIORITIES`; `lib/telecallerLeads.ts`)

`hot` Hot — "Ready to join / immediate requirement." · `warm` Warm — "Interested but needs follow-up." · `cold` Cold — "Long-term / low interest."

### 5.3 Lead sources (`app/tel_sources.py`; labels `lib/telecallerCatalogue.ts`)

`instagram` Instagram · `facebook` Facebook · `google` Google · `website` Website · `whatsapp` WhatsApp · `walk_in` Walk-in · `college`
College · `school` School · `agent` Agent · `referral` Referral · `exhibition_event` Exhibition/Event · `bdm` BDM · `other` Other.
Product groups: `it` IT Courses · `overseas` Overseas Education · `other` Other.

### 5.4 Calls (`LEAD_CALL_TYPES`, `LEAD_CALL_OUTCOMES`; labels `services/lead_calls.py`)

Call types: `outgoing`, `incoming`.

| Outcome key | Label | Effect |
|---|---|---|
| `interested` | Connected – Interested | connected |
| `need_information` | Connected – Need Information | connected |
| `follow_up_required` | Connected – Follow-up Required | connected; **next follow-up required** |
| `appointment_fixed` | Connected – Appointment Fixed | connected |
| `not_interested` | Not Interested | closes → Not Interested |
| `wrong_number` | Wrong Number | not connected; closes → Wrong Number |
| `busy` | Busy | not connected (→ First Call Pending) |
| `no_answer` | No Answer | not connected |
| `switched_off` | Switched Off | not connected |
| `call_back_requested` | Call Back Requested | connected; **next follow-up required** |
| `already_joined` | Already Joined Elsewhere | closes → Lost |
| `duplicate_lead` | Duplicate Lead | remarks naming the other lead required; no stage change |
| `not_eligible` | Not Eligible | closes → Not Eligible |

Limits: max duration 4 h; back-date ≤ 7 days; not in the future; 300 calls/day cap; edit/delete only today by the caller.

### 5.5 Follow-ups (`LEAD_FOLLOW_UP_REASONS`; labels `lib/telecallerFollowUps.ts`)

| Reason key | Label |
|---|---|
| `discuss_with_parents` | Need to discuss with parents |
| `course_details` | Need course details |
| `fee_details` | Need fee details |
| `waiting_salary` | Waiting for salary |
| `waiting_documents` | Waiting for documents |
| `comparing_courses` | Comparing courses |
| `next_month` | Interested next month |
| `next_intake` | Interested next intake |
| `university_information` | Waiting for university information |
| `counselor_call` | Requested counselor call |

Statuses `open`, `done`, `cancelled`. My Leads filters: "Due today", "Overdue". There is no follow-up "type" field — the reason is the
classifier (`NEEDS_CONFIRMATION` if the manual should call it a type).

### 5.6 Lead appointments (`models.py` L1963–1973; labels `lib/leadAppointments.ts`)

Statuses: `scheduled` Scheduled · `confirmed` Confirmed · `rescheduled` Rescheduled · `completed` Completed · `cancelled` Cancelled ·
`no_show` No show (open = scheduled/confirmed/rescheduled). Actions: Confirm, Mark completed, Mark no-show, Cancel, Reschedule.
Types: Overseas lead → `career_counselling` Career counselling, `overseas_counselling` Overseas counselling, `university_counselling`
University counselling (IT → career, `it_course_counselling`). Modes: `Online`, `Phone`, `In person`. Fixed 60 minutes.

### 5.7 Qualification form (`lib/telecallerLeads.ts`; `LeadQualification` + `enquiries` columns)

| Section | Field (key → label) | Type |
|---|---|---|
| Basic | `qualification` Qualification · `current_org` Current college/company · `passing_year` Passing year (1950–2100) · `work_experience_years` Work experience (years) (0–50) · `city` City · `state` State | text / number |
| Overseas requirement (product label "Destination") | `study_level` UG / Master's (`ug` UG, `masters` Masters) · `preferred_course` Preferred course · `intake` Intake · `academic_percentage` Academic percentage (0–100) · `english_test_status` IELTS/PTE status · `budget_range` Budget · `passport_status` Passport status (`none` No passport, `applied` Applied, `valid` Has a valid passport) | select / text / number |
| IT requirement (product label "Course interested in") | `it_skill_level` (beginner/intermediate/advanced) · `career_objective` · `preferred_batch` · `budget_range` · `preferred_mode` (online/offline) | IT only |

### 5.8 Alerts (`services/telecaller_alerts.py` `TITLES`)

| Kind | Title | Trigger |
|---|---|---|
| `lead_assigned` | New lead assigned | event |
| `follow_up_due` | Follow-up due | beat, 15 min before due |
| `follow_up_missed` | Missed follow-up | beat, open 1 h after due |
| `appointment_tomorrow` | Appointment tomorrow | beat, from 18:00 IST the day before |
| `appointment_hour` | Appointment in 1 hour | beat |
| `not_contacted` | Lead not contacted | beat, team threshold (24 h default) |
| `hot_pending` | Hot lead pending | beat, team threshold (4 h default) |
| `appointment_completed` | Counselor appointment completed | event |
| `lead_returned` | Lead returned for follow-up | event |

### 5.9 Other enums

| Enum | Values |
|---|---|
| Message channels | `whatsapp`, `email`; email delivery `queued`, `sending`, `retrying`, `sent`, `failed` |
| WhatsApp template kinds | welcome, course_details, brochure, fee_details, counselling_appointment, reminder, follow_up, overseas_destination, document_request |
| Email template kinds | course_brochure, fee_proposal, counselling_confirmation, overseas_information, university_information, follow_up, appointment_confirmation |
| Placeholders | `{name}`, `{product}`, `{appointment_time}`, `{brochure_link}` |
| Asset kinds | `brochure`, `fee` |
| Target KPIs | calls, connected_calls, qualified_leads, follow_ups, counselling_appointments, conversions |
| BDM meeting request types | `college` College meeting, `agent` Agent meeting, `school` School meeting, `corporate` Corporate meeting (→ college BDMs); statuses `pending`, `accepted`, `declined` |

---

## 6. Recommended capture sessions

Overseas team throughout; Docs-created people use `DOCS_TEST_PASSWORD` and `@example.test` emails; a `DOCS_TEL_FILE` JSON carries IDs.
Each session restores the previous session's pg_dump snapshot rather than replaying everything.

| Session | Persona(s) | Creates (in order) | Depends on | Screens |
|---|---|---|---|---|
| **S2 admin provisioning** | super admin, overseas admin | 1. Super admin creates "Docs Overseas Manager" (`telecaller_manager`) at `/admin/telecallers`; 2. overseas admin creates "Docs Overseas Telecaller A" and "B" reporting to Docs manager (and one to Lakshmi); 3. activate via `mailLink` (Mailpit 8027) + set-password page; 4. edit a telecaller; login page masking shot | fresh seed | admin telecaller list/create/edit, welcome email, set password, `/telecaller/sign-in` chooser, telecaller + manager landing |
| **S3 manager setup** | telecaller manager (Lakshmi or Docs manager) | 1. Campaign "Docs UK September 2026" (Instagram → UK); 2. Overseas script for UK; 3. edit a template; 4. upload brochure + fee PDFs; 5. distribution rules (product UK → A, city rule → B); 6. alert settings for overseas; 7. team default + override targets (effective tomorrow) | S2 | Products, Campaigns, Scripts, Templates (+ preview), Brochures, Distribution rules, Alert settings, Targets, Team |
| **S4 lead intake** | manager, telecaller, public | 1. website enquiries via `/overseas` public form or `POST /public/enquiries` (auto-distributed); 2. manager manual lead; 3. telecaller manual lead + duplicate panel + "Add enquiry to this lead"; 4. CSV import (per-row report with rejects); 5. Lead assignment page: unassigned queue, bulk assign/reassign | S3 (campaign, rules) | My Leads, New lead, duplicate panel, Lead import, Lead assignment, unassigned queue |
| **S5 telecaller frontline** | Docs telecaller A | 1. lead detail + priority; 2. qualification (Overseas section); 3. log calls incl. back-dated ones (not connected, call-back + follow-up, interested, closing outcome); 4. follow-ups create/reschedule/complete/cancel; 5. WhatsApp log (template + custom, same-day delete); 6. email (Mailpit shows "via EduSphere"); 7. stage moves Qualified/Interested/close with reason | S4 | Lead detail sections, Calls, Follow-ups page, Messages, script panel, timeline |
| **S6 appointments + BDM requests** | telecaller A, `counselor@` (Ritika), `bdm.agent@`/`bdm.school@` | 1. book Overseas counselling with Ritika (clash 409 shot); 2. counselor confirms/completes; 3. no-show on a second lead → back to Follow-up; 4. telecaller files Agent + School meeting requests (named and pool); BDM accepts one, declines one | S5 | Booking form, counselor appointments, BDM requests list/new, BDM side |
| **S7 counselor handover** | telecaller A / manager, Ritika, overseas admin | 1. handover to Ritika; 2. counselor lead view (read qualification, timeline); 3. return with reason → `lead_returned` alert; 4. re-handover; 5. student link (link-suggestions → Ananya or a Docs student) → Application/Enrollment; 6. Converted requires an `OverseasApplication` at `enrolled` (see Q3); 7. admin unlink | S6 | Handover dialog, `/overseas/counselor/leads(/{id})`, return, link, Converted badge, admin History |
| **S8 alerts, dashboard, targets** | telecaller A, manager | 1. wait for/trigger beat alerts (follow-up due, hot pending) or capture event alerts only; 2. notifications page + badge; 3. telecaller dashboard + My targets; 4. manager team activity | S5–S7 | Notifications, Dashboard, daily activity |
| **S9 manager oversight + reports** | manager, overseas admin, super admin | 1. manager leads list/filters, follow-ups, reopen a closed lead; 2. performance (manager + `/overseas/admin/telecaller-performance`); 3. reports (source, campaign, telecaller, handover, …) + CSV | S5–S8 | Manager Leads/Follow-ups, Performance, Reports |
| **S10 lifecycle** | overseas admin, super admin | 1. open-work view; 2. deactivate telecaller B with reassignment to A / queue; 3. reactivate; 4. super admin team move (needs both teams) and manager deactivation | S4+ (B must own open leads) | Deactivate dialog, open work, team move |

Dependency chain: S2 → S3 → S4 → S5 → S6 → S7 → (S8, S9) → S10. S10 must run last because it moves leads.

---

## 7. Open questions

| # | Question | Why it matters |
|---|---|---|
| Q1 | May Claude start/seed/reset a `teldocs` stack (web 3030, api 8030, Mailpit 127.0.0.1:8027), including worker + beat? | Memory: the user controls docker |
| Q2 | Use the seeded accounts (Imran, Lakshmi) or Docs-created ones as the main personas? Seeded Imran gets every round-robin Overseas lead unless other Overseas telecallers exist | Persona naming in the manual and distribution results |
| Q3 | Showing "Converted" needs the linked student's `OverseasApplication` at `enrolled` (HO3). Create that through the counselor/admin application flow in the capture, or leave Converted as text-only? | Application workflow is outside the Telecaller CRM |
| Q4 | Time-based alerts need beat ticks (every 15 min) and real elapsed time (e.g. 24 h not contacted). Lower the team thresholds to 1 h and wait, or document those alerts from event alerts + text only? | Capture duration |
| Q5 | Include the IT-only parts (tel-017 IT counselor, IT script) as a short note, or omit entirely from an Overseas manual? | Scope of the manual |
| Q6 | Is the super admin's read-only view of telecaller work (PM2) and the Management `/management/telecalling` summary (mgmt) in scope? | Extra personas |
| Q7 | shoot.ts needs a `TELECALLER_ROOT` and an admin-portal sign-in; OK to edit that shared test helper on the docs branch? | Only test code, but shared with Agent/School specs |
| Q8 | Brochure/fee PDFs: which sample files may be uploaded (a generated dummy PDF)? | Asset screens |
