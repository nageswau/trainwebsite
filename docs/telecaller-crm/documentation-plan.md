# Overseas Telecaller CRM User Documentation — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans. Work one session at a time, in this
> plan's order (later sessions rely on data created earlier). Tick the checkboxes here and update
> `docs/telecaller-crm/documentation-progress.md` at the end of every session.

**Goal:** Produce verified end-user, manager, administrator and role-based documentation for the EduSphere **Overseas
Telecaller CRM**, with screenshots captured by Playwright from the running app.

**Scope (owner D2):** Overseas `telecaller`, `telecaller_manager` running an Overseas team, Super Admin / Overseas Admin
telecaller provisioning and lifecycle, and the Overseas counselor side of handover/conversion. IT-team telecallers are
out of scope.

**Architecture:**
- **Feature files.** One Markdown file per Doc ID (template below):
  - telecaller: `docs/telecaller-crm/user-manual/<module>/`
  - manager: `docs/telecaller-crm/manager-manual/<module>/`
  - Super Admin / Overseas Admin / Counselor: `docs/telecaller-crm/admin-manual/` (counselor in `admin-manual/counselor/`)
- **Screenshots** in `docs/telecaller-crm/screenshots/<module>/`, indexed in `docs/telecaller-crm/screenshot-index.md`.
- **Source of behaviour.** Code reviewed in Phase 1 (`documentation-analysis.md` + `discovery/`), confirmed in the browser before it is written.
- **Reproducibility.** Test-only Playwright capture specs in `apps/web/tests/doc-capture/telecaller/`.

**Tech stack:** Next.js 15 / FastAPI / PostgreSQL / Celery worker + beat via Docker Compose; Playwright (Chromium) for
capture; `browser-use` skill for exploration; Markdown.

