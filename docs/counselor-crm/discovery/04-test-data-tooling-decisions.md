# 04 — Test data, capture tooling and decisions (Counselor CRM, Overseas)

> Evidence appendix for the Overseas Counselor CRM documentation set. Read-only S1 discovery, 2026-10-29, main @ `045d8c40`
> (worktree `.claude/worktrees/cns-docs`). Nothing outside this file was changed; no docker or server was run. Passwords are **not**
> copied here: the seeded-account password is called "the seed password (DOCS_PASSWORD)"; it is the `PASSWORD` constant in
> `apps/api/app/seed.py` (and is printed on the dev-only login card — see §5).

Classification: every row is **as built in code on main @ 045d8c40** unless marked otherwise. Decision status words are quoted from
`docs/decisions/PRODUCT_DECISION_REGISTER.md`; "defaults" = builder's recommended defaults (`NEEDS_CONFIRMATION` / `UNVERIFIED`), not
`EXPLICIT_APPROVAL`.

---

## 1. Seed data

### 1.1 Entry point and how it runs

| Item | Value |
|---|---|
| Seed script | `apps/api/app/seed.py` → `python -m app.seed` (runs `Base.metadata.create_all`, then idempotent inserts; most blocks run only when the table/row is empty) |
| Reference JSON | `apps/api/seed/countries.json`, `programs.json`, `direct_tieups.json` (+ CSVs) |
| Migrations | `api` container command `alembic upgrade head && uvicorn …`; `apps/api/entrypoint.sh` also runs alembic unless `RUN_MIGRATIONS=false` |
| Seed in compose | `docker compose -p cnsdocs -f docker-compose.yml -f docker-compose.docs.yml exec api python -m app.seed` |
| Date-relative rows | Seed appointment = seed time **+2 days**; IT interview +3 days; enrolment −25 days. Screenshots taken days after seeding drift (an "upcoming" appointment becomes past) → reseed close to capture |

### 1.2 Accounts relevant to the counselor manual (no passwords)

All use the seed password and `profile={"demo": true}`; created only if the email is missing.

| Email | Name | Role | Division | Use in this set |
|---|---|---|---|---|
| `counselor@edusphere.local` | Ritika Counselor | `counselor` | overseas | **The only seeded Overseas counselor** (specialisms UK/Germany/Ireland); owns the seeded application + appointment; landing `/overseas/counselor/dashboard` |
| `overseasadmin@edusphere.local` | Overseas Administrator | `overseas_admin` | overseas | Assigns counselors (AGN-023, csc-005, ccrm-033), checklist templates, reminder rules, counselor tasks/performance, CRM reports, message templates, archive restore |
| `student.overseas@edusphere.local` | Ananya Sharma | `overseas_student` | overseas | Agency student (linked to `agent@`) with application `EDU-OVS-2027-0001` (stage `university_review`), 3 documents (Passport + Transcript verified, SOP pending), visa case `not_started`, structured profile (ccrm-007) |
| `student.walkin@edusphere.local` | Vikram Walk-in | `overseas_student` | overseas | csc-001 walk-in student linked to Ritika, **no application**; source "Walk-in" (ccrm-043); chat target for ccrm-044 |
| `agent@edusphere.local` | Global Admissions Agent | `agent` (approved) | overseas | Agency side of the seeded application (agency vs direct contrast) |
| `university.rep@edusphere.local` | Daniel University Rep | `university_rep` | overseas | Manchester rep; never sees sensitive documents (ccrm-022) |
| `superadmin@edusphere.local` | Global Super Admin | `super_admin` | global | `/admin/login`; read-only on most counselor work |
| `telecaller.overseas@edusphere.local` / `telecaller.manager@edusphere.local` | Imran / Lakshmi | `telecaller` / `telecaller_manager` | overseas / global | Source of handed-over leads (tel-018) |
| `partner.one@`, `partner.two@`, `accountant@edusphere.local` | — | `partner`, `accountant` | global | Management CRM reports (ccrm-034, `/management/crm-reports`) |

Not seeded: a **second Overseas counselor** (needed for csc-005 / ccrm-033 reassignment and Admin performance comparisons), an IT
counselor (`/it/counselor/*` exists but is out of scope), any direct (non-agency) application.

