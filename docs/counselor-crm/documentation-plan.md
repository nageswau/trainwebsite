# Overseas Counselor CRM User Documentation — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans.
> - Work one session at a time, in this plan's order; later sessions rely on data created earlier.
> - Tick the checkboxes here and update `docs/counselor-crm/documentation-progress.md` at the end of every session.

**Goal:** Produce verified end-user and administrator documentation, with role guides, for the EduSphere **Overseas Counselor CRM**. Screenshots are captured by Playwright from the running app.

**Scope (owner D2):**
- In: the Overseas `counselor` portal, Overseas Admin counselor management and oversight, and Super Admin differences.
- Telecaller, agent and student screens appear only at handoff points (HO-001..004).
- Out: IT counselors.

**Architecture:**
- **Feature files.** One Markdown file per Doc ID, using the template below:
  - Counselor: `docs/counselor-crm/user-manual/<module>/`
  - Overseas Admin / Super Admin: `docs/counselor-crm/admin-manual/<module>/`
- **Screenshots** go in `docs/counselor-crm/screenshots/<module>/` and are indexed in `screenshot-index.md`.
- **Source of behaviour.** Code reviewed in Phase 1 (`documentation-analysis.md` + `discovery/`), confirmed in the browser before it is written.
- **Reproducibility.** Test-only Playwright capture specs live in `apps/web/tests/doc-capture/counselor/`.

**Tech stack:**
- App: Next.js 15, FastAPI, PostgreSQL, Celery worker + beat, via Docker Compose.
- Capture: Playwright (Chromium); the `browser-use` skill for exploration.
- Output: Markdown.

## Global Constraints
- **Scope.** The 85 Doc IDs in analysis §3. Anything else found goes into "Discovered functionality" in the progress file.
- **Do not edit** the Agent CRM docs (`docs/documentation-*.md`, `docs/user-manual/`, `docs/admin-manual/`, `docs/role-guides/`, `docs/screenshots/`, `docs/faq.md`, `docs/troubleshooting.md`, `docs/screenshot-index.md`), `docs/school-crm/` or `docs/bdm-crm/`.
- **Code baseline.** `main` @ `045d8c40`. When `main` moves, re-check features whose files changed (`git diff --stat 045d8c40..<new> -- apps/`).
- **No product code changes.** The capture tooling under `apps/web/tests/doc-capture/` and `docs/tooling/` is test/docs only.
- **Screenshot settings.**
  - Viewport **1440 × 900**, Chromium, light scheme, `deviceScaleFactor: 1`, locale `en-IN`, timezone `Asia/Kolkata`.
  - Viewport shots by default. Use `fullPage` only when a step needs the whole form, and note it in the index.
  - One 390 px mobile shot for NAV-001 (shows P18).
- **Screenshot path.** `docs/counselor-crm/screenshots/<module>/<NN>-<feature>-<step>.png`. Module folders: `account-access`, `navigation`, `dashboard`, `leads`, `conversion`, `activity`, `chat`, `follow-ups`, `tasks`, `calendar`, `reports`, `universities`, `students`, `applications`, `offers`, `documents`, `visa`, `finance`, `arrival`, `handoffs`, `admin`, `escalation`, `performance`, `config`.
- **Never show secrets.**
  - Mask password inputs, the dev-only "Demo accounts" card and "Development only" boxes (`shoot()` does this).
  - **Add a mask for the iCal feed URL (`#calendar-feed-url`)**: it is a live credential.
  - Never put a reset or welcome URL with a token in a doc or screenshot.
  - Never paste the seed password into a file. Never screenshot Mailpit.
- **Test data only (owner D1).**
  - Docs personas use `*@example.test`.
  - Every lead, student, university, course, template and task created for the docs is prefixed `Docs `.
  - Phone numbers come from the fictional range `+91 90000 1xxxx`.
  - Seeded demo records (Ananya, Vikram, Ritika) appear only where a seeded record is unavoidable (the agency application). No real people's data.
- **Commission (owner D5).** Commission fields are shown only on the Docs University and Docs courses, with fictional values (10% university, 12% course).
- **Time-dependent states (owner D3).**
  - Never back-date with SQL.
  - Overdue, expired and escalation states are captured on a later real day (S9).
  - Reminders and escalation are triggered with the Overseas Admin's **Run now**.
  - Record the capture date of each such PNG in the index.