## Global Constraints
- **Scope.** The 82 Doc IDs in §Feature records. Anything else found goes into "Discovered functionality" in the progress file.
  - IT-team telecallers, BDM CRM (beyond CNS-006's touchpoint note) and Management dashboards are out of scope.
  - Never edit the Agent CRM docs (`docs/documentation-*.md`, `docs/user-manual/`, `docs/admin-manual/`, `docs/role-guides/`, `docs/screenshots/`, `docs/faq.md`, `docs/troubleshooting.md`, `docs/screenshot-index.md`) or `docs/school-crm/`.
- **Code baseline.** `main` @ `6fee294d`. When `main` moves, re-check features whose files changed (`git diff --stat 6fee294d..<new> -- apps/`).
- **No product code changes.** The capture tooling under `apps/web/tests/doc-capture/` and `docs/tooling/` is test/docs only.
- **Screenshot settings.** Viewport **1440 × 900**, Chromium, light scheme, `deviceScaleFactor: 1`, locale `en-IN`, timezone `Asia/Kolkata`. Viewport shots; `fullPage` only when a step needs the whole form (note it in the index). One 390 px mobile shot for NAV-001.
- **Screenshot path.** `docs/telecaller-crm/screenshots/<module>/<NN>-<feature>-<step>.png`. Module folders: `account-access`, `navigation`, `dashboard`, `leads`, `calls`, `follow-ups`, `appointments`, `messages`, `content`, `meeting-requests`, `handover`, `intake`, `manager-team`, `manager-leads`, `distribution`, `imports`, `catalogue`, `targets`, `alerts`, `performance`, `reports`, `admin`, `counselor`.
- **Never show passwords, tokens or keys.** Mask password inputs, the dev-only "Demo accounts" card and "Development only" boxes (`shoot()` does this). Never put a reset/welcome URL with a token in a doc or screenshot. Never paste the seed password into a file. Never screenshot Mailpit.
- **Test data only.** `*@example.test` for Docs personas; every lead, product, campaign, script, template and brochure created for the docs is prefixed `Docs `. Phone numbers from the reserved fictional range (`+91 90000 0xxxx`). No real people's data.
- **VERIFICATION REQUIRED.** Anything not confirmed in the browser is written as **VERIFICATION REQUIRED** and left out of the numbered steps.
- **As-built.** Document behaviour as built, including product findings P1–P17 (analysis §12), phrased neutrally ("The form opens with **IT** selected; choose **Overseas**.").
- **Writing style.** Simple English, numbered steps, bold UI labels exactly as on screen, one feature per file, mandatory template.
- **Terminology** (use exactly):
  - Roles: **Telecaller** (Overseas), **Telecaller Manager** ("Manager" after first use), **Super Admin**, **Overseas Admin**, **Counselor**, **BDM**.
  - Work items: **lead**, **enquiry** (one contact event on a lead), **stage** (open) / **outcome** (closed), **priority**, **source**, **product**, **campaign**, **call log**, **follow-up**, **counselling appointment**, **BDM meeting request**, **handover**, **conversion**.
  - Places: **My Leads**, **unassigned queue**, **distribution rule**, **round robin**, **content library** (scripts, templates, brochures), **targets**, **alert thresholds**.
- **Capture helpers.** Every spec calls `noPrefetch(context)` before navigating; long cards use `shoot(..., { element })`, messages `shoot(..., { center })`, `behavior: "instant"` scrolls. Passwords only from `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`. IDs and emails pass between specs through `DOCS_TEL_FILE` (JSON, scratchpad only).
- **Docker.** Owner approved (2026-10-17) Claude starting, seeding, resetting and snapshotting the `teldocs` project only. Never touch other compose projects. Never load the Caddy override.
- **Git.** Commit on `docs/telecaller-crm-user-guide` with `docs: add <module> Telecaller CRM guide`. Stage explicit paths only (`docs/telecaller-crm/`, `apps/web/tests/doc-capture/telecaller/`, and the shared tooling files when changed in S2). Never stage `graphify-out/`, `.env` or `docker-compose.docs.yml`. The owner pushes.

## Review Focus
1. **Same screen, different role.** Lead detail differs for telecaller (full work panels), manager (stage/priority/qualification/reopen/counselor, no calls or messages) and counselor (link/return/milestones). Each such feature file has a **What each role sees** table and one screenshot per differing role.
2. **Locked states.** Handed-over (read-only), closed (no reopen for telecaller), deactivated telecaller, daily caps and same-day windows — document the exact message for each.
3. **Overseas-only screens.** Manager screens must show only Overseas data (Docs Overseas Manager has only Overseas reports). Where a form defaults to IT, the step tells the user to pick Overseas.
4. **Secrets in screenshots.** Open every new PNG before committing.
5. **Time-dependent behaviour.** Today/overdue follow-ups, same-day windows, targets starting tomorrow / next month, 72 h welcome links, 7-day brochure links, 1-hour alert thresholds (S8). Create data relative to the capture date; record the capture date in the index.

---

## File structure (created across sessions)

```
docs/telecaller-crm/
  documentation-analysis.md   documentation-plan.md   documentation-progress.md   screenshot-index.md
  discovery/01..04-*.md
  user-manual/
    README.md
    account-access/  navigation/  dashboard/  leads/  calls/  follow-ups/  appointments/
    messages/  content/  meeting-requests/  handover/  intake/
  manager-manual/
    README.md
    team/  leads/  distribution/  imports/  catalogue/  content/  targets/  follow-ups/
    alerts/  performance/  reports/
  admin-manual/
    README.md   adm-001-… adm-009-…   counselor/cns-001-… cns-006-…
  role-guides/
    overseas-telecaller.md  telecaller-manager.md  overseas-admin-telecallers.md
    super-admin-telecallers.md  counselor-telecaller-leads.md
  demo-accounts.md            (D4: Docs personas ↔ seeded demo accounts)
  faq.md   troubleshooting.md   documentation-review-report.md
  screenshots/<module>/NN-<feature>-<step>.png
apps/web/tests/doc-capture/telecaller/   (capture specs, test-only)
```

Image links: from a manual feature file `../../screenshots/<module>/<file>.png`; from `admin-manual/*.md`
`../screenshots/admin/<file>.png`; from `admin-manual/counselor/*.md` `../../screenshots/counselor/<file>.png`; from role
guides `../screenshots/<module>/<file>.png`.

### Feature file template (every feature)
```markdown
# <Feature name>
> Doc ID: DOC-TEL-XXX-NNN · Verified on <date> against `main` @ <commit> · Roles: <roles>

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

### Dependency order
- **S2** builds the stack and tooling and creates the Docs personas through the admin screens. Everything depends on it.
- **S3** uses the S2 welcome links to set passwords (all later sessions sign in as Docs personas).
- **S4** creates the catalogue, content library, routing rules, targets — needed by S5–S9.
- **S5** creates leads (intake, import, manual) — needed by S6–S10.
- **S6–S7** create activity, appointments, handovers and the converted lead — needed by S8–S9 dashboards/reports.
- **S8** includes the ~75-minute alert wait (D6).
- **S10** (lifecycle) runs last because it moves leads.
- **S11** writes guides from existing screenshots; **S12** reviews.

**Rerun rule.** Specs create data through the UI, so a rerun needs a fresh DB: reset the `teldocs` stack (`down -v`, `up -d`, migrate, seed), clear Mailpit, then rerun specs in session order. To iterate on one session, restore the `pg_dump` snapshot from the end of the previous session (scratchpad only).

### Standard session loop (S2–S10)
- [ ] **L1** Read `documentation-analysis.md`, this plan, `documentation-progress.md`, `screenshot-index.md`, and the relevant `discovery/` sections.
- [ ] **L2** Fetch `origin/main`. If it moved past the baseline, list changed files touching this session's routes and re-review them. Check the `teldocs` stack is up (start it if not — D3). Record web URL and commit in the progress file.
- [ ] **L3** Explore each feature in the browser as each relevant role. Tick "Browser Verified" only for what was seen.
- [ ] **L4** Write or extend `apps/web/tests/doc-capture/telecaller/tel-sN-<module>.capture.ts` and run it. Open every PNG: readable, correct state, no secrets.
- [ ] **L5** Write one feature file per Doc ID using the template. Mark unconfirmed points **VERIFICATION REQUIRED**.
- [ ] **L6** Run `node docs/tooling/check-doc-links.mjs docs/telecaller-crm` and fix broken links.
- [ ] **L7** Update `screenshot-index.md` and `documentation-progress.md` (status, unresolved items, discovered functionality, session log). Snapshot the DB.
- [ ] **L8** Report to the owner. Commit explicit paths. The owner pushes.

### S1 — Master planning — DONE 2026-10-17
- [x] Graphify orientation; four parallel discovery passes (frontline, manager, access/admin/counselor, test data/tooling/decisions).
- [x] Owner answers D1–D6; `documentation-analysis.md`, this plan, `documentation-progress.md`, `screenshot-index.md` skeleton, `discovery/` appendices.

### S2 — Environment, capture tooling, admin provisioning (creates personas)
Features: ADM-001, ADM-002, ADM-003, ADM-004 (4).
- [ ] **S2.1** Stack: worktree `.claude/worktrees/tel-docs`, `docker compose -p teldocs -f docker-compose.yml -f docker-compose.docs.yml`. Untracked `docker-compose.docs.yml` adds Mailpit `127.0.0.1:8027:8025`. Untracked `.env` = repo `.env` with `WEB_PORT=3030`, `API_PORT=8030`, `FRONTEND_URL=http://localhost:3030`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, no SMTP credentials, `SMTP_FROM_EMAIL=no-reply@edusphere.local`, `ENVIRONMENT=development`. Worker and beat must run. Seed from `6fee294d`. Scratchpad: `docs-env.sh` (DOCS_BASE_URL, DOCS_MAILPIT_URL, DOCS_PASSWORD from seed, random DOCS_TEST_PASSWORD), `reset-stack.sh`.
- [ ] **S2.2** Tooling (test-only): add `export const TELECALLER_ROOT` to `apps/web/tests/doc-capture/shoot.ts`; extend `signIn()` with an optional portal (`/admin/login`) keeping the default unchanged; create `apps/web/tests/doc-capture/telecaller/`. Prove Agent and School specs still list (`--list`).
- [ ] **S2.3** Masking check on `account-access/01-overseas-login.png` and `admin-login.png`.
- [ ] **S2.4** Standard loop. As Super Admin: create **Docs Overseas Manager** (ADM-001). As Overseas Admin: create **Docs Telecaller A/B/C** (Employee IDs `DOCS-TEL-A..C`, manager = Docs Overseas Manager) (ADM-002), duplicate Employee ID error, edit mobile/manager (ADM-003), re-send link from Users (ADM-004). Create **Docs Counselor** (Overseas) and a **Docs Student** (Overseas student registration) for later sessions.
- [ ] **S2.5** Snapshot `after-s2`.

### S3 — Account access and navigation
Features: AUTH-001..008, NAV-001, NAV-002 (10).
- [ ] Standard loop. Set passwords from the S2 welcome links in Mailpit (AUTH-004) for each Docs persona. Wrong portal (telecaller on `/admin/login`, manager on `/overseas/login`), invalid credentials. AUTH-005: verify whether a reset email arrives (P8) — expect PARTIAL. Profile phone change + name-locked 403 (AUTH-007). Sign-out and ended session (AUTH-008). Sidebar tours; 390 px mobile shot (NAV-001).

### S4 — Manager set-up: catalogue, content, routing, targets, thresholds
Features: CAT-001, CAT-002, CONT-002, CONT-003, CONT-004, DIST-001..003, TGT-001, TGT-002, ALRT-001 (11).
- [ ] Standard loop as Docs Overseas Manager. Create **Docs Study in UK** product + **Docs Autumn Intake** campaign; a Docs call script with steps; Docs WhatsApp and email templates with placeholders + preview; upload a generated Docs brochure PDF and copy a 7-day link (never paste the link). Product rule → Telecaller A, city rule → Telecaller B; change and delete a rule. Overseas team targets (daily from tomorrow, monthly from the 1st of next month) and an override for Telecaller A. View alert thresholds (24 h / 4 h) and the validation (1–168).

### S5 — Lead intake and entry
Features: INTAKE-001, INTAKE-002, IMP-001..003, MLEAD-002, MLEAD-006, MLEAD-007, LEAD-001..003 (11).
- [ ] Standard loop. Website enquiry on `/overseas/contact` (new lead + repeat enquiry joins it). CSV import with created / attached / rejected rows + replay. Manager manual lead (distributed and queued). Bulk assign from the unassigned queue; reassign. As Telecaller A: My Leads filters; create a lead; duplicate warning + "Add enquiry to this lead". Build up ~20 Docs leads across stages, priorities and sources for later sessions.

### S6 — Working a lead (telecaller)
Features: LEAD-004..007, QUAL-001, CALL-001, CALL-002, FUP-001, FUP-002, MSG-001, MSG-002, CONT-001, TIME-001 (13).
- [ ] Standard loop as Telecaller A. Log calls with several outcomes and stage effects; edit/delete today's call. Qualification form. Follow-ups today / overdue / future; reschedule, complete, cancel; follow-ups page. WhatsApp (template + custom, delete today's record; never follow the wa.me link). Email (check delivery in Mailpit, not screenshotted). Script + template + brochure use on the lead. Stage change and close with reason (telecaller cannot reopen). Timeline.