### 1.3 Counselor business data after a fresh seed

| Data | Source | State | Capture consequence |
|---|---|---|---|
| Universities | seed `UNIVERSITIES` | 11 across UK, Germany, Canada, Australia, USA, Ireland, Netherlands, Singapore | Enough for lists/filters |
| Courses | seed (only if empty) | 5 Masters (Manchester, TUM, Waterloo, Monash, UCD) | Multiple applications (ccrm-046) can use 5 courses |
| Applications | seed | **1** (agency, Ananya, Manchester, `university_review`, ref `EDU-OVS-2027-0001`; APP- code from 0166) | Every direct-application flow (offers, conditions, deposits, visa, enrolment, arrival) must be created by specs |
| Leads (`enquiries`) | seed | 1 Overseas "Demo Overseas Lead" (`overseaslead@example.com`, status `contacted`, **no owner**) | Counselor lead list is empty until a lead is handed over (tel-018), owner-assigned by Admin, or recorded as walk-in (csc-004) |
| Sub-statuses | code `app/application_sub_status.py` (no table seed) | 5 stages × fixed list | Nothing to seed |
| Checklist templates | migration 0173 (tables only) | **0** | Admin must create one (`/overseas/admin/checklists`) before ccrm-019 checklist/readiness screens show content |
| Lost reasons | migration 0186 | 6 seeded reasons | Usable as-is |
| Reminder rules | none; missing row = catalogue default **enabled** | 11 rules (§1.4) | Every rule fires on the first run |
| Student message templates | migration 0191 (no inserts) | **0** | Admin creates at `/overseas/admin/message-templates` (ccrm-037) |
| Consent agreements | migration 0193 | overseas data-processing + document-sharing v1 | Student accepts on their dashboard (ccrm-040) |
| Tasks, follow-ups, notes, calls, meetings, offers, deposits, document requests, calendar feed | none | 0 | Created by specs |

### 1.4 Celery beat jobs that affect counselor screens (`apps/api/app/worker.py` L258–272)

| Beat key | Task | Schedule | Counselor relevance |
|---|---|---|---|
| `ccrm030-counselor-reminders` | `send_counselor_reminders_task` | daily 02:45 UTC = **08:15 IST** | ccrm-030 rules **and** ccrm-031 `overdue_escalation`; idempotent per `rule:subject:anchor`. Admin "Run now" on `/overseas/admin/reminder-rules` triggers the same run (no need to wait for beat) |
| `ccrm021-document-expiry` | `expire_documents_task` | daily 18:35 UTC = 00:05 IST | Documents past expiry date → `expired` (day after the date). **No Run-now button** |
| `ccrm025-offer-expiry` | `expire_offers_task` | daily 18:40 UTC = 00:10 IST | Undecided offers past deadline expire. **No Run-now button** |
| `tel018-conversion-sweep` | `sweep_lead_conversions_task` | every 900 s | Computed lead conversion after handover |
| `ccrm037-sweep-stale-student-emails` | | every 300 s | Re-sends stuck student emails |
| `enh014-sweep-stale-deliveries` | | every 300 s | Re-sends stuck notification deliveries (email) |
| `agn017-daily-reminders` | | 08:00 IST | Agency reminders only (RM4: counselor never told here) |

ccrm-038 iCal is **not** a beat job: `GET /api/v1/calendar/feeds/{token}.ics` is served on demand (lookback 90 days, max 500 events).

Reminder/escalation rule catalogue (`services/counselor_reminders.py` L78–92) — **thresholds are configurable** by the Overseas Admin
(enabled, `offset_days` within min–max, notify-student where allowed):

| Rule | Action | Timing | Default days | Range | Student copy default |
|---|---|---|---|---|---|
| first_contact | task | on assign (runs inside handover/admin owner write) | 1 | 0–30 | never |
| no_response | task | silent contacted lead | 3 | 1–60 | never |
| document_overdue | task | after due | 0 | 0–30 | yes |
| application_deadline | notify | before | 7 | 0–60 | never |
| decision_overdue | task | after | 0 | 0–30 | never |
| offer_deadline | notify | before | 3 | 0–60 | yes |
| deposit_due | notify | before | 3 | 0–60 | yes |
| condition_due | notify | before | 3 | 0–60 | yes |
| visa_appointment | notify | before | 2 | 0–30 | no |
| hold_review | task | on review date | 0 | 0–30 | never |
| overdue_escalation (ccrm-031) | notify every active Overseas Admin, once per counselor | overdue > N days | 2 | 0–30 | never |