- **VERIFICATION REQUIRED.** Anything not confirmed in the browser is written as **VERIFICATION REQUIRED** and left out of the numbered steps.
- **As-built (owner D4).**
  - Document behaviour as built, including product findings P1–P22 (analysis §12), in neutral wording. For example: "There is no Sign out on small screens; widen the window or use a desktop."
  - Default-based behaviours get no warning banners.
- **Writing style.** Simple English, numbered steps, bold UI labels exactly as on screen, one feature per file, the mandatory template.
- **Terminology** (use exactly):
  - **Roles:** **Counselor** (Overseas), **Overseas Admin**, **Super Admin**, **Telecaller**, **Agent** (agency Master/Staff), **Student**.
  - **Lead side:** **lead**, **stage** (open) / **closed** (with reason), **next action**, **follow-up**, **call log**, **meeting**, **note**, **handover**, **return**, **convert**, **link**.
  - **Student side:** **student**, **Student 360**, **walk-in student**, **application**, **EduSphere ID**, **stage**, **sub-status**, **outcome**, **journey stage**, **checklist**, **Ready for Submission**, **offer**, **condition**, **interview**, **deposit**, **visa case**, **enrolment**, **arrival**, **orientation**, **archive**, **consent**.
  - **Places:** use the sidebar label first, then the page title, e.g. "**Leads** (page title **My leads**)".
- **Capture helpers.**
  - Every spec calls `noPrefetch(context)` before navigating. Long cards use `shoot(..., { element })`, messages use `shoot(..., { center })`, and scrolls use `behavior: "instant"`.
  - Passwords only come from `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`.
  - IDs and emails pass between specs through `DOCS_CNS_FILE` (JSON, scratchpad only).
- **Docker (owner D6).**
  - Claude may start, seed, reset and snapshot the `cnsdocs` project only. Never touch other compose projects.
  - Never load the Caddy override.
  - The worker **and** beat must run.
- **Git.**
  - Commit on `docs/counselor-crm-user-guide` with `docs: add <module> Counselor CRM guide`.
  - Stage explicit paths only: `docs/counselor-crm/`, `apps/web/tests/doc-capture/counselor/`, and the shared tooling files when changed.
  - Never stage `graphify-out/`, `.env` or `docker-compose.docs.yml`.
  - The owner pushes.

## Review Focus
1. **Same screen, different role.**
   - Applies to the 360, admin users page and counselor-admin pages (Counselor vs Overseas Admin vs Super Admin), and to agency vs direct applications.
   - Each such feature file has a **What each role sees** table and one screenshot per differing role.
2. **Locked states.**
   - Closed lead (no activity), linked lead (no return), converted lead, archived student.
   - The Ready-for-Submission gate (block vs warn), agency enrolment (P13), and a deactivated counselor.
   - Document the exact message for each.
3. **Where the work happens.** Application writes are in **Evaluate Applications**, not the 360 Applications tab. Steps must send the reader to the right card.
4. **Secrets in screenshots.** Open every new PNG before committing, especially the Calendar (feed URL) and login pages.
5. **Time-dependent behaviour.**
   - Today, overdue and next-7-days follow-ups.
   - Overdue tasks older than the escalation threshold.
   - Offer and document expiry (00:05 / 00:10 IST jobs).
   - 72-hour welcome links.
   - Record capture dates.

---

## File structure (created across sessions)

```
docs/counselor-crm/
  documentation-analysis.md   documentation-plan.md   documentation-progress.md   screenshot-index.md
  discovery/01..04-*.md
  user-manual/
    README.md
    account-access/ navigation/ dashboard/ leads/ conversion/ activity/ chat/ follow-ups/ tasks/
    calendar/ reports/ universities/ students/ applications/ offers/ documents/ visa/ finance/
    arrival/ handoffs/
  admin-manual/
    README.md   (incl. Super Admin differences, P3/P4/P15)
    accounts/ escalation/ performance/ config/
  role-guides/
    overseas-counselor.md   overseas-admin-counselors.md   super-admin-counselors.md
  demo-accounts.md            (D1: Docs personas ↔ seeded demo accounts)
  faq.md   troubleshooting.md   documentation-review-report.md
  screenshots/<module>/NN-<feature>-<step>.png
apps/web/tests/doc-capture/counselor/   (capture specs, test-only)
```