### S7 — Appointments, BDM meetings, handover, counselor, conversion
Features: APPT-001, APPT-002, MEET-001, MEET-002, HAND-001, HAND-002, CNS-001..006, MLEAD-005 (13).
- [ ] Standard loop. Book / reschedule / cancel a counselling appointment with Docs Counselor. BDM meeting request (Agent/School BDM). Hand a lead over (telecaller) and set a counselor (manager). As Docs Counselor: list, open, link Docs Student, return another lead. Conversion: create the Docs Student's Overseas application and move it to `enrolled` through the real application screens (D5, setup only), then capture Converted on telecaller, counselor and manager views; Overseas Admin unlink (CNS-005). CNS-006 touchpoint: one BDM-side shot.

### S8 — Alerts, notifications and dashboard
Features: NAV-003, DASH-001..004 (5).
- [ ] Standard loop. Event alerts from S5–S7 (new lead assigned, returned, appointment…). Time-based alerts (D6): as Docs Overseas Manager set Overseas thresholds to 1 h, create untouched new + hot leads for Telecaller B, wait ~75 min (beat runs every 900 s), capture both alerts, then restore 24 h / 4 h. Dashboard tiles, today cards, targets, daily activity for a past date and the future-date error.

### S9 — Manager oversight
Features: TEAM-001, TEAM-002, MLEAD-001, MLEAD-003, MLEAD-004, MFUP-001, PERF-001, RPT-001..003 (10).
- [ ] Standard loop as Docs Overseas Manager. Team list; a telecaller's activity. Team leads filters; manager lead view (What each role sees); reopen a closed lead to Follow-up. Follow-ups monitor. Performance over a range + CSV (do not commit CSVs). Reports: source, course, campaign, telecaller, handover + CSV.