Fixed constants (not configurable): `LOOKBACK_DAYS = 30` ("after" rules never flood old items); dashboard `WINDOW_DAYS = 14`
("approaching"), `FOLLOW_UP_DAYS = 7` (ccrm-042 overdue + today + next 7 days); WhatsApp `DAILY_CAP = 300`/sender/IST day.

---

## 2. Docs stack and capture tooling

### 2.1 Compose services (`docker-compose.yml`)

`postgres` (16), `redis` (7), `api` (migrate + uvicorn, `${API_PORT:-8000}`), **`worker`** (celery worker — sends every queued email),
**`beat`** (celery beat — §1.4), `web` (`${WEB_PORT:-3000}`, `ENVIRONMENT=${ENVIRONMENT:-production}`). **No Mailpit in the repo**;
`docker-compose.override.yml` adds Caddy on 80/443 and is auto-merged unless `-f` is explicit.

Proposed `cnsdocs` stack (follows agentdocs 3010/8025, schooldocs 3020/8026, teldocs 3030/8027, bdmdocs 3040/8028):

| Item | Value | Why |
|---|---|---|
| `docker-compose.docs.yml` (untracked) | `mailpit` (`axllent/mailpit`), ports `127.0.0.1:8029:8025` | Local catch-all |
| Command | `docker compose -p cnsdocs -f docker-compose.yml -f docker-compose.docs.yml up -d --build` | Never without Mailpit (repo `.env` may hold real SMTP/Zoho); never the Caddy override |
| `.env` (untracked copy) | `WEB_PORT=3050`, `API_PORT=8050`, `FRONTEND_URL=http://localhost:3050`, `ENVIRONMENT=development`, `EMAIL_TRANSPORT=smtp`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, empty SMTP user/password, `SMTP_FROM_EMAIL=no-reply@edusphere.local`, `EMAIL_WEBHOOK_URL=` empty, all `ZOHO_MAIL_*`, `TWILIO_*`, `RAZORPAY_*` keys empty | `email_configured()` needs `SMTP_FROM_EMAIL` + host (`services/mailer.py` L539); links must point at :3050 |
| Capture env | `DOCS_BASE_URL=http://localhost:3050`, `DOCS_MAILPIT_URL=http://localhost:8029`, `DOCS_PASSWORD`, random `DOCS_TEST_PASSWORD`, `DOCS_CNS_FILE` (hand-off JSON) | Session scratchpad only |
| Worker + beat | **must run** | Emails are queued and sent by the worker; reminders/expiry by beat |

Per memory the user controls the docker lifecycle: start / seed / reset need the user's OK.

### 2.2 What exists on main vs the doc branches

| File | main @045d8c40 | `docs/bdm-crm-user-guide` | `docs/telecaller-crm-user-guide` |
|---|---|---|---|
| `apps/web/playwright.docs.config.ts` | yes (1440×900, en-IN, Asia/Kolkata, workers 1) | identical | identical |
| `apps/web/tests/doc-capture/shoot.ts` | yes — only `SCHOOL_ROOT`; `signIn` hard-codes `/overseas/login` | identical | identical |
| Agent `s2…s9` + `school/sch-s2…s10` capture specs | yes | identical | identical |
| `docs/tooling/build-pdfs.mjs` | modes: (none)=Agent, `school`, `telecaller`, **`bdm`** | identical | older (no `bdm`) |
| `docs/tooling/check-doc-links.mjs` | yes (`[root]` arg) | identical | identical |
| `docs/bdm-crm/` (S1 discovery + plan) | yes | — | — |
| `docs/telecaller-crm/` | **not on main** (branch only) | — | S1 discovery |

Neither branch has added `TELECALLER_ROOT`/`BDM_ROOT` or a portal-aware `signIn` yet (both S1 only) — all three sets will touch the same
lines of `shoot.ts`.

### 2.3 Changes needed for the counselor set