### Planned file names (S2 pages already link to these)
| Doc ID | File |
|---|---|
| AUTH-002 | `user-manual/account-access/auth-002-first-password.md` |
| CHAT-001 | `user-manual/chat/chat-001-counselor-chat.md` |
| FUP-002 | `user-manual/follow-ups/fup-002-overdue-follow-ups.md` |
| FUP-003 | `user-manual/follow-ups/fup-003-automatic-reminders.md` |
| APP-005 | `user-manual/applications/app-005-sub-status-ready-gate.md` |
| DOC-001 | `user-manual/documents/doc-001-application-checklist.md` |
| APP-010 | `user-manual/applications/app-010-agency-vs-direct.md` |
| FIN-001 | `user-manual/finance/fin-001-deposit.md` |
| ADM-003 / ADM-004 | `admin-manual/accounts/adm-003-student-counselor.md`, `adm-004-application-counselor.md` |
| ESC-001 / ESC-002 | `admin-manual/escalation/esc-001-counselor-tasks-admin.md`, `esc-002-overdue-escalation.md` |

Other files follow `<module-code>-<NNN>-<short-name>.md` in the module folder.

Image links:
- From a manual feature file: `../../screenshots/<module>/<file>.png`.
- From a role guide: `../screenshots/<module>/<file>.png`.

### Feature file template (every feature)
```markdown
# <Feature name>
> Doc ID: DOC-CNS-XXX-NNN · Verified on <date> against `main` @ <commit> · Roles: <roles>

## Purpose
## Who Can Use This Feature
## Prerequisites
## How to Access
<Sidebar > … > …>
## Steps
### Step 1 — <action>
<instruction with **UI label**>
![<alt text>](../../screenshots/<module>/<file>.png)
<expected result>
## Fields
| Field | Description | Required | Example |
|---|---|---|---|
## Expected Result
## Validation Messages
## Common Errors
**Problem:** … **Cause:** … **Resolution:** …
## Tips
## Related Features
```
Add a **What each role sees** table after "Who Can Use This Feature" whenever roles differ.

---

## Sessions

### Dependency order and calendar (owner D3)
- **S2** builds the stack and tooling, configures the catalogue and templates, and creates the Docs personas. Everything depends on it.
- **S3** sets persona passwords from the welcome links. All later sessions sign in as Docs personas.
- **S4–S8** create the leads, activity, students and applications.
  - **Day 1 = the day S5 runs.** S5 creates follow-ups and tasks due **tomorrow**.
  - S7 creates an offer whose expiry is **tomorrow**, and a document request due tomorrow.
- **S9 runs at least 3 real days after S5**, so follow-ups and tasks are overdue past the escalation threshold (appendix 03: older than 2 days) and the offer has expired. Run reminders with **Run now**.
- **S10** (lifecycle: archive, restore, deactivate) runs last because it hides data.
- **S11** writes guides from the existing screenshots; **S12** reviews.

**Rerun rule.** Specs create data through the UI, so a rerun needs a fresh database:
1. Reset `cnsdocs` (`down -v`, `up -d`, migrate, seed).
2. Clear Mailpit.
3. Rerun the specs in session order.

To iterate on one session, restore the `pg_dump` snapshot from the end of the previous session (scratchpad only). A reset after S5 restarts the D3 calendar.

### Standard session loop (S2–S10)
- [ ] **L1** Read `documentation-analysis.md`, this plan, `documentation-progress.md`, `screenshot-index.md` and the relevant `discovery/` sections.
- [ ] **L2** Fetch `origin/main`.
  - If it has moved past the baseline, list changed files touching this session's routes and re-review them.
  - Check the `cnsdocs` stack is up; start it if not.
  - Record the web URL and commit in the progress file.
- [ ] **L3** Explore each feature in the browser as each relevant role. Tick "Browser Verified" only for what was seen. Confirm or drop each product finding for these features.
- [ ] **L4** Write or extend `apps/web/tests/doc-capture/counselor/cns-sN-<module>.capture.ts` and run it. Open every PNG: readable, correct state, no secrets.
- [ ] **L5** Write one feature file per Doc ID using the template. Mark unconfirmed points **VERIFICATION REQUIRED**.
- [ ] **L6** Run `node docs/tooling/check-doc-links.mjs docs/counselor-crm` and fix broken links.
- [ ] **L7** Update `screenshot-index.md` and `documentation-progress.md` (status, unresolved items, discovered functionality, session log). Snapshot the database.
- [ ] **L8** Report to the owner. Commit explicit paths. The owner pushes.