### S10 — Lifecycle (runs last)
Features: ADM-005..009 (5).
- [ ] Standard loop. Deactivate Telecaller C with open work → hand to Telecaller B / team queue; reassign open work of an inactive telecaller; reactivate. As Super Admin: move a telecaller to IT and back (capture only the Overseas side); deactivate a spare **Docs Spare Manager** with replacement Docs Overseas Manager (create the spare in S10 first).

### S11 — Role guides, FAQ, troubleshooting, indexes, demo accounts
- [ ] Five role guides, `faq.md`, `troubleshooting.md` (every error message from the feature files), `user-manual/README.md`, `manager-manual/README.md`, `admin-manual/README.md`, `demo-accounts.md` (D4: Docs Overseas Manager ↔ Lakshmi, Docs Telecaller A ↔ Imran `telecaller.overseas@`, Docs Counselor ↔ `counselor@`; note Lakshmi's team mixes IT and Overseas). Link check.

### S12 — Final review
- [ ] Parallel reviewers (accuracy vs code, secrets/screenshots, links/consistency, role-matrix). Fix findings. Mark Reviewed PASSED / COMPLETE. Write `documentation-review-report.md` with product findings P1–P17 plus new ones.

---

## Feature records

**Status at end of S1:** code-reviewed at `6fee294d`, browser not verified, not documented. "Appx" = discovery file §
holding labels, messages and file:line. TC = telecaller, MGR = manager, SA = Super Admin, OA = Overseas Admin, CO = Counselor.

### AUTH — `user-manual/account-access/`, shots → `account-access/`
| ID | S | Roles | Capture (est. shots) | File | Appx |
|---|---|---|---|---|---|
| AUTH-001 | S3 | TC, MGR | chooser page; Overseas button keeps `next` (1) | `auth-001-choose-your-portal.md` | 03 §1.1–1.2 |
| AUTH-002 | S3 | TC | `/overseas/login` masked; invalid credentials; wrong portal; landing dashboard (4) | `auth-002-sign-in-telecaller.md` | 03 §1.3 |
| AUTH-003 | S3 | MGR | `/admin/login` masked; wrong portal; landing Team (3) | `auth-003-sign-in-manager.md` | 03 §1.3, 02 §0.1 |
| AUTH-004 | S3 | TC, MGR | reset page from welcome link (token hidden); success → login (2) | `auth-004-set-first-password.md` | 03 §1.6–1.7 |
| AUTH-005 | S3 | TC, MGR | forgot page; confirmation (2) — expect PARTIAL (P8) | `auth-005-forgot-password.md` | 03 §1.8 |
| AUTH-006 | S3 | TC, MGR | change password form; wrong current password (2) | `auth-006-change-password.md` | 03 §1.9 |
| AUTH-007 | S3 | TC | profile page; mobile saved; account page name-locked message (3) | `auth-007-profile-and-mobile.md` | 01 §1.2–1.3, 03 §1.10 |
| AUTH-008 | S3 | TC, MGR | sign-out; ended-session card; access-unavailable card (3) | `auth-008-sign-out-and-access-messages.md` | 03 §0.2, 1.4–1.5 |

### NAV — `user-manual/navigation/`, shots → `navigation/`
| ID | S | Roles | Capture | File | Appx |
|---|---|---|---|---|---|
| NAV-001 | S3 | TC | sidebar + role label + badge; 390 px menu (2) | `nav-001-telecaller-portal-tour.md` | 01 §1.1 |
| NAV-002 | S3 | MGR | 16-item sidebar (1) — placed in `manager-manual/` | `nav-002-manager-portal-tour.md` | 02 §0.2 |
| NAV-003 | S8 | TC | notification list with alerts; empty state (2) | `nav-003-notifications-and-alerts.md` | 01 §1.4, 02 §8 |

### DASH — `user-manual/dashboard/`, shots → `dashboard/`
| ID | S | Capture | File | Appx |
|---|---|---|---|---|
| DASH-001 | S8 | tiles (1) | `dash-001-todays-tiles.md` | 01 §2 |
| DASH-002 | S8 | today's follow-ups + appointments cards (1) | `dash-002-todays-follow-ups-and-appointments.md` | 01 §2 |
| DASH-003 | S8 | My targets table (1) | `dash-003-my-targets.md` | 01 §2 |
| DASH-004 | S8 | daily activity past date; future-date error (2) | `dash-004-daily-activity.md` | 01 §2 |

### LEAD / QUAL / TIME — `user-manual/leads/`, shots → `leads/`
| ID | S | Capture | File | Appx |
|---|---|---|---|---|
| LEAD-001 | S5 | list; filters applied; empty result (3) | `lead-001-my-leads.md` | 01 §3.1 |
| LEAD-002 | S5 | new-lead form; validation; created (3) | `lead-002-create-a-lead.md` | 01 §3.2 |
| LEAD-003 | S5 | duplicate panel; enquiry added (2) | `lead-003-duplicate-warning.md` | 01 §3.2 |
| LEAD-004 | S6 | lead header + panels; read-only (handed over) (2) | `lead-004-open-a-lead.md` | 01 §3.3 |
| LEAD-005 | S6 | priority control (1) | `lead-005-set-priority.md` | 01 §3.3 |
| LEAD-006 | S6 | details edit form (1) | `lead-006-edit-lead-details.md` | 01 §3.3 |
| LEAD-007 | S6 | stage control; close with reason; closed state (3) | `lead-007-change-stage.md` | 01 §3.4 |
| QUAL-001 | S6 | qualification form filled; saved (2) | `qual-001-qualification-form.md` | 01 §3.9 |
| TIME-001 | S6 | timeline with mixed events (1) | `time-001-lead-timeline.md` | 01 §3.12 |

### CALL / FUP / APPT / MSG / CONT-001 / MEET / HAND / INTAKE — telecaller manual
| ID | S | Folder / shots folder | Capture | File | Appx |
|---|---|---|---|---|---|
| CALL-001 | S6 | `calls/` | call-log form; outcomes; logged call + stage effect (3) | `call-001-log-a-call.md` | 01 §3.5 |
| CALL-002 | S6 | `calls/` | edit today's call; delete confirm (2) | `call-002-edit-or-delete-a-call.md` | 01 §3.5 |
| FUP-001 | S6 | `follow-ups/` | add form; reschedule; complete/cancel (3) | `fup-001-follow-ups-on-a-lead.md` | 01 §3.7 |
| FUP-002 | S6 | `follow-ups/` | Today tab; Overdue tab (2) | `fup-002-follow-ups-page.md` | 01 §4 |
| APPT-001 | S7 | `appointments/` | booking form; booked card (2) | `appt-001-book-counselling.md` | 01 §3.10 |
| APPT-002 | S7 | `appointments/` | reschedule; cancelled (2) | `appt-002-reschedule-or-cancel.md` | 01 §3.10 |
| MSG-001 | S6 | `messages/` | WhatsApp composer template/custom; record; delete (3) | `msg-001-whatsapp.md` | 01 §3.6 |
| MSG-002 | S6 | `messages/` | email composer; delivery status (2) | `msg-002-email.md` | 01 §3.6 |
| CONT-001 | S6 | `content/` | call script panel; template/brochure in composer (2) | `cont-001-use-scripts-and-templates.md` | 01 §3.8 |
| MEET-001 | S7 | `meeting-requests/` | form; submitted (2) | `meet-001-request-a-bdm-meeting.md` | 01 §5 |
| MEET-002 | S7 | `meeting-requests/` | list with statuses (1) | `meet-002-track-meeting-requests.md` | 01 §5 |
| HAND-001 | S7 | `handover/` | handover form; handed-over banner (2) | `hand-001-hand-over-to-counselor.md` | 01 §3.11 |
| HAND-002 | S7 | `handover/` | read-only view; returned; converted milestones (3) | `hand-002-after-handover.md` | 01 §3.11 |
| INTAKE-001 | S5 | `intake/` | contact form; resulting lead in queue/My Leads (2) | `intake-001-website-enquiries.md` | 03 §5.2 |
| INTAKE-002 | S5 | `intake/` | reference table (0–1) | `intake-002-lead-sources.md` | 03 §5.2, 04 §5 |

### Manager manual — `manager-manual/<folder>/`
| ID | S | Folder / shots | Capture | File | Appx |
|---|---|---|---|---|---|
| TEAM-001 | S9 | `team/` / `manager-team/` | team list (1) | `team-001-your-team.md` | 02 §1 |
| TEAM-002 | S9 | `team/` / `manager-team/` | activity + targets for a date (2) | `team-002-telecaller-activity.md` | 02 §1.1 |
| MLEAD-001 | S9 | `leads/` / `manager-leads/` | team leads; filters (2) | `mlead-001-team-leads.md` | 02 §2.1 |
| MLEAD-002 | S5 | `leads/` / `manager-leads/` | new lead; distributed notice; queued notice (3) | `mlead-002-enter-a-lead.md` | 02 §2.2 |
| MLEAD-003 | S9 | `leads/` / `manager-leads/` | manager lead view (What each role sees) (2) | `mlead-003-open-a-team-lead.md` | 02 §2.3 |
| MLEAD-004 | S9 | `leads/` / `manager-leads/` | reopen dialog; reopened (2) | `mlead-004-reopen-a-lead.md` | 02 §2.3 |
| MLEAD-005 | S7 | `leads/` / `manager-leads/` | counselor picker; set (2) | `mlead-005-assign-counselor.md` | 02 §2.3, 03 §4.1 |
| MLEAD-006 | S5 | `leads/` / `manager-leads/` | unassigned queue; bulk assign result (2) | `mlead-006-bulk-assign.md` | 02 §4 |
| MLEAD-007 | S5 | `leads/` / `manager-leads/` | assigned view; reassign (2) | `mlead-007-reassign.md` | 02 §4 |
| DIST-001 | S4 | `distribution/` | rules page explained (1) | `dist-001-how-routing-works.md` | 02 §5 |
| DIST-002 | S4 | `distribution/` | product rule; city rule; duplicate error (3) | `dist-002-create-a-rule.md` | 02 §5 |
| DIST-003 | S4 | `distribution/` | change telecaller; delete (2) | `dist-003-change-or-delete-a-rule.md` | 02 §5 |
| IMP-001 | S5 | `imports/` | template download area (1) | `imp-001-csv-template.md` | 02 §6 |
| IMP-002 | S5 | `imports/` | upload form; per-row report (2) | `imp-002-import-leads.md` | 02 §6 |
| IMP-003 | S5 | `imports/` | history list (1) | `imp-003-past-imports.md` | 02 §6 |
| CAT-001 | S4 | `catalogue/` | products list; create/edit (2) | `cat-001-products.md` | 02 §11 |
| CAT-002 | S4 | `catalogue/` | campaigns list; create (2) | `cat-002-campaigns.md` | 02 §12 |
| CONT-002 | S4 | `content/` | script editor with steps (2) | `cont-002-call-scripts.md` | 02 §13.1 |
| CONT-003 | S4 | `content/` | template editor; preview (2) | `cont-003-message-templates.md` | 02 §13.2 |
| CONT-004 | S4 | `content/` | brochure upload; link copied notice (2) | `cont-004-brochures.md` | 02 §13.3 |
| TGT-001 | S4 | `targets/` | Overseas team defaults; history (2) | `tgt-001-team-targets.md` | 02 §7 |
| TGT-002 | S4 | `targets/` | override for one telecaller (1) | `tgt-002-telecaller-override.md` | 02 §7 |
| MFUP-001 | S9 | `follow-ups/` | team follow-ups (1) | `mfup-001-team-follow-ups.md` | 02 §3 |
| ALRT-001 | S4/S8 | `alerts/` | thresholds form; validation (2) | `alrt-001-alert-thresholds.md` | 02 §8, 03 §5.1 |
| PERF-001 | S9 | `performance/` | range table; export (2) | `perf-001-performance.md` | 02 §9 |
| RPT-001 | S9 | `reports/` | source / course / campaign (3) | `rpt-001-funnel-reports.md` | 02 §10 |
| RPT-002 | S9 | `reports/` | telecaller report (1) | `rpt-002-telecaller-report.md` | 02 §10 |
| RPT-003 | S9 | `reports/` | handover report (1) | `rpt-003-handover-report.md` | 02 §10 |

### ADM / CNS — `admin-manual/`, shots → `admin/`, `counselor/`
| ID | S | Roles | Capture | File | Appx |
|---|---|---|---|---|---|
| ADM-001 | S2 | SA | Users create form (Telecaller Manager); created (2) | `adm-001-create-telecaller-manager.md` | 03 §2.1, 2.4 |
| ADM-002 | S2 | OA, SA | Telecallers page; create form; created (3) | `adm-002-create-telecaller.md` | 03 §2.2 |
| ADM-003 | S2 | OA, SA | search; edit; duplicate Employee ID error (3) | `adm-003-edit-telecaller.md` | 03 §2.2 |
| ADM-004 | S2 | OA, SA | Users re-send link panel (1) | `adm-004-resend-set-password-link.md` | 03 §2.2 |
| ADM-005 | S10 | OA, SA | deactivate dialog with open work; result (2) | `adm-005-deactivate-telecaller.md` | 03 §3 |
| ADM-006 | S10 | OA, SA | reassign open work (1) | `adm-006-reassign-open-work.md` | 03 §3 |
| ADM-007 | S10 | SA | move-team dialog (1) | `adm-007-move-team.md` | 03 §3 |
| ADM-008 | S10 | OA, SA | reactivated (1) | `adm-008-reactivate-telecaller.md` | 03 §3 |
| ADM-009 | S10 | SA | manager deactivate with replacement (2) | `adm-009-deactivate-manager.md` | 03 §3.4 |
| CNS-001 | S7 | CO | My leads list (1) | `counselor/cns-001-handed-over-leads.md` | 03 §4.2 |
| CNS-002 | S7 | CO | lead detail (1) | `counselor/cns-002-open-a-lead.md` | 03 §4.3 |
| CNS-003 | S7 | CO | link suggestions; linked (2) | `counselor/cns-003-link-student.md` | 03 §4.3 |
| CNS-004 | S7 | CO | return form; returned (2) | `counselor/cns-004-return-a-lead.md` | 03 §4.3 |
| CNS-005 | S7 | CO, OA | converted milestones; admin unlink (2) | `counselor/cns-005-conversion.md` | 03 §4.3 |
| CNS-006 | S7 | BDM | BDM meeting-request view (1) | `counselor/cns-006-bdm-meeting-requests.md` | 03 §4.4 |

## Self-review (S1)
- Every one of the 82 IDs in analysis §3 has exactly one record above and one row in the progress tracker.
- Each session lists its features; S2–S10 together cover all 82 (S2 4, S3 10, S4 11, S5 11, S6 13, S7 13, S8 5, S9 10, S10 5 = 82).
- Owner answers D1–D6 are reflected in S2 (personas), S7 (conversion), S8 (alerts), S11 (demo accounts).