| Tool | Change |
|---|---|
| `shoot.ts` | `export const COUNSELOR_ROOT = path.resolve(__dirname, "../../../../docs/counselor-crm/screenshots")`; pass `{ root: COUNSELOR_ROOT }` |
| `signIn` | Counselor/Admin/student/agent work as-is: `/overseas/login`, landing `/\/overseas\/counselor\//`, `/\/overseas\/admin\//`, `/\/overseas\/student\//`. Super admin and partner/accountant (management reports) need `/admin/login` → add a `portal` parameter (`"overseas" \| "it" \| "admin"`) once, shared with tel/bdm sets |
| `mailLink` | Default pattern = reset-password; welcome links (csc-002/003) need a set-password pattern — confirm the URL path from `_welcome_html` before writing it |
| `build-pdfs.mjs` | Add `counselor` mode: `ROOT docs/counselor-crm`, prefix "EduSphere Overseas Counselor CRM — ", `COUNSELOR_BOOKS` (plan book first) |
| `check-doc-links.mjs` | No change: `node docs/tooling/check-doc-links.mjs docs/counselor-crm` (needs `user-manual/`, `admin-manual/`, `role-guides/` layout) |
| Specs | `tests/doc-capture/counselor/cns-sN-*.capture.ts`; reuse flows from e2e `ccrm-041-sample-journey.spec.ts` and `csc-001…005-*.spec.ts` |
| Time-travel | Overdue/expired states cannot be created through the UI (see §4) → either back-dated SQL fixtures in the scratchpad or capture across days — owner decision Q3 |

---

## 3. Decision map (all items merged to main)

PR = merge PR into main. "Defaults" = builder defaults recorded `NEEDS_CONFIRMATION`/`UNVERIFIED`; "Owner" = owner-confirmed in
session. Migration "—" = none. Backlog status lines for ccrm-020/027/028 cite stale DEC numbers (266); the register numbers below win.