### S1 — Master planning — DONE 2026-10-29
- [x] Four parallel discovery passes: leads and workday, students and Student 360, access/admin/handoffs, test data/tooling/decisions.
- [x] Owner answers D1–D7. Wrote `documentation-analysis.md`, this plan, `documentation-progress.md`, the `screenshot-index.md` skeleton and the `discovery/` appendices.

### S2 — Environment, capture tooling, admin set-up (creates personas) — DONE 2026-10-30
Features: ADM-001, ADM-002 (create/edit/re-send; deactivate is in S10), CFG-001, CFG-002 (view/edit rules; Run now is in S9), CFG-003 (5).
- [x] **S2.1 Stack.**
  - Worktree `.claude/worktrees/cns-docs`; run `docker compose -p cnsdocs -f docker-compose.yml -f docker-compose.docs.yml`.
  - The untracked `docker-compose.docs.yml` adds Mailpit on `127.0.0.1:8029:8025`.
  - The untracked `.env` is the repo `.env` with `WEB_PORT=3050`, `API_PORT=8050`, `FRONTEND_URL=http://localhost:3050`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, no SMTP credentials, `SMTP_FROM_EMAIL=no-reply@edusphere.local`, `ENVIRONMENT=development`. Make sure the Zoho Mail API is **not** configured (ENH-032), so mail goes to SMTP/Mailpit.
  - The worker and beat must run. Seed from `045d8c40`.
  - Scratchpad scripts: `docs-env.sh` (DOCS_BASE_URL, DOCS_MAILPIT_URL, DOCS_PASSWORD from the seed, a random DOCS_TEST_PASSWORD) and `reset-stack.sh`.
- [x] **S2.2 Tooling (test-only).**
  - Add `export const COUNSELOR_ROOT` to `apps/web/tests/doc-capture/shoot.ts`.
  - Extend `signIn()` with an optional portal (`/admin/login`), keeping the default unchanged. This is the same shape as the telecaller/BDM branches, to ease later merges.
  - Add a set-password matcher to `mailLink`, a `#calendar-feed-url` mask, and a `counselor` mode in `docs/tooling/build-pdfs.mjs`.
  - Prove the Agent and School specs still list (`--list`).
- [x] **S2.3** Masking check on `account-access/01-overseas-login.png` and `admin-login.png`.
- [x] **S2.4 Standard loop.**
  - As the Overseas Admin:
    - create **Docs Counselor A/B/C** (ADM-001), including a duplicate-email error;
    - edit B and re-send the link from Users (ADM-002);
    - create the **Docs checklist template** in block mode (CFG-001);
    - view the reminder rules (CFG-002);
    - create a **Docs message template** (CFG-003).
  - As the Super Admin: show the create-user Division default (P4, shot only; cancel without saving).
  - Setup only, not documented features: create **Docs Telecaller** (Overseas, Employee ID `DOCS-TEL-1`, manager Lakshmi).
  - **Moved to S7 prep (2026-10-30):** **Docs University** with **Docs MSc Data Science** and **Docs MBA**, commission 10% / 12% (owner D5), via University Master (`/partnership/universities/new` → publish → add courses). Counselors only see published (catalogue-visible) universities.
  - S2 notes: `/admin/login` lands on `/admin` (no trailing slash); its demo card is titled "Demo super admin" — `shoot()` now masks it. Restoring a snapshot must restart `web` after `api` is healthy (scratchpad `restore-snap.sh`).
- [x] **S2.5** Snapshot `after-s2`.

### S3 — Account access and navigation — DONE 2026-10-30
Features: AUTH-001..006, NAV-001 (7).
- [x] Standard loop.
  - Docs Counselor A/B/C set their passwords from Mailpit links (AUTH-002); C sets one too so they can be deactivated later.
  - Sign in at /overseas/login, forgot/reset password, change password, My profile, sign out.
  - Sidebar tour, plus the 390 px menu without Sign out (P18).
  - The deactivated-login message is captured in S10 and added to AUTH-006 then.
- [x] Snapshot `after-s3`.

