# School CRM User Documentation — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans. Work one module session at a time, in this
> plan's order (later sessions rely on data created earlier). Steps use checkbox (`- [ ]`) syntax. Tick them here and
> update `docs/school-crm/documentation-progress.md` at the end of every session.

**Goal:** Produce verified end-user, administrator and role-based documentation for the EduSphere **School CRM**, with
screenshots captured by Playwright from the running app. The scope is all seven `/school/*` portals plus the Overseas /
Super Admin school-management screens.

**Architecture:**
- **Feature files.** One Markdown file per Doc ID (template below):
  - school users: `docs/school-crm/user-manual/<module>/`
  - Overseas Admin / Super Admin / Counselor: `docs/school-crm/admin-manual/`
- **Screenshots.** Stored in `docs/school-crm/screenshots/<module>/` and indexed in `docs/school-crm/screenshot-index.md`.
- **Source of behaviour.** Behaviour comes from the code reviewed in Phase 1 (`documentation-analysis.md` + `discovery/`) and is confirmed in the browser before it is written down.
- **Reproducibility.** Repeatable Playwright capture specs (test-only) make every screenshot reproducible.

**Tech stack:** Next.js 15 / FastAPI / PostgreSQL via Docker Compose; Playwright `^1.62.1` (Chromium) for capture; the
`browser-use` skill for exploration; the `webapp-testing` skill for scripted checks; Markdown.

**Spec:** `docs/school-crm/documentation-analysis.md`, which gives the feature inventory, roles, routes, APIs, test data and
open questions. Field-level evidence is in `docs/school-crm/discovery/01..04`.

## Global Constraints
- **Scope.** The 86 Doc IDs in §Feature records. Anything else found goes into "Discovered functionality" in the progress file, not into the manuals.
  - BDM CRM and Agent CRM are out of scope.
  - Never edit the Agent CRM files (`docs/documentation-*.md`, `docs/user-manual/`, `docs/admin-manual/`, `docs/role-guides/`, `docs/screenshots/`, `docs/faq.md`, `docs/troubleshooting.md`, `docs/screenshot-index.md`).
- **Code baseline.** `main` @ `ce1f07c2`.
  - Browser work runs against a stack built from that commit, or a later `main` recorded at the top of the progress file.
  - When `main` moves, re-check the features whose files changed (`git diff --stat ce1f07c2..<new> -- apps/`).
- **No product code changes.** Do not modify application source code. The capture tooling under `apps/web/tests/doc-capture/` and `docs/tooling/` is test or docs only.
- **Screenshot settings.** Viewport **1440 × 900**, Chromium, light colour scheme, `deviceScaleFactor: 1`, locale `en-IN`, timezone `Asia/Kolkata`.
  - Take viewport shots. `fullPage: true` is allowed only when a step needs the whole form; note it in the index.
  - Exactly one extra width, 390 px, is allowed for S360 / AUTH-009 mobile shots; note it in the index.
- **Screenshot path.** `docs/school-crm/screenshots/<module>/<NN>-<feature>-<step>.png`.
  - `NN` = two-digit sequence within the module folder.
  - Module folders: `account-access`, `dashboards`, `students`, `transfers`, `activities`, `team`, `reports`, `entitlements`, `notifications`, `parent`, `academic-team`, `career-counselor`, `psychometric-team`, `student-360`, `portfolio`, `admin-schools`.
- **Never show passwords, tokens or keys.**
  - Mask every password input, the dev-only "Demo accounts" card and every "Development only" box with Playwright `mask`. The existing `shoot()` does this.
  - Never put an invite or reset URL with a token in a doc or a screenshot.
  - Never paste the seed password into any file.
- **Test data only.** Use `*@edusphere.local` (seed) or `*@example.test` addresses. Every school, student and person created for the docs is prefixed `Docs `. No real people's data.
- **VERIFICATION REQUIRED.** Anything not confirmed in the browser is written as **VERIFICATION REQUIRED** and left out of the numbered steps.
- **Writing style.**
  - Simple English, numbered steps.
  - Bold UI labels exactly as on screen.
  - One feature per file; the feature file template below is mandatory.
- **Terminology** (use exactly):
  - Roles: **School Coordinator** (short form "Coordinator" after first use), **Principal**, **Teacher**, **Parent**, **Academic Team**, **Career Counselor**, **Psychometric Team**, **Overseas Admin**, **Super Admin**, **Counselor** (Overseas).
  - Partnership: **partner school**, **partnership tier** (Bronze / Silver / Gold / Platinum), **entitlement**.
  - Students and identifiers:
    - **student**: a roster entry; students have no login.
    - **Student ID**: the 8-character code. **School ID**: the 8-character school code.
  - Two kinds of portfolio:
    - **school portfolio**: the schools assigned to a specialist.
    - **Digital Portfolio**: a student's achievements.
  - Work items: **activity**, **result** (Draft / Verified / Published), **record** (career guidance / counselling), **assessment** (psychometric), **skills batch**, **funding case**, **transfer request**.
  - Interface: **360° view**, **sidebar**.
- **Capture helpers (from S2).** Every school spec calls `noPrefetch(context)` before navigating, because open Next.js prefetch streams stall screenshots on the docs stack. Long cards use `shoot(..., { element })` and messages use `shoot(..., { center })`. Passwords come only from `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`. School codes and emails pass between specs through `DOCS_SCHOOL_FILE` (JSON, scratchpad only).
- **Docker.** The owner approved (2026-10-05) Claude starting, seeding and resetting the `schooldocs` stack only. Never touch other compose projects ([[user-controls-docker-lifecycle]]).
- **Git.**
  - Commit on the docs-only branch `docs/school-crm-user-guide`, using the message style `docs: add <module> School CRM guide`.
  - Stage explicit paths only:
    - `docs/school-crm/`
    - `apps/web/tests/doc-capture/school/`
    - the two shared tooling files, when changed in S2
  - Never stage `graphify-out/` or untracked owner files.
  - The owner pushes.

## Review Focus
1. **Same screen, different role.** STU-006, STU-008, S360-001, PORT-001 and RPT-* behave differently by role: scope, hidden sections, editability. Every such feature file has a "What each role sees" table, and the session captures at least one screenshot per differing role.
2. **Tier-denied states.** Every gated write in a feature must document the 403 message the user sees. Capture at least one denial per message type: no tier, expired, not included. Use the Docs Bronze / No-Tier / Expired schools from S2.
3. **Secrets in screenshots.**
   - Before committing, open every new PNG and confirm that no password, invite or reset token or development box is readable.
   - Viewport shots exclude the browser chrome, so the URL bar is not captured.
   - Mailpit pages are never screenshotted.
4. **Time-dependent behaviour.**
   - Things that depend on the date: past and future activities, "Renewal due" (≤ 60 days), expired tier, invite expiry (7 days), welcome links (72 h), attendance future-date blocking, IST dates.
   - Create such data relative to the capture date, and state the capture date in the index.
5. **Wrong-portal rendering.** Never document or screenshot a page under another role's label (§5.3 of the analysis), except deliberately in AUTH-008 / SADM-011. Each session captures as the role that owns the page.

---

## File structure (created across sessions)

```
docs/school-crm/
  documentation-analysis.md        (Phase 1, done S1)
  documentation-plan.md            (this file, S1)
  documentation-progress.md        (tracker, S1)
  screenshot-index.md              (skeleton S1; filled S2+)
  discovery/01..04-*.md            (evidence appendices, S1)
  user-manual/
    README.md                      (index, S11)
    account-access/   auth-001-sign-in.md … auth-009-find-your-way-around.md
    dashboards/       dash-001-… dash-007-…
    students/         stu-001-… stu-009-…
    transfers/        xfer-001-… xfer-003-…
    activities/       act-001-… act-005-…
    team/             team-001-… team-003-…
    reports/          rpt-001-… rpt-006-…
    entitlements/     ent-001-… ent-002-…
    notifications/    notif-001-… notif-002-…
    parent/           par-001-…
    academic-team/    acad-001-… acad-007-…
    career-counselor/ car-001-… car-011-…
    psychometric-team/ psy-001-… psy-004-…
    student-360/      s360-001-…
    portfolio/        port-001-… port-005-…
  admin-manual/
    README.md                      (S11)
    sadm-001-… sadm-011-…
  role-guides/                     (S11)
    school-coordinator.md  principal.md  teacher.md  parent.md
    academic-team.md  career-counselor.md  psychometric-team.md
    overseas-admin-schools.md  super-admin-schools.md
  faq.md                           (S11)
  troubleshooting.md               (S11)
  documentation-review-report.md   (S12)
  screenshots/<module>/NN-<feature>-<step>.png
apps/web/tests/doc-capture/school/ (capture specs, test-only, S2+)
```