| Item | Feature | DEC-SCOPE | API § | RBAC § | Migration | PR | Decision status |
|---|---|---|---|---|---|---|---|
| AGN-023 | EduSphere counselor assignment / agency hand-off | 090 | 12M | §1 note (L273) | — | #102 (+#105) | EXPLICIT_APPROVAL H1–H12 |
| tel-018 | Handover to counselor, return, student link | 101 | 12V | 2.28 | — | #114 | EXPLICIT_APPROVAL |
| csc-001 | Student belongs to bringing counselor | 226 | — (no route) | 2.148 | 0165 | #293 | Owner confirmed |
| csc-002 | Counselor creates walk-in login | 227 | 12EM | 2.149 | — | #294 | Owner confirmed |
| csc-003 | Resend link / fix pending walk-in | 228 | 12EN | 2.150 | — | #295 | Owner confirmed |
| csc-004 | Walk-in lead | 229 | 12EO | 2.151 | — | #296 | Owner confirmed |
| csc-005 | Admin reassigns student counselor | 230 | 12EP | 2.152 | — | #297 | Owner confirmed |
| ccrm-001 | Dashboard tile counts | 238 | — | — | — | #300 | Owner confirmed |
| ccrm-002 | Lead notes | 242 | 12EU | 2.157 | 0167 | #302 | Owner pre-authorised |
| ccrm-003 | Lead stage, next action, follow-ups | 243 | 12EV | 2.158 | 0169_lead_next_action | #305 | Owner pre-authorised |
| ccrm-004 | Calls/WhatsApp/email/meetings on leads | 259 | 12FL | 2.173 | 0181 | #322 | Defaults |
| ccrm-005 | Lead data fields | 260 | 12FM | 2.174 | 0182 | #323 | Defaults |
| ccrm-006 | Lead stages + loss capture | 264 | 12FQ | 2.178 | 0186 | #327 | Defaults |
| ccrm-007 | Structured student profile | 249 | 12FB | 2.164 | 0174 | #311 | P1–P2 owner; rest defaults |
| ccrm-008 | Convert lead → student | 252 | 12FE | 2.167 | — | #314 | Defaults (K1–K6) |
| ccrm-009 | Student 360 | 253 | 12FF | 2.168 | — | #315 | V1–V2 owner; rest defaults |
| ccrm-010 | Student/application notes | 241 | 12ET | 2.156 | 0169_overseas_student_notes | #304 | Owner (proceed with defaults) |
| ccrm-011 | APP- business IDs ("EduSphere ID") | 239 | 12EQ | 2.153 | 0166 | #301 | Defaults (UNVERIFIED) |
| ccrm-012 | Quick search + filters | 246 | 12EY | 2.161 | — | #308 | PROPOSED, defaults |
| ccrm-013 | Application fields / dates | 256 | 12FI | 2.171 | 0179 | #319 | Defaults |
| ccrm-014 | Application sub-status | 240 | 12ER | 2.154 | 0168 | #303 | Owner confirmed |
| ccrm-015 | Exception outcomes | 244 | 12EW | 2.159 | 0170 | #306 | Owner confirmed |
| ccrm-016 | Status history author/reason | 247 | 12EZ | 2.162 | 0172 | #309 | Owner confirmed |
| ccrm-017 | Journey stage (direct students) | 258 | 12FK | — | — | #321 | Defaults |
| ccrm-018 | Checklist templates | 248 | 12FA | 2.163 | 0173 | #310 | CL1 owner; PROPOSED |
| ccrm-019 | Checklist, readiness, Ready-for-Submission gate | 257 | 12FJ | 2.172 | 0180 | #320 | AC1–AC2 owner; rest defaults |
| ccrm-020 | Document requests (direct students) | 266 | 12FS | 2.180 | 0188 | #330 | R1–R2 owner; rest defaults |
| ccrm-021 | Document status, expiry, versions | 251 | 12FD | 2.166 | 0176 | #313 | S1 owner; rest defaults |
| ccrm-022 | Sensitive documents + access log | 263 | 12FP | 2.177 | 0185 | #326 | Defaults |
| ccrm-023 | Offer records | 245 | 12EX | 2.160 | 0171 | #307 | Owner confirmed |
| ccrm-024 | Offer conditions | 261 | 12FN | 2.175 | 0183 | #324 | C1–C4 owner; rest defaults |
| ccrm-025 | Decision, acceptance, deposits | 255 | 12FH | 2.170 | 0178 | #317 (+#318) | Owner confirmed |
| ccrm-026 | Visa lifecycle | 254 | 12FG | 2.169 | 0177 | #316 | VC1–VC5 owner |
| ccrm-027 | Enrolment confirmation | 262 | 12FO | 2.176 | 0184 | #325 | Defaults |
| ccrm-028 | Arrival + orientation | 265 | 12FR | 2.179 | 0187 | #328 | Defaults |
| ccrm-029 | Counselor tasks | 250 | 12FC | 2.165 | 0175 | #312 | PROPOSED, defaults |
| ccrm-030 | Reminder engine | 270 | 12FW | 2.184 | 0189 | #333 | Defaults |
| ccrm-031 | Overdue escalation | 272 | 12FY | 2.186 | 0190 | #335 | Defaults |
| ccrm-032 | Action dashboard | 277 | 12GD | 2.191 | — | #340 | Defaults |
| ccrm-033 | Reassignment reason | 271 | 12FX | 2.185 | — | #334 | Owner RR1–RR3 (UNVERIFIED marks remain) |
| ccrm-034 | Management CRM reports | 267 | 12FT | 2.181 | — | #329 | Defaults |
| ccrm-035 | CSV/Excel exports | 268 | 12FU | 2.182 | — | #331 | Defaults |
| ccrm-036 | Counselor's own performance | 269 | 12FV | 2.183 | — | #332 | Defaults |
| ccrm-037 | Templates + message log | 273 | 12FZ | 2.187 | 0191 | #336 | Defaults |
| ccrm-038 | Calendar invites + iCal feed (phase 1) | 274 | 12GA | 2.188 | 0192 | #337 | Defaults; phase 2 sync awaits provider decision |
| ccrm-039 | Finance tab | 275 | 12GB | 2.189 | — | #338 | Defaults |
| ccrm-040 | Archive + overseas consent | 276 | 12GC | 2.190 | 0193 | #339 | Defaults |
| ccrm-041 | Go-live matrix + sample journey | 278 | — | 2.192 | — | #341 | Defaults (test-only) |
| ccrm-042 | Dashboard follow-ups/tasks: overdue + 7 days | 316 | 12HN | — | — | #383 | Defaults |
| ccrm-043 | "My students" + Source filter | 317 | 12HO | — | — | #384 | Defaults |
| ccrm-044 | Chat with walk-in students | 320 | 12HR | — | — | #387 | Defaults |
| ccrm-045 | Counselor uploads student documents | 318 | 12HP | 2.224 | — | #385 | Defaults |
| ccrm-046 | Multiple applications per student | 324 | 12HV | 2.227 | — | #391 | Defaults |
| ccrm-047 | Intake Month+Year picker | 319 | 12HQ | — | — | #386 | Defaults |
| ccrm-048 | Deposit receipt upload (Finance) | 322 | 12HT | 2.225 | — | #389 | Defaults |
| ccrm-049 | Payment proof upload (Finance) | 326 | 12HX | 2.229 | 0216 | #393 | Defaults |
| ccrm-050 | Agent-Master commission on University form | 323 | 12HU | — (DEC-SCOPE-209 rules) | — | #390 | Defaults |
| ccrm-051 | Course-level agent-Master commission | 327 | 12HY | 2.230 | 0217 | #394 | Defaults |
| ccrm-052 | University-wise report + drill-down | 321 | 12HS | 2.181 (row added) | — | #388 | Defaults |
| ccrm-053 | Counselor performance: Admin view, intake filter, Overseas/IT split | 325 | 12HW | 2.228 | — | #392 | Defaults |