### S4 — Leads and handoffs (lead side) — DONE 2026-10-30
Features: HO-001, HO-002, LEAD-001..009, CONV-001, CONV-002 (13).
- [x] Standard loop.
  - As Docs Telecaller, hand **Docs Lead Asha** and **Docs Lead Bilal** to Docs Counselor A (HO-001).
  - Submit a public website enquiry → **Docs Lead Chen** (HO-002); the Overseas Admin assigns it if needed.
  - As Counselor A: record walk-in lead **Docs Lead Divya** (LEAD-002); list (LEAD-001); detail, details edit, next action (LEAD-003..005).
  - Stages: move Asha to Qualified; close Bilal as Not Interested with a reason (LEAD-006, P5); qualification (LEAD-007).
  - Return Chen to the telecaller (LEAD-008; also show P2 on Bilal without submitting); milestones panel (LEAD-009).
  - Convert Asha → **Docs Converted Student** (CONV-001); link/unlink an existing student on Divya (CONV-002).
- [x] Snapshot `after-s4`.
- S4 as run: Chen came via auto-distribution (no manager step); Esha (not Chen) was returned; CONV-002 used a walk-in student "Docs Divya Student" with Divya's email (linked, then unlinked, so Divya is at Follow-up). Lead ids are in `DOCS_CNS_FILE`.

### S5 — Activity, chat, follow-ups, tasks, calendar (= Day 1) — DONE 2026-10-30
Features: ACT-001..006, CHAT-001, FUP-001, TASK-001, CAL-001, CAL-002 (11).
- [x] Standard loop.
  - On Divya: call, WhatsApp record, email (lands in Mailpit), meeting, note, timeline (ACT-001..006).
  - Counselor Chat with Docs Converted Student (CHAT-001).
  - Follow-ups due today and **tomorrow** (FUP-001). Tasks due today, tomorrow and +7 days; complete one, cancel one (TASK-001, P10).
  - Appointments page and the no-show text (CAL-001, P8). Calendar page and feed URL, which is **masked** (CAL-002).
- [x] Record "Day 1 = <date>" in the progress file. Snapshot `after-s5`.
- S5 as run: appointments are booked by the telecaller on the telecaller's own leads (Esha + new Farah/Gita/Hari); one open appointment per lead; 60-minute slots can't overlap. CAP-000002 (Farah, 31 Oct 13:00) was left **Scheduled** for the S9 no-show. Day 1 = 2026-10-30.

### S6 — Students and the Student 360 — DONE 2026-10-30
Features: STU-001..007, STU-010, HO-003, HO-004, ADM-003, ADM-004 (12).
- [x] Standard loop.
  - As Counselor A: add walk-in **Docs Walk-in Student** and **Docs Pending Walk-in** (left pending); edit pending, resend (STU-003).
  - Students page / Application Tracking (STU-001); My students with the Source filter (STU-002, P17).
  - Student 360 Overview (STU-004), structured profile (STU-005), notes (STU-006), Activities/History (STU-007).
  - **Docs Self-registered Student** registers via the public sign-up (HO-004).
  - As the Overseas Admin:
    - assign the seeded agency application (Ananya) to Docs Counselor A (ADM-004, HO-003);
    - assign the self-registered student to A (ADM-003);
    - change Docs Walk-in Student's counselor A → B with a reason, then back (ADM-003).
  - Counselor-side view of each reassignment (STU-010).
  - Super Admin: the counselor column is absent (shot for the "What each role sees" table).
- [x] Snapshot `after-s6`.
- S6 as run: self-registered student uses `docs.self.student@example.com`; Ananya's seeded agency application moved from Ritika to Counselor A (its 360 now in A's caseload). Long 360 tabs are element shots of `main` (full-page shots repeat the sticky sidebar).

### S7 — Applications, offers, documents — DONE 2026-10-30
Features: APP-001..010, OFR-001..003, DOC-001..004 (17).
- [x] **S7 prep (setup only):** as the Overseas Admin, add **Docs University** (United Kingdom, so the S2 checklist matches; agent commission 10%), publish it, add **Docs MSc Data Science** (PG, course commission 12%) and **Docs MBA** (PG).
- [x] Standard loop.
  - On Docs Converted Student: add application A1 (Docs University / Docs MSc Data Science, intake picker) (APP-001..003).
  - Checklist from the Docs template (DOC-001). Request documents due tomorrow (DOC-003). Upload a document (DOC-004). Documents page (DOC-002, P21).
  - Show the Ready-for-Submission block, then satisfy it (APP-005). Advance stages (APP-004, P12). Application details (APP-008, P14). Journey stage (APP-006). History (APP-009).
  - On Docs Walk-in Student: add application A2 (Docs MBA) and record an outcome / resume (APP-007).
  - Agency vs direct on the seeded agency application (APP-010, P22).
  - On A1: record an offer with expiry **tomorrow**, plus conditions and an interview (OFR-001..003). On A2: an offer with expiry +30 days, accepted (needed by S8).