Image links:
- From a user-manual feature file: `../../screenshots/<module>/<file>.png`.
- From the admin manual: `../screenshots/admin-schools/<file>.png`.
- From the role guides: `../screenshots/<module>/<file>.png`.

### Feature file template (every feature)
```markdown
# <Feature name>
> Doc ID: DOC-SCH-XXX-NNN · Verified on <date> against `main` @ <commit> · Roles: <roles>

## Purpose
## Who Can Use This Feature
## Prerequisites
(include the partnership tier needed, if any)
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
Add a **What each role sees** table after "Who Can Use This Feature" whenever the roles differ.

---

## Sessions

### Dependency order
- **S2** creates the schools and staff, and the stack plus tooling. Every other session depends on it.
- **S3** creates the invited accounts, which **S4–S10** need.
- **S4** creates the students, which **S5–S10** need.
- **S6** needs an active academic year (owner, U3) and a second school with a coordinator (from S2).
- **S9** needs the Gold+ school students from S4.
- **S10** reads data from all earlier sessions.
- **S11** uses only existing screenshots.
- **S12** reviews everything.

**Rerun rule.** Capture specs create their data through the UI, so a rerun needs a fresh DB:
1. `down -v`, `up -d`, seed (owner).
2. Rerun the specs in session order (`sch-s2` → …).
3. To iterate on one session, restore a `pg_dump` snapshot taken at the end of the previous session. Snapshots stay in the session scratchpad only.

### Standard session loop (S2–S10)
- [ ] **L1** Read `documentation-analysis.md`, this plan, `documentation-progress.md`, `screenshot-index.md`, and the relevant `discovery/` sections.
- [ ] **L2** Fetch `origin/main`. If it has moved past the recorded baseline, list the changed files touching this session's routes and re-review them ([[recheck-main-before-building]]). Ask the owner to confirm the docs stack is up and seeded. Record the web URL and commit in the progress file.
- [ ] **L3** Explore each feature in the browser (`browser-use` skill) as each relevant role. Note labels, fields, messages and states. Tick "Browser Verified" only for what was actually seen.
- [ ] **L4** Write or extend `apps/web/tests/doc-capture/school/sch-sN-<module>.capture.ts`, then run it. Open every PNG and check that it is readable, shows the correct state and contains no secrets.
- [ ] **L5** Write one feature file per Doc ID using the template. Mark unconfirmed points **VERIFICATION REQUIRED**.
- [ ] **L6** Run `node docs/tooling/check-doc-links.mjs docs/school-crm` and fix any broken links.
- [ ] **L7** Update `screenshot-index.md` and `documentation-progress.md`: status columns, unresolved items, discovered functionality, session log.
- [ ] **L8** Report to the owner. Commit only the explicit paths. The owner pushes.

### S1 — Master planning — DONE 2026-10-05
- [x] Graphify orientation; four discovery passes (account / principal / teacher / parent, coordinator, specialists + 360 + portfolio, admin).
- [x] `documentation-analysis.md`, this plan, `documentation-progress.md`, `screenshot-index.md` skeleton, `discovery/` appendices.

### S2 — Environment, capture tooling, school administration (creates schools and staff) — DONE 2026-10-05
Features: DOC-SCH-SADM-001, 002, 003, 004, 005, 010, 011 (7).
- [x] **S2.1** Owner confirms the stack, using the same pattern as the Agent CRM docs stack:
  - A dedicated worktree `.claude/worktrees/school-docs`, compose project `schooldocs`, web `:3020` and api `:8020`.
  - Mailpit through an untracked `docker-compose.docs.yml` (`SMTP_HOST=mailpit`, port 1025, no TLS). Never run the docs stack against the real SMTP in `.env`.
  - Seeded from `ce1f07c2`.

  Record the seed password only as the `DOCS_PASSWORD` environment variable, and a new random `DOCS_TEST_PASSWORD` in the session scratchpad only.
- [x] **S2.2** Tooling (test-only):
  - (a) Add an optional `root` to `shoot()` in `apps/web/tests/doc-capture/shoot.ts` (default unchanged, so Agent specs keep working), plus `export const SCHOOL_ROOT = path.resolve(__dirname, "../../../../docs/school-crm/screenshots")`.
  - (b) Add `inviteLink(to, after)` next to `mailLink`. It matches `/school/invite/[A-Za-z0-9_-]+/accept` in the Mailpit text body and returns the path only.
  - (c) Create the `apps/web/tests/doc-capture/school/` folder. In it, call `signIn(page, email, kind, /\/school\//)` for school roles and `/\/overseas\/admin\//` for OA.
  - (d) In `docs/tooling/check-doc-links.mjs`, take an optional root argument. With an argument, scan `<root>/user-manual`, `<root>/admin-manual`, `<root>/role-guides`, `<root>/faq.md`, `<root>/troubleshooting.md` and `<root>/screenshot-index.md`. With no argument, keep today's paths.

  Run the existing Agent capture spec list once with `--list` to prove nothing broke.
- [x] **S2.3** Masking check: capture `account-access/01-login-page.png`, open it, and confirm no password or demo card is readable.
- [x] **S2.4** Run the standard loop for the S2 features as Overseas Admin.
  - Create **Docs Bronze School**, **Docs No-Tier School**, **Docs Renewal School** (Gold, valid +30 days), **Docs Expired School** (Gold, valid until yesterday) and **Docs Platinum Two** (Platinum, needed for transfers and the multi-school parent).
  - Create the bulk CSV fixture (D3).
  - Create staff `Docs AT`, `Docs CC` and `Docs PT` (portfolio: Sunrise + Docs Platinum Two) and `Docs Empty Portfolio CC` (no schools).
  - Upgrade, then downgrade, Docs Bronze School (tier notices for S10).
  - As Super Admin, capture "Workspace not found" (SADM-011).
  - For SADM-010, first code-review the Users page re-send panel (U12).
- [x] **S2.5** Take a `pg_dump` snapshot (scratchpad).

### S3 — Account access and Team (creates invited accounts)
Features: DOC-SCH-AUTH-001..009, DOC-SCH-TEAM-001..003 (12).
- [ ] Standard loop.
  - Use the S2 welcome links (Mailpit) for AUTH-003, as the Docs Platinum Two Coordinator.
  - As the Sunrise Coordinator, invite `Docs Principal`, `Docs Teacher A`, `Docs Teacher B` and `Docs Parent` (TEAM-001), and accept some of them (AUTH-002), leaving one pending.
  - Deactivate `Docs Teacher B` (TEAM-003) for AUTH-008.
  - Capture "This invite has already been used…" by reusing an accepted link.
  - The expired-invite state needs a time shift. Ask the owner, or document it as VERIFICATION REQUIRED.
  - Verify U1 (session length) and U2 (reset email); the latter decides how AUTH-004 is written.
  - Mobile menu shot at 390 px (AUTH-009).

### S4 — Students and roster
Features: DOC-SCH-STU-001..008 (8).
- [ ] Standard loop as the Sunrise Coordinator.
  - Add students in Grades 8–12 (≥ 2 each) with sections and roll numbers. Assign them to Docs Teacher A.
  - Give one student a parent email for a new parent (invite sent) and one an existing parent (linked).
  - Trigger the roll-number clash, the non-parent email error and the link-parent errors.
  - Run the bulk CSV with mixed rows (D6), and check U13.
  - Photo upload, replace and remove, including the 2 MB and wrong-type errors.
  - Progress report PDF download as CO, PR and PA. Note the file name and do not commit the PDF.
  - Student page as CO, PR and TE (role table).
  - Check U4 and U5 once.

### S5 — Activities, attendance and feedback
Features: DOC-SCH-ACT-001..005, DOC-SCH-SADM-009 (6).
- [ ] Standard loop.
  - Schedule a future typed activity (parents notified; check U9 in the parent's notifications), a past typed activity, a past untyped activity and, at Docs Bronze School, a campus visit (tier denied).
  - Mark attendance, then submit feedback once and capture the duplicate error.
  - Read the feedback as the Principal (ACT-004) and as OA (SADM-009, school filter).
  - Daily attendance as Docs Teacher A across three past days and today, covering the future-date note, the unsaved-changes prompt and the partial save.

### S6 — Transfers and promotion
Features: DOC-SCH-XFER-001..003, DOC-SCH-SADM-007, DOC-SCH-STU-009 (5).
- [ ] **S6.1** Owner decision (2026-10-05): Claude writes the exact `POST /overseas-admin/academic-years` + `PATCH /overseas-admin/academic-years/{id}` (activate) calls, to be run as Overseas Admin; the **owner runs them** on the docs stack. Read `apps/api/app/api/admin.py:1574-1660` for the body shape first. STU-009 says the year is set up by EduSphere.
- [ ] Standard loop.
  - Sunrise CO requests an outgoing transfer to Docs Platinum Two. Docs Platinum Two CO requests an incoming Sunrise student by Student ID (neutral success).
  - Cancel one request.
  - OA approves one transfer (warnings visible: pending parent invite; destination with no staff school portfolio) and rejects one with a note.
  - Capture the notifications for both Coordinators.
  - Docs Platinum Two CO links the existing Docs Parent to a student (D17, multi-school parent).
  - Promotion: promote, hold back, mixed result, Grade 12 hint, label mismatch.

### S7 — Academic Team and Digital Portfolio
Features: DOC-SCH-ACAD-001..007, DOC-SCH-PORT-001..005 (12).
- [ ] Standard loop.
  - `school.academic1` uploads a Draft, `school.academic2` verifies it, and academic1 sees "Ask another…".
  - academic2 publishes a result uploaded by academic1.
  - Include marks below 40 % and at or above 85 % (for RPT-004).
  - Bulk CSVs for results, test prep and language (mixed rows).
  - Test prep: start, then record the score. Language: start, then mark certified.
  - Portfolio:
    - entries in several sections
    - Skill India certification (including the validation errors)
    - internship with tracking and a certificate upload (≤ 5 MB PDF; a > 5 MB file for the error)
    - personal statement
    - delete confirm
    - the Platinum-only notice at Docs Bronze School
  - Teacher editing the portfolio of an assigned student (U14).

### S8 — Career Counselor
Features: DOC-SCH-CAR-001..011 (11).
- [ ] Standard loop as `school.careercounselor`.
  - Records in every status path (including the follow-up date rules), and the 409 conflict (two tabs).
  - Career preferences, and a career goal in the 360° view.
  - Skills: a Soft batch (open) with enrolments in every status, sessions with attendance, and an assessment with scores; a Digital batch closed (read-only); a Digital batch at Docs Bronze School (tier denied).
  - Funding: cases moved through the stages, one closed with a reason, and the duplicate open case error.
  - Show the empty-portfolio state with `Docs Empty Portfolio CC`.

### S9 — Psychometric Team, Student 360°, overseas pathway
Features: DOC-SCH-PSY-001..004, DOC-SCH-S360-001, DOC-SCH-SADM-006, DOC-SCH-RPT-006 (7).
- [ ] Standard loop.
  - Assign assessments, attach a report URL, then record and edit the results (validation messages); bulk CSV.
  - 360° view as a school role (16 tabs) and as AT / CC / PT ("Restricted" tabs), plus one 390 px shot (U16).
  - SADM-006 as OA and as Counselor: start applications for Gold+ students, then capture the Silver / Bronze tier denial.
  - Check how the stages advance (U15). Move at least one student far enough for the Global Education funnel, recording the method used.
  - RPT-006 as CO and PR.

### S10 — Dashboards, reports, entitlements, notifications, parent, analytics
Features: DOC-SCH-DASH-001..007, DOC-SCH-RPT-001..005, DOC-SCH-ENT-001..002, DOC-SCH-NOTIF-001..002, DOC-SCH-PAR-001, DOC-SCH-SADM-008 (18). Most of these are read-only screens over data from S2–S9. If time runs short, split into **S10a** (DASH, PAR, NOTIF) and **S10b** (RPT, ENT, SADM-008).
- [ ] Standard loop. Capture:
  - each role's dashboard
  - the parent multi-school grouping
  - reports and the threshold form, including the invalid-value messages
  - the scorecards grade filter and paging
  - entitlements for Platinum, no tier and expired
  - staff and parent notifications (check U8)
  - School Analytics flags and search

### S11 — Role guides, FAQ, troubleshooting, indexes
- [ ] Write the nine role guides in `role-guides/`. Each has these sections: Role Purpose, Login, Dashboard, Menus Available, Main Activities, Daily Workflows, Restrictions, Common Problems, Related Features. Link to the feature files and reuse existing screenshots only.
- [ ] Write `faq.md` and `troubleshooting.md`. Troubleshooting uses Problem / Possible Cause / Resolution / When to Contact Administrator. Include only behaviour observed in S2–S10.
- [ ] Write the indexes `user-manual/README.md` and `admin-manual/README.md`.

### S12 — Final review
- [ ] Re-check every feature file against:
  - the code (baseline or recorded commit)
  - the permission matrix (§5)
  - the routes and APIs
  - the screenshots
  - this plan and the tracker
- [ ] Run the link check. Detect duplicate screenshots with `sha256sum docs/school-crm/screenshots/*/*.png | sort | uniq -D -w64`.
- [ ] Write `documentation-review-report.md`, with findings rated CRITICAL / HIGH / MEDIUM / LOW.
- [ ] Mark a feature COMPLETE only when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES (or N/A), Documented = YES and Reviewed = PASSED.

---

## Feature records

These records use the role abbreviations from the analysis legend. "Shots" = estimated screenshots.

**Status of every record at the end of S1:** code-reviewed at `ce1f07c2`, **browser not verified**, not documented.

"Appx" = `discovery/` file § for the field-level detail (labels, messages, file:line).

### Module AUTH — Account access & navigation (`user-manual/account-access/`, shots → `account-access/`)

**DOC-SCH-AUTH-001 — Sign in to the School portals** · S3
- Role: all 7 · Nav: `/overseas/login` (the same page for every school role)
- Preconditions: active account with a password set
- Workflow:
  1. Enter **Email** and **Password**.
  2. Click **Sign in securely**.
  3. You land on your role's dashboard (landing table, analysis §4).
- Shots (3): login page (masked); invalid credentials; wrong portal (sign in at `/it/login`)
- Validation: browser required fields; 422 list joined with "; "
- Errors: "Invalid credentials" (also shown for a deactivated account); "Use the correct EduSphere portal for this account: sign in at /overseas/login"
- Related: AUTH-002, 003, 004, 008 · File: `auth-001-sign-in.md` · Appx 01 §1.2–1.3

**DOC-SCH-AUTH-002 — Accept a school invitation and set up your login** · S3
- Role: invited PR / TE / PA · Nav: the link in the email "You're invited to join {school} on EduSphere" → `/school/invite/[token]/accept`
- Preconditions: pending invite less than 7 days old
- Workflow:
  1. Open the link.
  2. Enter **Choose a password** (≥ 10 characters).
  3. Click **Accept and set up login**.
  4. You are signed in and land on your dashboard. No success message is shown.
- Shots (3): form; used / expired invite error; short-password error
- Validation: "Password must be at least 10 characters"
- Errors: "This invite has already been used, expired, or was revoked"; "Email already exists"; "Unable to accept this invite."
- Related: TEAM-001, STU-004 · File: `auth-002-accept-an-invitation.md` · Appx 01 §1.5

**DOC-SCH-AUTH-003 — Set your first password from a welcome link** · S3
- Role: CO, AT, CC, PT · Nav: the welcome email link → `/overseas/reset-password?token=…` (**Choose a new password**)
- Preconditions: account created by OA; link less than 72 h old
- Workflow:
  1. Open the link.
  2. Enter **New password**.
  3. Click **Reset password**.
  4. You are taken to the login page; sign in.
- Shots (2): set-password form; invalid-link message
- Validation: 10–128 characters
- Errors: "Reset token is invalid or expired" + "…ask your administrator to re-send it."; missing-token text
- Related: SADM-002, 005, 010, AUTH-001 · File: `auth-003-set-your-first-password.md` · Appx 01 §1.6; 04 §2

**DOC-SCH-AUTH-004 — Forgot / reset your password** · S3
- Role: all 7 · Nav: login → **Forgot your password?** → `/overseas/forgot-password`
- Preconditions: active account
- Workflow:
  1. Enter **Email**.
  2. Click **Send reset instructions**.
  3. A neutral confirmation appears.
  4. Use the emailed reset (U2) to set a **New password**.
- Shots (3): request form; confirmation; reset form
- Validation: 10–128; 30-minute token
- Errors: "Reset token is invalid or expired"; network text
- Related: AUTH-003, 005 · File: `auth-004-forgot-password.md` · Open: U2 · Appx 01 §1.6

**DOC-SCH-AUTH-005 — Change your password** · S3
- Role: all 7 · Nav: sidebar footer **Change password** → `/account/password`
- Workflow:
  1. Enter **Current password** and **New password**.
  2. Optionally tick **Show passwords**.
  3. Click **Change password**.
  4. The message "Your password was changed." appears.
- Shots (2): form; wrong current password
- Validation: different from the current password; not only spaces; 10–128
- Errors: "Incorrect current password"; "Too many incorrect attempts…"; session expired
- Related: AUTH-004 · File: `auth-005-change-password.md` · Appx 01 §1.7

**DOC-SCH-AUTH-006 — My profile and notification settings** · S3
- Role: all 7 · Nav: sidebar footer **My profile** → `/account/profile`
- Workflow:
  1. Edit **Full name** and **Phone**.
  2. Click **Save changes**; "Your profile was updated." appears.
  3. In Notifications, tick **WhatsApp** / **SMS** (needs a valid phone).
  4. Click **Save notification settings**.
- Shots (2): profile form; notifications section
- Validation: name 2–160; phone ≤ 40; "Add a valid mobile number to your profile first"
- Related: NOTIF-001, 002 · File: `auth-006-my-profile.md` · Appx 01 §1.8

**DOC-SCH-AUTH-007 — Sign out and session expiry** · S3
- Role: all 7 · Nav: sidebar **Sign out**
- Workflow: Sign out takes you to the site home page. An expired session shows "Access unavailable" with **Return to login** (U1).
- Shots (1): expired-session card (or N/A if it cannot be reproduced)
- Related: AUTH-008 · File: `auth-007-sign-out-and-session-expiry.md` · Open: U1 · Appx 01 §1.9–1.10

**DOC-SCH-AUTH-008 — "Access unavailable" messages** · S3
- Role: all 7 · Nav: any portal page
- Cases:
  - signed out → **Return to login**
  - wrong role (e.g. Teacher on `/school/principal/reports` → "Principal role required")
  - deactivated account (sign-in "Invalid credentials"; signed-in "User unavailable")
  - another school's student ("This student is at a different institution"), unassigned student, unlinked child
- Shots (3): signed out; wrong role; other-school student
- Related: TEAM-003 · File: `auth-008-access-unavailable.md` · Appx 01 §1.11–1.12

**DOC-SCH-AUTH-009 — Find your way around** · S3
- Role: all 7 · Nav: sidebar, role pill, footer buttons, top bar; the mobile menu below 980 px
- Shots (2): sidebar per role (one composite example + a table of each role's menu); mobile menu at 390 px
- Note: the sidebar highlights nothing on sub-pages; there is no unread badge
- Related: role guides · File: `auth-009-find-your-way-around.md` · Appx 01 §1.4

### Module DASH — Dashboards (`user-manual/dashboards/`, shots → `dashboards/`)

**DOC-SCH-DASH-001 — Coordinator dashboard** · S10
- Role: CO · Nav: **Dashboard** (landing)
- Content:
  - "School at a glance": 20 KPI tiles in 4 groups, with a definitions table
  - "Your school", with **Go to student roster / bulk upload / activities / reports**
  - "Upcoming activities" (next 10)
  - "Results & guidance"
- Shots (2): KPI board; lower cards
- Errors: "This section couldn't load. Refresh to try again."
- Related: STU-001, ACT-001, RPT-002 · File: `dash-001-coordinator-dashboard.md` · Appx 02 §1

**DOC-SCH-DASH-002 — Principal dashboard** · S10
- Role: PR · Content: KPI board; "Your school" roster (Name, Grade/Class, **Timeline**); **View full reports**; "Results & guidance"
- Shots (2) · Related: STU-006, RPT-* · File: `dash-002-principal-dashboard.md` · Appx 01 §2.1

**DOC-SCH-DASH-003 — Teacher dashboard** · S10
- Role: TE · Content: "Your students" (assigned only, **View**); "Results & guidance" (assigned scope)
- Empty: "No students assigned to you yet."
- Shots (1) · Related: ACT-005, STU-006 · File: `dash-003-teacher-dashboard.md` · Appx 01 §3.1

**DOC-SCH-DASH-004 — Parent dashboard** · S10
- Role: PA · Content:
  - "My children" cards: grade, date of birth, class teacher, status row, recommended careers, **View full profile & progress**
  - grouping by school when the children are at different schools
  - "Upcoming sessions"
  - "Important notifications" + "{n} unread" (U8)
- Shots (3): single school; multi-school grouping; notifications card
- Related: PAR-001, NOTIF-002 · File: `dash-004-parent-dashboard.md` · Appx 01 §4.1, §1.13

**DOC-SCH-DASH-005 — Academic Team dashboard** · S10
- Role: AT · Content: section map (Portfolio progress, Results + Upload, Bulk results, Test preparation, Foreign language classes, Bulk test prep / language, Students) with links to the ACAD / PORT files
- Empty portfolio: "No students in your portfolio yet. Contact your Overseas Admin."
- Shots (1) · File: `dash-005-academic-team-dashboard.md` · Appx 03 §1.1

**DOC-SCH-DASH-006 — Career Counselor dashboard** · S10
- Role: CC · Content: Records, Add a record, Career preferences, Student 360° view list; sidebar Skills, Funding
- Shots (1) · File: `dash-006-career-counselor-dashboard.md` · Appx 03 §2.1

**DOC-SCH-DASH-007 — Psychometric Team dashboard** · S10
- Role: PT · Content: Assessments, Assign an assessment, Bulk entry, Student 360° view list
- Shots (1) · File: `dash-007-psychometric-team-dashboard.md` · Appx 03 §3.1

### Module STU — Students & roster (`user-manual/students/`, shots → `students/`)

**DOC-SCH-STU-001 — View the student roster** · S4
- Role: CO · Nav: sidebar **Students**
- Content: columns Student ID, Name, Grade/Class, Section, Roll no., Parent, Actions (**Edit**, **Link parent**, **Profile & timeline**)
- There is no search, filter, sort or paging, and the Parent column shows only pending invites. Say both plainly.
- Shots (2): roster; empty state (Docs Platinum Two before students)
- Related: STU-002..006 · File: `stu-001-view-the-roster.md` · Open: U4 · Appx 02 §2

**DOC-SCH-STU-002 — Add one student** · S4
- Role: CO · Nav: **Students** → card **Add one student**
- Preconditions: an active academic year exists, for the student's year (seed)
- Workflow:
  1. Fill the Identity, Class placement, Contact, and Studies & interests groups.
  2. Click **Add student**.
  3. A success message appears, plus a parent note: linked / invite sent / pending.
- Fields: about 17 (table in appx 02 §2); only **Full name** is required
- Validation: grade level 1–12; roll number unique per grade + section + year; mobile format; list ≤ 20 items × 80 characters; teacher must be at your school; parent email must not belong to a non-parent account
- Shots (3): form; success with invite; roll-number conflict
- Related: STU-003, 004, TEAM-001 · File: `stu-002-add-a-student.md` · Open: U5 · Appx 02 §2

**DOC-SCH-STU-003 — Edit a student (incl. teacher assignment)** · S4
- Role: CO · Workflow: Roster **Edit** → change fields (**Assigned Teacher**; inactive teachers are marked "(inactive)") → **Save changes** → "Student updated."
- Shots (1) · Errors: same as STU-002; "This student is at a different institution"
- Related: STU-002, ACT-005 · File: `stu-003-edit-a-student.md` · Appx 02 §2

**DOC-SCH-STU-004 — Link a parent to a student** · S4
- Role: CO · Workflow: **Link parent** → **Parent's email** → **Link parent** → "Parent linked to this student."
- Errors: "parent_email must belong to an existing Parent account" (shown with the field label); "This parent is already linked to this student"
- Shots (2): form; error
- Related: TEAM-001, AUTH-002, DASH-004 · File: `stu-004-link-a-parent.md` · Appx 02 §2

**DOC-SCH-STU-005 — Upload the roster in bulk (CSV)** · S4
- Role: CO · Nav: Dashboard **Go to bulk upload** or the roster link → `/school/coordinator/students/bulk-upload`
- Workflow:
  1. **Download template (.csv)**.
  2. Fill it in, using `;` as the separator inside list cells.
  3. **Filled-in roster file** → **Upload roster**.
  4. Read "Upload result" (Added / Rejected per row).
- Fields: 17 columns (column reference)
- Validation: row-level messages (appx 02 §3)
- Tips: delete the example row; row numbers start after the header
- Shots (3): template card + column reference; mixed result; no-file error
- Related: STU-002 · File: `stu-005-bulk-upload-roster.md` · Open: U13 · Appx 02 §3

**DOC-SCH-STU-006 — Student profile and journey timeline** · S4
- Role: CO, PR, TE (role table) · Nav:
  - CO: roster **Profile & timeline**
  - PR: dashboard **Timeline** / scorecard name
  - TE: dashboard **View**
- Content:
  - header facts, **Open 360° view**
  - Request a transfer (CO only)
  - Grade history, Transfer history
  - Journey timeline
  - Digital Portfolio (see PORT)
  - Progress report (CO / PR), Progress scorecard (CO / PR), Funding support (CO / PR; not shown to teachers)
- Shots (4): header; timeline; scorecard + funding (CO); teacher view
- Related: STU-007, 008, S360-001, PORT-001, XFER-001 · File: `stu-006-student-profile-and-timeline.md` · Appx 02 §4; 01 §2.7, §3.3

**DOC-SCH-STU-007 — Student photo** · S4
- Role: CO · Workflow: **Upload a photo (JPEG or PNG, up to 2 MB)** → "Photo saved."; **Replace photo**; **Remove photo** → **Confirm remove**
- Errors: "Photo must be a JPEG or PNG image"; "Photo must be at most 2 MB"; "photo could not be read as a valid JPEG or PNG image"
- Shots (2) · File: `stu-007-student-photo.md` · Appx 02 §4

**DOC-SCH-STU-008 — Download a student progress report (PDF)** · S4
- Role: CO, PR, PA · Workflow: **Download progress report (PDF)** → "Report downloaded." (file `progress-report.pdf`)
- Errors: session expired; "Something went wrong on our side. Please try again."
- Shots (1) · Related: PAR-001 · File: `stu-008-progress-report-pdf.md` · Appx 02 §4; 01 §2.7

**DOC-SCH-STU-009 — Promote or hold back students** · S6
- Role: CO · Nav: sidebar **Promotion**
- Preconditions: an **active academic year** set by EduSphere (U3); students have a grade level
- Workflow:
  1. Filter by **Grade level**.
  2. Tick students and choose **Promote** or **Hold back** (optionally **New label**).
  3. **Review changes (n)** → **Confirm promotion**.
  4. Read the summary "Done for {Year}: …".
- Validation: Grade 12 cannot be promoted; grade level must be set; label must match the level; at most 500 students per action
- Errors: "No active academic year. Ask an Overseas Admin to activate one."; concurrency 409s
- Tips: promotion clears roll numbers
- Shots (4): no-active-year; list; confirm; mixed result
- Related: STU-006 · File: `stu-009-promote-students.md` · Open: U3 · Appx 02 §7

### Module XFER — Student transfers (`user-manual/transfers/`, shots → `transfers/`)

**DOC-SCH-XFER-001 — Request a transfer out** · S6
- Role: CO · Nav: Students → **Profile & timeline** → **Request a transfer**
- Workflow:
  1. Choose **Destination school**.
  2. Optionally add **Reason (optional)** (≤ 500).
  3. Click **Request transfer**.
  4. The message "Transfer request sent for review…" appears and the "Transfer requested" badge shows.
- Errors: "Choose a school."; "A transfer request is already pending for this student"; rate limit 30 per hour; 50 open
- Shots (2) · Related: XFER-003, SADM-007 · File: `xfer-001-request-a-transfer-out.md` · Appx 02 §6

**DOC-SCH-XFER-002 — Request a student from another school** · S6
- Role: CO · Nav: **Transfers** → "Request a student from another school"
- Workflow: **Student ID** (8 characters) + reason → **Request student** → the same neutral message for every valid ID
- Validation: "Enter all 8 characters of the Student ID (digits 0-9 and letters A-F)."
- Shots (2) · File: `xfer-002-request-a-student-in.md` · Appx 02 §6

**DOC-SCH-XFER-003 — Track and cancel transfer requests** · S6
- Role: CO · Nav: **Transfers** → list
- Workflow: filter **Status** → **Load more** → **Cancel** a pending request → "Request cancelled."
- Content: incoming requests show "Student ID {code}" until approved; rejected requests show the "Admin note"
- Errors: "This transfer request has already been decided"
- Shots (2) · Related: NOTIF-001 · File: `xfer-003-track-and-cancel-transfers.md` · Appx 02 §6

### Module ACT — Activities, attendance & feedback (`user-manual/activities/`, shots → `activities/`)

**DOC-SCH-ACT-001 — Schedule an activity** · S5
- Role: CO · Nav: sidebar **Activities**
- Workflow: **Title**, **Date & time**, **Entitlement category (optional)** → **Schedule activity** → "{Title} scheduled."; parents are notified
- Tier: typed activities need their service (a campus visit needs Platinum); untyped activities need any valid tier
- Errors: three tier 403 messages; "title and scheduled_at are required"
- Tips: activities cannot be edited or deleted
- Shots (3): form; list; tier denied
- Related: ACT-002, 003, ENT-002, NOTIF-002 · File: `act-001-schedule-an-activity.md` · Open: U5, U9 · Appx 02 §8

**DOC-SCH-ACT-002 — Mark attendance for an activity** · S5
- Role: CO · Workflow: **Mark attendance** → untick absent students (everyone starts ticked) → **Save attendance** → "Attendance recorded for N student(s)."
- Tips: re-saving overwrites the earlier marks
- Shots (2) · File: `act-002-mark-activity-attendance.md` · Appx 02 §8

**DOC-SCH-ACT-003 — Give feedback on a completed activity** · S5
- Role: CO · Nav: **Feedback** (or Activities **Give feedback**)
- Workflow:
  1. Filter **Show**.
  2. **Give feedback**.
  3. Fill **Overall rating**, **School satisfaction**, **Trainer / Counsellor (optional)**, **Feedback**, **Suggestions (optional)**.
  4. **Submit feedback** → "Feedback saved for {title}."
- Validation: "Feedback: Must not be blank"; ≤ 5000
- Errors: "Feedback had already been submitted for this activity; your text was not saved…"; "Feedback opens once the activity has taken place"
- Tips: feedback cannot be changed after you submit it
- Shots (3) · Related: ACT-004, SADM-009 · File: `act-003-give-activity-feedback.md` · Appx 02 §9

**DOC-SCH-ACT-004 — View activity feedback** · S5
- Role: PR · Nav: sidebar **Feedback** → filter **Show** → **View feedback**; **Load more**
- Shots (2) · File: `act-004-view-activity-feedback.md` · Appx 01 §2.4

**DOC-SCH-ACT-005 — Take daily class attendance** · S5
- Role: TE · Nav: sidebar **Attendance**
- Workflow:
  1. Choose **Date** → **Show**.
  2. Select **Present / Absent / Late / Excused** for each student, or **Mark all present** (fills only the unmarked students).
  3. **Save attendance** → "Attendance saved for {n} student(s) on {date}."
- Validation: "Choose a status for at least one student."; no future dates
- Errors: "Your class list changed since this page was opened…"; tier expired / no tier; "{date} is in the future…"
- Tips: the leave-page prompt protects unsaved marks; a partial save is allowed
- Shots (4) · Related: DASH-003, PAR-001 · File: `act-005-daily-class-attendance.md` · Appx 01 §3.2

### Module TEAM — Team & invitations (`user-manual/team/`, shots → `team/`)

**DOC-SCH-TEAM-001 — Invite a Principal, Teacher or Parent** · S3
- Role: CO · Nav: sidebar **Team** → "Invite a team member"
- Workflow: **Role**, **Full name**, **Email** → **Send invite** → "Invite sent to {email}. It's valid for 7 days." (with the email-not-configured variant)
- Errors: "Email already exists"; "email and full_name are required"
- Tips: invites cannot be resent or revoked
- Shots (2) · Related: AUTH-002, STU-004 · File: `team-001-invite-a-team-member.md` · Appx 02 §10

**DOC-SCH-TEAM-002 — View your team and pending invites** · S3
- Role: CO · Content: "Your team" table (Name, Email, Role, Status, Action) and "Pending invites" table (Expires)
- Notes: parents appear only once linked to a student
- Empty: "It's just you so far…"
- Shots (2) · File: `team-002-view-your-team.md` · Appx 02 §10

**DOC-SCH-TEAM-003 — Deactivate or reactivate a team account** · S3
- Role: CO · Workflow: **Deactivate** / **Reactivate** (no confirmation) → "{name} deactivated."
- Effects: the user cannot sign in; a deactivated teacher keeps assigned students; a multi-school parent is blocked everywhere
- Shots (1) · Related: AUTH-008 · File: `team-003-deactivate-or-reactivate.md` · Appx 02 §10

### Module RPT — Reports, analytics & global education (`user-manual/reports/`, shots → `reports/`)

**DOC-SCH-RPT-001 — Download the school report (PDF)** · S10 · CO, PR · **Reports** → **Download school report (PDF)** → "Report downloaded." · Shots (1) · `rpt-001-school-report-pdf.md` · Appx 02 §11

**DOC-SCH-RPT-002 — School summary** · S10
- Roles: CO, PR · Content: metric tiles (Students, Teachers, Parents, Pending invites), "Students by grade", "Service delivery completion", "Activities & attendance", with a definitions table
- Shots (2) · `rpt-002-school-summary.md` · Appx 02 §11

**DOC-SCH-RPT-003 — Grade-wise comparison** · S10
- Roles: CO, PR · Content: a table of metrics by grade; "Estimate:" notes for estimated metrics
- Shots (1) · `rpt-003-grade-wise-comparison.md` · Appx 02 §11

**DOC-SCH-RPT-004 — Student development, at-risk students and top performers** · S10
- Roles: CO, PR · Workflow: set **At risk below (%)** / **Top performer from (%)** → **Update thresholds**; read the lists (max 50)
- Validation: "Thresholds must be between 0 and 100. Showing the defaults."; "At-risk must be below the top-performer threshold…"
- Shots (2) · `rpt-004-student-development.md` · Appx 02 §11

**DOC-SCH-RPT-005 — Student progress scorecards** · S10
- Roles: CO, PR · Workflow: **Grade** → **Show**; paging "← Previous / Next →"
- Content: 12 areas with the states Completed / In progress / Not started / Not in plan / Not tracked yet
- Shots (2) · `rpt-005-student-scorecards.md` · Appx 02 §11

**DOC-SCH-RPT-006 — Global education pipeline** · S9
- Roles: CO, PR · Nav: sidebar **Global Education**
- Content: funnel (6 stages); "Not tracked yet" tiles; students table with **Grade** filter and paging
- Note: application details are handled by EduSphere
- Shots (2) · Related: SADM-006 · `rpt-006-global-education.md` · Open: U15 · Appx 02 §12; 01 §2.3

### Module ENT — Partnership entitlements (`user-manual/entitlements/`, shots → `entitlements/`)

**DOC-SCH-ENT-001 — View your school's partnership entitlements** · S10
- Roles: CO, PR · Nav: sidebar **Entitlements**
- Content: "Plan: {Tier} Partner — valid until {date}"; Service / Included / Used
- No-tier message: "No partnership tier has been set for your school yet…"
- Expired tier: no warning is shown (document as a tip)
- Shots (3): Platinum; no tier; expired · `ent-001-view-entitlements.md` · Appx 02 §13

**DOC-SCH-ENT-002 — Partnership tiers explained** · S10 · reference for all roles
- Content: the tier → services table (analysis §1.4), the three denial messages and what they mean, grandfathering after a downgrade, and who to contact (Overseas Admin)
- Shots (1): an example denial (reused from ACT-001)
- `ent-002-partnership-tiers-explained.md` · Appx 03 §0.4

### Module NOTIF — Notifications (`user-manual/notifications/`, shots → `notifications/`)

**DOC-SCH-NOTIF-001 — Notifications for school staff** · S10
- Roles: CO, PR · Nav: sidebar **Notifications**; **Open** marks a notice read
- Triggers: tier change; transfer approved / joined / not approved; password reset requested
- Shots (2) · Related: SADM-003, XFER-003 · `notif-001-staff-notifications.md` · Appx 02 §14; 01 §2.6

**DOC-SCH-NOTIF-002 — Notifications for parents** · S10
- Role: PA · Nav: sidebar **Notifications** (table) + dashboard card
- Triggers (table): activity scheduled, career record, psychometric, test prep, language, result published, overseas application, funding, skills, transfer
- Open items: U8 (badges never clear), U9 (time zone)
- Shots (2) · `notif-002-parent-notifications.md` · Appx 01 §4.4

### Module PAR — Parent (`user-manual/parent/`, shots → `parent/`)

**DOC-SCH-PAR-001 — Your child's profile and progress** · S10
- Role: PA · Nav: Dashboard → **View full profile & progress**
- Content:
  - header; status row
  - Career guidance, Counselling, Recommended careers, Psychometric assessment
  - Academic results (published only), Activities, Skills, Upcoming sessions
  - Funding support, Grade history, Transfer history, Journey timeline, Digital Portfolio
  - **Download progress report (PDF)**, **Open 360° view**
- Shots (4) · Related: DASH-004, S360-001, STU-008 · `par-001-child-profile-and-progress.md` · Appx 01 §4.2

### Module ACAD — Academic Team (`user-manual/academic-team/`, shots → `academic-team/`)

**DOC-SCH-ACAD-001 — Portfolio progress** · S7 · AT · Content: Student / School / Results / Avg % (the average includes drafts) · Shots (1) · `acad-001-portfolio-progress.md` · Appx 03 §1.1.a

**DOC-SCH-ACAD-002 — Upload a result as Draft** · S7
- Role: AT · Workflow:
  1. **Student** (searchable).
  2. Fill **Academic year**, **Term**, **Subject**, **Maximum marks**, **Marks obtained**, **Grade**, **Teacher remarks**.
  3. **Save as Draft** → "{Subject} result saved as Draft."
- Validation: required fields; remarks ≤ 2000. Marks are **not** range-checked here, so check them yourself.
- Shots (2) · Open: U5 · `acad-002-upload-a-result.md` · Appx 03 §1.1.c

**DOC-SCH-ACAD-003 — Verify and publish results** · S7
- Role: AT (not the uploader) · Workflow: **Verify** → "Result verified."; **Publish** → "Result published."; the parent is notified
- Two-person rule: the uploader sees "Ask another Academic Team member to verify / publish"
- Errors: no skipping a stage; "A different Academic Team member must perform this step…"
- Shots (3): uploader view; verify; publish
- Related: PAR-001, RPT-004 · `acad-003-verify-and-publish-results.md` · Appx 03 §1.1.b

**DOC-SCH-ACAD-004 — Bulk entry: results (CSV)** · S7
- Role: AT · Workflow: expand "Bulk entry — results (CSV)" → **Download the pre-filled template (.csv)** → fill in → upload → "Upload result"
- Limits: 1 MB, 500 rows, UTF-8; the same file is never added twice
- Errors: file-level and row-level lists
- Shots (2) · `acad-004-bulk-results.md` · Appx 03 §1.1.d

**DOC-SCH-ACAD-005 — Test preparation (IELTS / SAT)** · S7
- Role: AT · Workflow: **Start test preparation** (Student, Test, Target score) → **Start preparation**; then **Record score** → "Result recorded."
- Tier: Gold · Shots (2) · `acad-005-test-preparation.md` · Appx 03 §1.1.e

**DOC-SCH-ACAD-006 — Foreign language classes** · S7
- Role: AT · Workflow: **Start language classes** (Student, Language, Level) → **Start classes**; **Mark certified** → "Marked certified."
- Tier: Gold · Shots (2) · `acad-006-foreign-language-classes.md` · Appx 03 §1.1.f

**DOC-SCH-ACAD-007 — Bulk entry: test preparation and language classes** · S7 · AT · same flow as ACAD-004, with the columns per target · Shots (1) · `acad-007-bulk-test-prep-and-language.md` · Appx 03 §1.1.d

### Module CAR — Career Counselor (`user-manual/career-counselor/`, shots → `career-counselor/`)

**DOC-SCH-CAR-001 — Add a career guidance / counselling record** · S8
- Role: CC · Nav: Dashboard → "Add a record"
- Workflow:
  1. Choose **Student** and **Type** (Guidance session / Counselling note / Recommendation).
  2. Fill **Status** (with its date fields), the Assessment, Recommendations and Parent participation fieldsets, and **Notes**.
  3. **Save record** → "Record saved."; the parent is notified
- Validation: notes required for a Recommendation and for Completed / Follow-up; a date and time for Scheduled; follow-up date today or later; lists 20 × 80
- Tier: Silver · Shots (3) · `car-001-add-a-record.md` · Appx 03 §2.1.b

**DOC-SCH-CAR-002 — Edit a record and move its status** · S8
- Role: CC · Workflow: Records **Edit** → change **Status** (Not Started → Scheduled → Completed → Follow-up Required → …) → **Save changes**
- Errors: "Cannot change status from X to Y"; 409 → **Discard my changes and reload**
- Shots (2) · `car-002-edit-a-record.md` · Appx 03 §2.1.a–b

**DOC-SCH-CAR-003 — Record career preferences** · S8 · CC · Workflow: "Career preferences" → Student → Career interests, Preferred countries, Preferred courses, Interested in studying abroad → **Save preferences** → "Career preferences saved." · not tier-gated · Shots (1) · `car-003-career-preferences.md` · Appx 03 §2.1.c

**DOC-SCH-CAR-004 — Set a student's career goal** · S8
- Role: CC · Nav: Dashboard → Student 360° view list → **Set career goal** / **Edit career goal**
- Workflow: **Career goal** (≤ 120) → **Save** → "Career goal saved."
- Tier: Silver · Shots (1) · Related: S360-001 · `car-004-career-goal.md` · Appx 03 §4.2

**DOC-SCH-CAR-005 — Find and create skills batches** · S8
- Role: CC · Nav: sidebar **Skills**
- Workflow: filter **Module** / **Status**; **Load more**; "Create a batch" (School, Skills module, Title, Topic, Trainer name, Start date, End date) → **Create batch** opens the new batch
- Validation: "Enter a title"; "Choose a start date"; "The end date must be on or after the start date"
- Tier: Soft = Bronze, Digital = Silver
- Shots (3) · `car-005-skills-batches.md` · Appx 03 §2.2

**DOC-SCH-CAR-006 — Edit, close or reopen a skills batch** · S8 · CC · **Edit details** → **Save details**; **Close batch** / **Reopen batch**; a closed batch is read-only · Shots (2) · `car-006-edit-close-reopen-batch.md` · Appx 03 §2.3

**DOC-SCH-CAR-007 — Enrol students and change enrolment status** · S8
- Role: CC · Workflow: "Enrol students" (**Filter students**, tick) → **Enrol N student(s)**; then **Mark completed** / **Certify** (confirm; cannot be undone) / **Withdraw** / **Re-enrol**
- Limits: 200 per batch; 100 per request
- Shots (2) · `car-007-enrolments.md` · Appx 03 §2.3

**DOC-SCH-CAR-008 — Add sessions and take batch attendance** · S8 · CC · **Session date**, **Session topic** → **Add session**; pick the session → tick → **Save attendance** · Errors: date outside the batch; a session already exists on that date · Shots (2) · `car-008-sessions-and-attendance.md` · Appx 03 §2.3

**DOC-SCH-CAR-009 — Add assessments and record scores** · S8 · CC · **Assessment name**, **Maximum score** → **Add assessment**; score and remarks per student → **Save scores** · Validation: "Enter a score from 0 to {max}" · Shots (2) · `car-009-assessments-and-scores.md` · Appx 03 §2.3

**DOC-SCH-CAR-010 — Open a funding support case** · S8
- Role: CC · Nav: sidebar **Funding** → "Add a case"
- Workflow: **Student**, **Support type**, **Provider or institution**, **Amount**, **Notes** → **Add case** → "Case saved."
- Tier: Scholarship = Gold; Loan / financial / guidance = Platinum
- Errors: "{Name} already has an open {type} case…"
- Shots (2) · `car-010-open-a-funding-case.md` · Appx 03 §2.4

**DOC-SCH-CAR-011 — Move a funding case through its stages or close it** · S8
- Role: CC · Workflow: **Edit** → **Stage** (Required → Counselling → Documents → Application → Approved → Completed, or Closed with **Reason for closing**) → **Save changes**
- "Finished cases" list
- Errors: "Give a reason for closing this case."; "This case was changed by someone else…"
- Shots (3) · `car-011-update-or-close-a-funding-case.md` · Appx 03 §2.4

### Module PSY — Psychometric Team (`user-manual/psychometric-team/`, shots → `psychometric-team/`)

**DOC-SCH-PSY-001 — Assign a psychometric assessment** · S9 · PT · **Student**, **Assessment type** → **Assign assessment** → "Assessment assigned."; the parent is notified · Tier: Bronze · Shots (2) · `psy-001-assign-an-assessment.md` · Appx 03 §3.1.a

**DOC-SCH-PSY-002 — Attach an assessment report** · S9
- Role: PT · Workflow: **Attach report** → **Report URL** → **Attach** → "Report attached."; status Completed; the parent is notified
- Tips: it is a link, not a file upload, and it cannot be changed later
- Shots (1) · `psy-002-attach-a-report.md` · Appx 03 §3.1.a

**DOC-SCH-PSY-003 — Record or edit assessment results** · S9
- Role: PT · Workflow: **Record results** / **Edit results** → Test date, Findings lists, Counsellor remarks, Parent discussion date and notes, Follow-up date → **Save results** → "Results saved."
- Validation: "Up to 20 items."; "Each item must be 80 characters or fewer."; "Enter a complete date, or clear the field."
- Shots (2) · `psy-003-record-results.md` · Appx 03 §3.1.a

**DOC-SCH-PSY-004 — Bulk entry: assessments (CSV)** · S9 · PT · as ACAD-004, with the assessment columns · Shots (1) · `psy-004-bulk-assessments.md` · Appx 03 §1.1.d

### Module S360 — Student 360° view (`user-manual/student-360/`, shots → `student-360/`)

**DOC-SCH-S360-001 — Student 360° view** · S9
- Roles: all 7 · Nav: student page **Open 360° view** (CO / PR / TE / AT), child page (PA), or the dashboard list (CC / PT)
- Content: header (career goal); 16 tabs; tab-by-role table (analysis appx 03 §4.2); "Restricted" tabs; keyboard navigation; deep link `?tab=`
- Shots (5): school-role tabs; restricted (service role); examination results; Edusphere programs; 390 px
- Related: CAR-004, PORT-001 · `s360-001-student-360-view.md` · Open: U16 · Appx 03 §4

### Module PORT — Digital Portfolio (`user-manual/portfolio/`, shots → `portfolio/`)

**DOC-SCH-PORT-001 — Digital Portfolio overview** · S7
- Roles: all 7 read
- Content: "{N}% complete" and what counts toward it; the read-only sections; where each role finds the portfolio
- Shots (1) · `port-001-digital-portfolio-overview.md` · Appx 03 §4.3

**DOC-SCH-PORT-002 — Add, edit or delete portfolio entries** · S7
- Roles: CO, TE (assigned), AT · Workflow: **Add {entry}** → **Title**, **Organization**, dates, **Description** → **Save**; **Edit**; **Delete** → **Confirm delete**
- Tier: Gold · Errors: "End date must not be before start date"; write-access 403
- Shots (2) · `port-002-portfolio-entries.md` · Open: U14 · Appx 03 §4.3

**DOC-SCH-PORT-003 — Record a Skill India certification** · S7
- Roles: CO, TE (assigned), AT · Workflow: **Add certification** → tick **Skill India certification** → **Status** / **Certificate number** / **Issue date** (required once Certified)
- Validation: "Choose a status."; "Enter the certificate number."; "Enter the issue date."
- Shots (2) · `port-003-skill-india-certification.md` · Appx 03 §4.3

**DOC-SCH-PORT-004 — Internship tracking and certificates** · S7
- Roles: CO, TE (assigned), AT · Tier: Platinum
- Workflow: **Add internship** (Role, Company, mentor, Completion, Attendance %, Skills acquired, Feedback); when Completed with an end date → **Upload certificate (PDF, JPEG or PNG, up to 5 MB)**; **Download** / **Remove certificate**
- Errors: "Certificate must be at most 5 MB"; "A certificate can only be attached to a completed internship"; the Platinum notice
- Shots (3) · `port-004-internships-and-certificates.md` · Appx 03 §4.3

**DOC-SCH-PORT-005 — Write the personal statement** · S7 · CO, TE (assigned), AT · **Add statement** / **Edit statement** (≤ 4000) → **Save** → "Personal statement saved." · Shots (1) · `port-005-personal-statement.md` · Appx 03 §4.3

### Module SADM — School administration (`admin-manual/`, shots → `admin-schools/`)

**DOC-SCH-SADM-001 — Partner Schools list** · S2
- Role: OA · Nav: sidebar **Schools**
- Content: table columns (raw "reference" UUID, School ID, Name, Branch, City, State, Board, Tier, Created) with client-side search, filter, sort and paging (10 / 25 / 50)
- Shots (2) · `sadm-001-partner-schools-list.md` · Appx 04 §1

**DOC-SCH-SADM-002 — Create a school and seed its Coordinator** · S2
- Role: OA · Workflow: "Create school" → Identity / Academic / Partnership fieldsets + **Coordinator full name** / **Coordinator email** → **Create school + seed Coordinator** → green message (emailed) or amber (not delivered)
- Validation: name required; email format; lengths
- Errors: "Email already exists"; "A valid email address is required"
- Tips: there is no "Valid until" field (set it with Edit); duplicate names are not checked
- Shots (4) · Related: AUTH-003, SADM-003 · `sadm-002-create-a-school.md` · Open: U7 · Appx 04 §2

**DOC-SCH-SADM-003 — Edit a school profile and change its partnership tier** · S2
- Role: OA · Workflow: **School ID** → **Look up** → edit the fields / **Partnership tier** / **Valid until** → **Save changes**; a downgrade shows the confirmation → **Confirm downgrade**
- Messages: "School profile updated. Partnership is now {Tier}…"; "No changes to save."; "No school found with that School ID"; the 409 concurrent tier change
- Effects: CO and PR notified (not for a "Valid until"-only change)
- Shots (5) · Related: ENT-001, NOTIF-001 · `sadm-003-edit-school-and-tier.md` · Appx 04 §3

**DOC-SCH-SADM-004 — Onboard several schools by CSV** · S2
- Role: OA · Workflow: "Onboard several schools (CSV)" → **Download the template (.csv)** → **Filled-in schools file** → **Upload schools** → result report
- Limits: 1 MB, 100 rows
- Errors: file-level and row-level lists; replaying the same file is safe
- Shots (3) · `sadm-004-bulk-onboard-schools.md` · Appx 04 §4

**DOC-SCH-SADM-005 — Create school staff accounts and their school portfolio** · S2
- Role: OA · Nav: sidebar **School Staff**
- Workflow: **Role**, **Full name**, **Email**, **School portfolio** (search / select) → **Create account** → set-password link emailed
- Tips: the school portfolio cannot be changed later in the UI (§12.2 item 3)
- Shots (3) · Related: AUTH-003, DASH-005..007 · `sadm-005-create-school-staff.md` · Appx 04 §5

**DOC-SCH-SADM-006 — Start an overseas application for a school student** · S9
- Roles: OA, OC · Nav: sidebar **School Applications**
- Workflow: **School** → **Student** → **University**, **Intake** → **Start application** → "Application started for {student}."; the parent is notified
- Tier: Gold (Application support) · Errors: tier denial; "An application for this university already exists for this student"
- Shots (4) · Related: RPT-006 · `sadm-006-school-applications.md` · Appx 04 §6

**DOC-SCH-SADM-007 — Review school transfer requests** · S6
- Roles: OA, SA · Nav: sidebar **School Transfers**
- Workflow:
  1. Filter **Status**.
  2. Read the warnings.
  3. **Approve** → **Confirm approval**, or **Reject** → note → **Confirm rejection**.
- Messages: "Moved {student} to {To}…"; "Request rejected for {student}."; conflict 409s
- Shots (5) · Related: XFER-* · `sadm-007-review-transfers.md` · Appx 04 §7

**DOC-SCH-SADM-008 — School Analytics** · S10
- Roles: OA, SA · Content: "All partner schools" KPI groups (definitions); "Service utilization by school" with **Search schools**, flags (New / Renewal due / No active tier) and paging
- Shots (3) · `sadm-008-school-analytics.md` · Appx 04 §8

**DOC-SCH-SADM-009 — Activity Feedback across schools** · S5 · OA, SA · **Search schools** / **School** filter; **Load more** · Shots (2) · `sadm-009-activity-feedback.md` · Appx 04 §9

**DOC-SCH-SADM-010 — Re-send a set-password link** · S2 · OA · Nav: sidebar **Users** → re-send · Code review PARTIAL (U12) · Shots (1) · `sadm-010-resend-set-password-link.md` · Appx 04 §5

**DOC-SCH-SADM-011 — Super Admin and the school screens** · S2
- Role: SA · Content: what SA can open (Analytics in the sidebar; Transfers and Feedback by URL) and what shows "Access unavailable / Workspace not found"
- Shots (2) · `sadm-011-super-admin-access.md` · Open: U11 · Appx 04 §0.6

---

## Self-review (S1)
- **Spec coverage.** All 86 Doc IDs in analysis §3 have a feature record and a session:
  - S2: 7
  - S3: 12
  - S4: 8
  - S5: 6
  - S6: 5
  - S7: 12
  - S8: 11
  - S9: 7
  - S10: 18

  The total is 86. Every analysis §11 data item (D1–D18) is created in a named session, and every §12.1 open item (U1–U16) has a session.
- **Placeholder scan.** No TBD / TODO. Unknowns are explicit U-items with an owner or session.
- **Consistency.**
  - Doc ID prefixes match the analysis.
  - Screenshot module folders match the Global Constraints list.
  - File names match the file-structure block.
- **Review Focus.**
  - Item 1 is covered by the role tables in STU-006 / S360-001 / PORT-001.
  - Item 2 by the Docs Bronze / No-Tier / Expired schools (S2) and the denial shots in ACT-001, CAR-005, PORT-004 and SADM-006.
  - Item 3 by S2.3 and L4.
  - Item 4 by the D2 / D8 data created relative to the capture date.
  - Item 5 by L3 / L4 ("capture as the owning role").