**Not on main:** none — every ccrm-001..053, csc-001..005, tel-018 and AGN-023 is merged (verified with `git log --merges` and
`merge-base --is-ancestor` for `origin/worktree-ccrm-050..053`). Owner answers for ccrm-042..053 are Q1–Q10 in
`docs/delivery/COUNSELOR_CRM_BACKLOG_2.md`; ccrm-050/051 are Admin-only (university form), not counselor screens.

Docs consequence: pages for "Defaults" items must describe behaviour as built and must not present it as approved policy.

---

## 4. Time-dependent behaviour and email

| Behaviour | Rule (code) | Screenshot impact |
|---|---|---|
| Walk-in welcome link (csc-002/003) | `WELCOME_EXPIRY_HOURS = 72` (`services/provisioning.py`); counselor response never includes the dev token (csc-002 e2e asserts it) | Activate within 72 h or resend (csc-003) — read link from Mailpit |
| Password reset | `RESET_TOKEN_TTL = 30 min` (`api/auth.py`); dev response exposes `development_reset_token` on the forgot-password page ("Development only", masked by `shoot`) | Capture quickly |
| Lead follow-ups (ccrm-003) | Must be due in the future (`DUE_PAST`); overdue = open and past due | **Overdue follow-up cannot be created via UI** — wait or back-date |
| Counselor tasks (ccrm-029) | Bands overdue / today / upcoming by IST date; done tasks visible 7 days | Past-due create allowed? `UNVERIFIED` (no validation seen in service) — check in browser |
| Dashboard (ccrm-032/042) | Approaching = within 14 days; follow-ups & tasks = overdue + today + next 7 days | Data must be dated inside these windows on capture day |
| Calls / meetings (ccrm-004) | Not in the future; back-dating up to `BACKDATE_DAYS` (shared with bdm/tel, 7) | Lets specs spread activity across days |
| Document requests (ccrm-020) | Due date must be today or later; `overdue` = open and past due; reminder rule `document_overdue` | Overdue state needs time or back-dating |
| Document expiry (ccrm-021) | Expired the day after expiry date, nightly 00:05 IST, no Run-now | Needs a night of beat or a manual task call |
| Offer expiry (ccrm-025 D3) | Nightly 00:10 IST, no Run-now | Same |
| Reminders / escalation (ccrm-030/031) | 08:15 IST daily or Admin "Run now"; idempotent per firing | Use Run now; second run creates nothing |
| Calendar feed (ccrm-038) | URL shown **once** after create/regenerate; token = credential | Must be masked |
| Consent (ccrm-040) | Student accepts v1 overseas agreements on their dashboard; WhatsApp sends need the student's opt-in (CN7) | Capture before/after consent; student WhatsApp blocked until opt-in |
| Seeded appointment | seed time +2 days | Drifts into the past |