- [x] Snapshot `after-s7`.
- S7 as run: specs `cns-s7a-university-setup` (set-up) and `cns-s7b-applications`; sample PDFs from `DOCS_FILES_DIR` (scratchpad `files/`). Uploads must be tied to the application to appear in Document Verification (P28). For S8: A2 (Docs Walk-in Student, Docs MBA) has an accepted unconditional offer with deposit GBP 3,000 due +20 days; Ananya's agency application is on Counselor A for the P13 check.

### S8 — Visa, finance, arrival, universities — DONE 2026-10-30
Features: VISA-001, FIN-001..003, ARR-001, ARR-002, UNI-001, UNI-002 (8).
- [x] Standard loop.
  - On A2: deposit record (FIN-001), Finance tab (FIN-002), deposit receipt / payment proof upload (FIN-003), visa case lifecycle (VISA-001), confirm enrolment (ARR-001), arrival and orientation (ARR-002).
  - Agency enrolment message vs panel on the agency application (P13): shot only, **do not confirm**.
  - Universities list and University 360 with the Docs course commission (UNI-001/002).
- [x] Snapshot `after-s8`.
- S8 as run: spec needs `DOCS_WALKIN_ID` (users.id of Docs Walk-in Student) for the admin fee; the visa case needs its checklist documents Verified first.

### S9 — Time-based states, dashboards, admin oversight (≥ 3 days after S5)
Features: FUP-002, FUP-003, ESC-001, ESC-002, DASH-001, SRCH-001, REP-001, PERF-001, PERF-002 (9). Also the CFG-002 **Run now** step.
- [ ] Confirm the date is ≥ Day 1 + 3 (2026-11-02), and that the 00:05/00:10 jobs have run (expired offer on A1, overdue document request).
- [ ] OFR-001: A1 offer shows **Expired** (deadline 31 Oct). OFR-002: mark the A1 condition **Met** with `docs-evidence.pdf`. DOC-003: English test request shows **Overdue**.
- [ ] CAL-001: **Mark no-show** on CAP-000002 (P8 text). TASK-001: the Overseas Admin gives Counselor A a task ("Given by" row, status-only).
- [ ] Standard loop.
  - As the Overseas Admin: **Run now** on the reminder rules (CFG-002 step), counselor tasks (ESC-001), overdue by counselor + escalation notice (ESC-002), team performance A vs B (PERF-001), one counselor (PERF-002).
  - As Counselor A: overdue follow-ups on Tasks (FUP-002); reminder results and where they appear (FUP-003, P1); dashboard tiles and "View all" (DASH-001, P6); quick search (SRCH-001, P7); My performance (REP-001, P9).
- [ ] Snapshot `after-s9`.

### S10 — Lifecycle: archive, consent, restore, deactivate
Features: STU-008, STU-009, CFG-004 (3). Also adds the deactivate steps to ADM-002 and the deactivated-login message to AUTH-006.
- [ ] Standard loop.
  - Docs Walk-in Student accepts consent on their dashboard; counselor view (STU-009).
  - Counselor A archives Docs Walk-in Student; Archived Students list (STU-008, P16).
  - The Overseas Admin restores them (CFG-004); the Super Admin refusal shot.
  - The Overseas Admin deactivates **Docs Counselor C** (ADM-002, P19); C's sign-in attempt (AUTH-006).
- [ ] Snapshot `after-s10`.

### S11 — Guides and supporting pages
- [ ] `user-manual/README.md` and `admin-manual/README.md`. The admin README includes Super Admin differences and P3/P4/P15.
- [ ] Role guides: `overseas-counselor.md` (day-in-the-life, workflows 1–4), `overseas-admin-counselors.md`, `super-admin-counselors.md`.
- [ ] `demo-accounts.md` (D1), `faq.md`, `troubleshooting.md` (built from Common Errors and P-findings).
- [ ] Link check.

### S12 — Final review and PDFs
- [ ] Parallel reviewers: accuracy against code, screenshots/secrets, style/terminology, links/structure. Fix all findings.
- [ ] Duplicate-screenshot check. Set Reviewed = PASSED/FAILED; mark COMPLETE.
- [ ] `documentation-review-report.md` (findings, P1–P22 status, partial features, owner items).
- [ ] PDFs: `node docs/tooling/build-pdfs.mjs counselor` → `docs/counselor-crm/pdf/`.