Emails that reach Mailpit (all via the **worker**; every in-app `Notification` queues an email delivery — "email always", WhatsApp/SMS
only when opted in and Twilio configured):

| Email | Trigger |
|---|---|
| Welcome / set-password | csc-002 create, csc-003 resend, Admin-created counselor (2nd counselor for reassignment) |
| Password reset | forgot-password |
| Generic notification (+ `.ics` REQUEST/CANCEL) | Overseas appointment booked/cancelled — student + counselor, never a lead (ccrm-038 CA1–CA3) |
| Reminder / escalation notices | ccrm-030 rules (counselor; student when the rule says so), ccrm-031 to every active Overseas Admin |
| Reassignment notices | csc-005, ccrm-033 |
| Student email (ccrm-037) | Template send to a student, queued → `deliver_student_email_task` |
| Lead email (ccrm-004 / tel-014 path) | Email to a lead — `UNVERIFIED` whether counselor lead email is sent or only logged; check in browser |

---

## 5. Screenshot risks

| Risk | Where | Mitigation |
|---|---|---|
| Seed password printed on screen | `/overseas/login` and `/it/login` "Demo accounts" card when `ENVIRONMENT≠production` | `shoot` masks `.card:has-text("Demo accounts")`; never `fullPage` around it unmasked |
| Live tokens | forgot-password "Development only" reset link; iCal feed URL (`#calendar-feed-url`); welcome/reset links in Mailpit | `shoot` masks the dev text; add `mask: [page.locator("#calendar-feed-url")]`; never screenshot Mailpit bodies with links |
| Password inputs | all forms | Masked by `shoot` |
| Real-looking personal data | Seed names (Ananya Sharma, Vikram Walk-in), phones `+91999900000x`, passport/transcript rows, structured profile (passport no. fields), ccrm-022 sensitive docs | Use `Docs …` names + `@example.test`, obviously fake passport numbers; seeded document `file_url`s (`/demo/passport.pdf`) may not open — `UNVERIFIED` |
| Commercial numbers | ccrm-050/051 agent-Master commission %, seeded agent commission INR 15,000, ccrm-034/052 reports | Owner to confirm whether commission values may appear in docs |
| Email provider | `EMAIL_TRANSPORT=zoho_api` (ENH-032) would send real mail | Stack `.env`: `smtp` → Mailpit, Zoho Mail keys empty |
| WhatsApp | ccrm-004/037: no provider call — logged on confirm (click-to-chat); Twilio empty → deliveries `not_configured` | Fine in dev; describe as "logged", not "sent" |
| Payments | Razorpay keys empty → online pay unavailable; ccrm-048/049 are offline proof uploads | Do not document online payment from this stack |
| Meetings | `services/meetings.py` (Zoho Meeting) — whether counselor appointments call it is `UNVERIFIED`; keys empty | Check booking UI behaviour without keys |
| Ports collision | other docs stacks 3010–3040 / 8025–8028 | `cnsdocs` 3050 / 8050 / 8029 |

---

## 6. Open questions for the owner

| # | Question |
|---|---|
| Q1 | Scope: include Overseas Admin counselor-management screens (reminder rules, checklists, templates, counselor tasks/performance, CRM reports, ccrm-050/051 university commission) as an admin manual, or counselor-only? |
| Q2 | May the docs stack create a 2nd Overseas counselor (needed for reassignment csc-005/ccrm-033 and performance comparison)? |
| Q3 | Overdue/expired states (follow-ups, document requests, offers, documents, escalation): allow back-dated SQL fixtures in the scratchpad, or capture over several days? |
| Q4 | Pages for ~40 "defaults" decisions: describe as built with a "pending confirmation" note, or wait for confirmation? |
| Q5 | May commission figures (agent-Master %, INR amounts) appear in screenshots? |
| Q6 | Land one shared `shoot.ts` change (`COUNSELOR_ROOT` + portal-aware `signIn`) first, coordinated with the telecaller/BDM branches? |
| Q7 | OK to start the `cnsdocs` stack (3050/8050/Mailpit 8029) with worker + beat when capture begins? |
