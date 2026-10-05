# Agent CRM User Documentation — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans (one module session at a time, in this
> session's order). Steps use checkbox (`- [ ]`) syntax. Tick them in this file and update
> `docs/documentation-progress.md` at the end of every session.

**Goal:** Produce verified end-user, administrator and role-based documentation for the EduSphere **Agent CRM**
(Agent Portal + admin-side agency management), with screenshots captured by Playwright from the running app.

**Architecture:** One Markdown file per feature (template below) under `docs/user-manual/<module>/` (agency users) and
`docs/admin-manual/` (Overseas/Super Admin). Screenshots live under `docs/screenshots/<module>/` and are listed in
`docs/screenshot-index.md`. Behaviour is taken from code (already reviewed in Phase 1) and confirmed in the browser before
it is written down. Repeatable capture scripts make screenshots reproducible.

**Tech stack:** Next.js 15 / FastAPI / PostgreSQL stack via Docker Compose; Playwright 1.62.1 (Chromium) for capture;
the `browser-use` skill for exploration; Markdown.

**Spec:** `docs/documentation-analysis.md` (feature inventory, roles, routes, APIs, test data, open questions).

## Global Constraints
- Scope: Agent CRM only (54 features, §Feature records). Anything else found goes to "Discovered functionality" in
  `docs/documentation-progress.md`, not into the manuals.
- Code baseline: `main` @ `e376c25c`. Browser work runs against a stack built from that commit. If `main` moves, record
  the new commit at the top of `documentation-progress.md` and re-check affected features.
- Do not modify application source code. Capture tooling is test-only (see Task S2.3).
- Viewport **1440 × 900**, Chromium, light colour scheme, `deviceScaleFactor: 1`, full-page off (viewport shots)
  unless a step needs the whole form (`fullPage: true` allowed; note it in the index).
- Screenshot path: `docs/screenshots/<module>/<NN>-<feature>-<step>.png`, NN = two-digit sequence within the module
  folder. Module folders: `account-access`, `dashboard`, `students`, `universities`, `applications`, `documents`, `tasks`,
  `notifications`, `commissions`, `reports`, `team`, `staff-performance`, `admin-agencies`.
- **Never show passwords, tokens or keys.** The Overseas login page shows the demo password unless
  `ENVIRONMENT=production` (`apps/web/app/overseas/login/page.tsx:12`): mask that card and every password input with
  Playwright `mask`. Never paste the seed password into any doc.
- Test data only (`*@edusphere.local` or `*@example.test` addresses, agency names prefixed `Docs `).
- Anything not confirmed in the browser is written as **VERIFICATION REQUIRED** and left out of the steps.
- Simple English, numbered steps, bold UI labels exactly as on screen, one feature per file.
- Terminology (use exactly): **Agency Master**, **Agency Staff**, **Overseas Admin**, **Super Admin**, **agency**,
  **student** (with or without a login), **application**, **stage** (not "status") for application progress,
  **document**, **document request**, **task**, **commission**, **deposit**, **visa case**, **sidebar**.
- Docker lifecycle belongs to the owner: ask them to start/seed the stack; never run `docker compose up/down` yourself.
- Commit docs on a docs-only branch (`docs/agent-crm-user-guide`), only when the owner asks; message style
  `docs: add <module> user guide`.

## Review Focus
1. **Master vs Staff differences** — every feature file must say what Staff see (hidden button, "Own" scope, refusal
   text). Each module session captures at least one Staff screenshot for features where Staff differ.
2. **Secrets in screenshots** — run the masking check (Task S2.3 step 5) before committing any screenshot.
3. **Wrong stack / baseline** — the running worktree stacks (`bdm006`, `bdm009`) are not `e376c25c`; each session
   records `git rev-parse HEAD` of the stack's source and the web URL used.
4. **Blocked and read-only states** — pending/suspended agency, archived student, withdrawn application, paid deposit,
   recorded visa decision: each must be documented where users hit them (Common Errors).
5. **Time-dependent behaviour** — overdue tasks, deadline badges "(in N days)", 08:00 IST reminders, "as of" stamps:
   create data relative to the capture date and state the date in the index.

---

## File structure (created across sessions)

```
docs/
  documentation-analysis.md        (Phase 1, done)
  documentation-plan.md            (this file)
  documentation-progress.md        (tracker)
  screenshot-index.md              (created S2)
  user-manual/
    README.md                      (index, S10)
    account-access/  auth-001-register-an-agency.md … auth-006-my-profile.md
    dashboard/       dash-001-… dash-002-…
    students/        stu-001-… stu-009-…
    universities/    uni-001-…
    applications/    app-001-… app-009-…
    documents/       doc-001-… doc-006-…
    tasks/           task-001-… task-002-…
    notifications/   notif-001-…
    commissions/     comm-001-…
    reports/         rpt-001-… rpt-003-…
    team/            team-001-… team-005-…
    staff-performance/ perf-001-…
  admin-manual/
    README.md
    adm-001-… adm-008-…
  role-guides/
    agency-master.md  agency-staff.md  overseas-admin-agencies.md  super-admin-agencies.md
  faq.md
  troubleshooting.md
  documentation-review-report.md   (S11)
  screenshots/<module>/NN-<feature>-<step>.png
apps/web/tests/doc-capture/        (capture scripts, test-only — owner to confirm in S2)
apps/web/playwright.docs.config.ts (capture config, test-only — owner to confirm in S2)
```

Image links from a feature file: `../../screenshots/<module>/<file>.png` (user manual) and
`../screenshots/admin-agencies/<file>.png` (admin manual).

### Feature file template (every feature)
```markdown
# <Feature name>
> Doc ID: DOC-XXX-NNN · Verified on <date> against `main` @ <commit> · Roles: <roles>

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

---

## Sessions

Each module session (S2–S9) follows the **standard session loop**:

- [ ] **L1** Read `docs/documentation-analysis.md`, this plan, `docs/documentation-progress.md`, `docs/screenshot-index.md`.
- [ ] **L2** Ask the owner to confirm the stack is up from `e376c25c` (or the recorded commit) and seeded; record web URL + commit in the progress file.
- [ ] **L3** Explore each feature in the browser (`browser-use` skill) as each relevant persona; note labels, fields, messages; tick "Browser Verified" only for what was seen.
- [ ] **L4** Write/extend the Playwright capture spec for the module; run it; open every PNG and check it (readable, correct state, no secrets).
- [ ] **L5** Write one feature file per Doc ID using the template; mark unconfirmed points **VERIFICATION REQUIRED**.
- [ ] **L6** Run the link check (S2.4); fix broken links.
- [ ] **L7** Update `docs/screenshot-index.md`, `docs/documentation-progress.md` (status columns, unresolved items, discovered functionality).
- [ ] **L8** Report to the owner; commit only if asked.

### S1 — Master planning (this session) — DONE 2026-10-05
- [x] Graphify refreshed to `e376c25c`; discovery of portal, admin, API, RBAC, test data.
- [x] `docs/documentation-analysis.md`, `docs/documentation-plan.md`, `docs/documentation-progress.md` written.

### S2 — Environment, capture tooling, Account access, Agency approvals
Features: DOC-AUTH-001..006, DOC-ADM-001.
- [x] **S2.1** Owner confirms: stack from `e376c25c`, seeded; capture-tooling location (default below); whether the web
  container may run with `ENVIRONMENT=production` (removes the demo-password card) or masking is used instead.
- [x] **S2.2** Create `docs/screenshot-index.md`:
  ```markdown
  # Screenshot Index
  Captured against `main` @ <commit>, viewport 1440×900, Chromium.
  | Screenshot | Module | Feature | Step | Role | Description |
  |---|---|---|---|---|---|
  ```
- [x] **S2.3** Capture tooling (test-only, no product code). `apps/web/playwright.docs.config.ts`:
  ```ts
  import { defineConfig } from "@playwright/test";
  export default defineConfig({
    testDir: "./tests/doc-capture",
    workers: 1,
    retries: 0,
    use: {
      baseURL: process.env.DOCS_BASE_URL ?? "http://localhost:3000",
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
      colorScheme: "light",
      locale: "en-IN",
      timezoneId: "Asia/Kolkata",
    },
  });
  ```
  `apps/web/tests/doc-capture/shoot.ts`:
  ```ts
  import type { Locator, Page } from "@playwright/test";
  import path from "node:path";
  const ROOT = path.resolve(__dirname, "../../../../docs/screenshots");
  // Masks every password input and the dev-only "Demo accounts" card before each capture.
  export async function shoot(page: Page, module: string, file: string, extraMask: Locator[] = [], fullPage = false) {
    const mask = [page.locator('input[type="password"]'), page.locator(".card.soft", { hasText: "Demo accounts" }), ...extraMask];
    await page.screenshot({ path: path.join(ROOT, module, file), mask, fullPage, animations: "disabled" });
  }
  export async function signIn(page: Page, email: string) {
    const password = process.env.DOCS_PASSWORD; // supplied by the owner's shell; never committed
    if (!password) throw new Error("Set DOCS_PASSWORD");
    await page.goto("/overseas/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in securely" }).click();
    await page.waitForURL(/\/overseas\/(agent|admin)\//);
  }
  ```
  Run: `npx --prefix apps/web playwright test -c apps/web/playwright.docs.config.ts <spec>`.
- [x] **S2.4** Link/asset check script `docs/tooling/check-doc-links.mjs`:
  ```js
  // Fails when a Markdown image/link under docs/ points at a missing file. Usage: node docs/tooling/check-doc-links.mjs
  import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
  import { join, dirname, resolve } from "node:path";
  const dirs = ["docs/user-manual", "docs/admin-manual", "docs/role-guides"];
  const files = ["docs/faq.md", "docs/troubleshooting.md", "docs/screenshot-index.md"].filter(existsSync);
  const walk = (d) => existsSync(d) ? readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? walk(p) : p.endsWith(".md") ? [p] : []; }) : [];
  let bad = 0;
  for (const f of [...dirs.flatMap(walk), ...files]) {
    for (const m of readFileSync(f, "utf8").matchAll(/\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
      const target = m[1];
      if (/^(https?:|mailto:)/.test(target)) continue;
      if (!existsSync(resolve(dirname(f), target))) { console.log(`${f}: missing ${target}`); bad++; }
    }
  }
  console.log(bad ? `${bad} broken link(s)` : "All links OK");
  process.exit(bad ? 1 : 0);
  ```
- [x] **S2.5** Verify masking: capture `01-login-page.png`, open it, confirm no password text or demo card is readable.
- [x] **S2.6** Run the standard loop for AUTH-001..006 and ADM-001. Create the test agencies while documenting:
  `Docs Pending Agency` (left pending), `Docs Rejected Agency`, `Docs Suspended Agency` (approve → suspend),
  `Docs Second Agency` (approved).

### S3 — Team & staff (creates the Staff personas)
Features: DOC-TEAM-001..005, DOC-ADM-008.
- [x] Standard loop. As the seeded Master create Staff A (no permissions), B (*Verify documents*), C (*View reports*),
  D (to deactivate); invite a second Master. Staff need a set-password link: use ADM-008 (owner approval) or the
  email webhook sink — owner decides in S3.1.

### S4 — Students & universities
Features: DOC-STU-001..009, DOC-UNI-001.
- [ ] Standard loop. Create ≥21 no-login students (paging), assign some to A and B, archive one; agency universities;
  shortlist entries.

### S5 — Applications core + tasks
Features: DOC-APP-001..005, DOC-TASK-001..002.
- [ ] Standard loop. Applications in every filter group (Draft, Submitted, Offer received, Visa, Enrolled later in S6,
  Withdrawn); deadlines today/tomorrow/+3 days; tasks open, overdue (past due), done, cancelled.

### S6 — Offer, deposit, visa, enrollment
Features: DOC-APP-006..009.
- [ ] **S6.1** Owner confirms Razorpay **test** keys are configured (`RAZORPAY_KEY_ID` starts `rzp_test_`) and the
  webhook secret is set, or accepts documenting APP-007 payment as VERIFICATION REQUIRED.
- [ ] Standard loop. Produce a paid deposit, a visa case through to a decision (plus one checklist-gate failure), an
  enrolled application (creates an *estimated* commission for S8).

### S7 — Documents
Features: DOC-DOC-001..006.
- [ ] Standard loop. Documents in every state, an offer-letter document, open and cancelled requests; Staff B verify
  vs Staff A refusal.

### S8 — Dashboard, notifications, commissions, reports, staff performance
Features: DOC-DASH-001..002, DOC-NOTIF-001, DOC-COMM-001, DOC-RPT-001..003, DOC-PERF-001.
- [ ] Standard loop (data from S3–S7 now exists). Commission states: estimated → eligible (OA sets amount) → claimed
  (Master) → paid (OA approves). Reports as Master, Staff C, Staff A (refusal). Reminder notifications: owner decides
  whether to wait for 08:00 IST or trigger the job (S8.1).

### S9 — Admin-side agency management
Features: DOC-ADM-002..005, DOC-ADM-007 (DOC-ADM-006 is done in S8).
- [ ] Standard loop as Overseas Admin and Super Admin; record remittance and refund on the S6 deposit(s).

### S10 — Role guides, FAQ, troubleshooting, indexes
- [ ] Write `docs/role-guides/agency-master.md`, `agency-staff.md`, `overseas-admin-agencies.md`,
  `super-admin-agencies.md` (sections: Role Purpose, Login, Dashboard, Menus Available, Main Activities, Daily
  Workflows, Restrictions, Common Problems, Related Features), linking to feature files; reuse existing screenshots.
- [ ] Write `docs/faq.md` and `docs/troubleshooting.md` (Problem / Possible Cause / Resolution / When to Contact
  Administrator) only from behaviour observed in S2–S9.
- [ ] Write `docs/user-manual/README.md` and `docs/admin-manual/README.md` indexes.

### S11 — Final review
- [ ] Re-check every feature file against code (`e376c25c` or recorded commit), RBAC matrix, screenshots, plan and
  tracker; run the link check; detect duplicate screenshots (`certutil -hashfile` / `sha256sum` over
  `docs/screenshots`). Write `docs/documentation-review-report.md` with CRITICAL/HIGH/MEDIUM/LOW findings.
- [ ] Mark features COMPLETE only when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES (where required),
  Documented = YES, Reviewed = PASSED.

---

## Feature records

Abbreviations: M = Agency Master, S = Agency Staff, OA = Overseas Admin, SA = Super Admin. "Shots" = estimated
screenshots. Verification status for every record at the end of S1: **Code reviewed (HEAD e376c25c); browser NOT
verified** unless stated otherwise.

### Module AUTH — Account access (`docs/user-manual/account-access/`, shots → `screenshots/account-access/`)

**DOC-AUTH-001 — Register an agency** · Session S2
- Role: visitor · Nav: `/overseas/login` → **Create an account** → `/overseas/register`
- Preconditions: email not registered
- Workflow: fill Full name, Email, Phone → Account type **Education agent** → Agency name (optional) → Password → **Create account** → lands on dashboard showing "Agent registration is pending approval"
- Shots (4): empty form; Education agent selected (Agency name visible); duplicate-email error; pending card
- Validation: name 2–160; email shape ≤320; phone ≤40; agency ≤160; password 10–128 ("Use at least 10 characters.")
- Errors: "Email already exists"; "Registration failed." fallback
- Related: AUTH-003, ADM-001 · File: `auth-001-register-an-agency.md` · Open: U4

**DOC-AUTH-002 — Sign in and sign out** · S2
- Role: M, S · Nav: `/overseas/login`; sidebar footer **Sign out**
- Preconditions: active login (or blocked — see AUTH-003)
- Workflow: Email, Password → **Sign in securely** → role dashboard; Sign out → home page
- Shots (3): login page (masked); invalid credentials; wrong-portal error
- Validation: browser required fields
- Errors: "Invalid credentials"; "Use the correct EduSphere portal for this account: sign in at …"; "Unable to sign in"
- Related: AUTH-003, AUTH-004 · File: `auth-002-sign-in-and-sign-out.md`

**DOC-AUTH-003 — "Access unavailable" states** · S2 (suspended in S2 via ADM-001; deactivated staff in S3)
- Role: M, S · Nav: any Agent Portal page
- Preconditions: agency pending / rejected / suspended, or member deactivated
- Workflow: sign in → card "Access unavailable" + reason + "Contact EduSphere Overseas Admin…" + **Sign out**
- Shots (3): pending; suspended; deactivated member
- Validation: n/a
- Errors: "Agent registration is pending approval"; "Your agency's account is suspended"; "Your Master account is deactivated"
- Related: ADM-001, ADM-004, TEAM-003 · File: `auth-003-access-unavailable.md` · Open: U3

**DOC-AUTH-004 — Forgot / reset password and first-time set-password link** · S2 (first-time link in S3)
- Role: M, S · Nav: login → **Forgot your password?** → `/overseas/forgot-password`; email link → `/overseas/reset-password`
- Preconditions: access to the mailbox (or the test email sink)
- Workflow: Email → **Send reset instructions** → confirmation text → open link → New password → **Reset password** → login
- Shots (4): forgot form; confirmation; reset form; expired-token error
- Validation: 10–128 characters; link valid 30 min (reset) / 72 h (invitation)
- Errors: "Reset token is invalid or expired" + "Request a new reset link"; missing-token text; network error text
- Related: TEAM-002, TEAM-003 · File: `auth-004-reset-password.md`

**DOC-AUTH-005 — Change password** · S2
- Role: M, S · Nav: sidebar footer **Change password** → `/account/password`
- Preconditions: signed in
- Workflow: Current password, New password (optional **Show passwords**) → submit → "Your password was changed."
- Shots (3): form (masked); wrong current password; success
- Validation: ≥10 characters; must differ from current
- Errors: "Incorrect current password"; "New password must be different from the current password"; "Too many incorrect attempts. Try again in …"; session expired
- Related: AUTH-004 · File: `auth-005-change-password.md` · Open: U2

**DOC-AUTH-006 — My profile** · S2
- Role: M, S · Nav: sidebar footer **My profile** → `/account/profile`
- Preconditions: signed in (page renders in the public site shell, not the portal sidebar; "← Back to dashboard")
- Workflow (code-reviewed S2, `app/account/profile/page.tsx`, `ProfileForm.tsx`, `NotificationPreferencesForm.tsx`):
  "Your profile" → Full name (required, 2–160), Phone (≤40) → **Save changes** → "Your profile was updated.";
  "Notifications" → Email and In-app "Always on"; WhatsApp / SMS checkboxes (shows "Messages go to {phone}" when a
  valid phone is saved) → **Save notification settings** → "Notification settings saved."
- Shots (2): profile + notifications page; validation error
- Errors: "Unable to update your profile. Try again in a moment."; "Network error. Try again."; "Couldn't save your
  settings. Check your connection and try again."; "We couldn't load your notification settings right now." + Try
  again; signed out → "Sign in required"; outage → "Temporarily unavailable"
- Related: AUTH-005 · File: `auth-006-my-profile.md` · Status: code reviewed (S2), browser NOT verified · Open: U1
  (whether WhatsApp/SMS delivery is configured for agents)

### Module DASH — Dashboard (`dashboard/`)

**DOC-DASH-001 — Agency dashboard (Master)** · S8
- Role: M · Nav: sidebar **Dashboard**
- Preconditions: populated agency (S3–S7 data)
- Workflow: read scope line "Whole agency · Your code M00n"; KPI groups Students, Pipeline, Documents, Commission; by country / by university; staff table; links (View students, Open tasks, View reports, View staff performance)
- Shots (3): populated board; staff table; new empty agency (Docs Second Agency)
- Validation: n/a · Errors: "Dashboard figures are unavailable right now." + Try again
- Related: PERF-001, COMM-001, TASK-001 · File: `dash-001-master-dashboard.md` · Open: U5

**DOC-DASH-002 — Agency dashboard (Staff)** · S8
- Role: S · Nav: sidebar **Dashboard** · Preconditions: Staff A with assigned students
- Workflow: "Your assigned students" scope; no Commission, no staff table
- Shots (1) · Errors: as DASH-001 · Related: DASH-001 · File: `dash-002-staff-dashboard.md`

### Module STU — Students (`students/`)

**DOC-STU-001 — Find students** · S4
- Role: M (all), S (own) · Nav: **Students** (Staff: **My Students → All**)
- Preconditions: ≥21 students for paging
- Workflow: search "Name, email or phone"; **Show archived**; **Assigned to** (Master: Anyone/Unassigned); Previous/Next
- Shots (5): Master list; Staff list; no-match + **Clear filters**; pagination footer; empty agency
- Validation: search ≤100 · Errors: "Unable to load students." + Retry
- Related: STU-002..005 · File: `stu-001-find-students.md`

**DOC-STU-002 — Add a student** · S4
- Role: M, S · Nav: Students → **Add student** (Staff: My Students → **Add**)
- Preconditions: agency active
- Workflow: Personal / Contact / Academic / Preferences / Notes → **Save student** → "{name} added."; duplicate → **Save anyway** / **Go back**
- Shots (4): empty form; validation errors; duplicate warning; success
- Validation: Full name required ≤160; DOB 1900–today; email; phone 7–20 digits; graduation year 1950–(now+6); notes ≤2000
- Errors: "A student with this email or phone already exists in your agency"; "Unable to save this student."; unsaved-changes prompt
- Related: STU-005 (staff-created students auto-assign to self) · File: `stu-002-add-a-student.md` · Open: U6

**DOC-STU-003 — View and edit a student record** · S4
- Role: M, S (own) · Nav: Students → card **View** → **Edit**
- Preconditions: active student without a login (edit)
- Workflow: detail panel (fields, Journey, Counseling, Shortlist, Tasks, History) → Edit → **Save changes** → "{name} saved."; **Close**/Esc
- Shots (3): detail (no login); detail (with login, read-only); edit form
- Validation: as STU-002 · Errors: "Linked students are edited in their own account"; "Unarchive this student first"; "Student not found" (out of scope)
- Related: STU-006..008 · File: `stu-003-view-and-edit-a-student.md`

**DOC-STU-004 — Archive / unarchive a student** · S4
- Role: M · Nav: card **Archive** → **Confirm archive**; **Unarchive** → **Confirm unarchive**
- Preconditions: active / archived student
- Workflow: confirm → "{name} archived." / "{name} restored."; archived hidden unless Show archived
- Shots (2): confirm; archived card · Errors: "Already archived"/"Already active"; Staff: button absent
- Related: STU-001 · File: `stu-004-archive-a-student.md`

**DOC-STU-005 — Assign a student to a staff member** · S4
- Role: M · Nav: card **Assign** → Assign to → **Save assignment**
- Preconditions: active student; active staff (S3)
- Workflow: choose staff/Unassigned → save → "{name} assigned to {who}." (open tasks move; assignee notified)
- Shots (2): control open; success · Errors: "Choose an active Staff member of this agency"; "Couldn't load your staff."
- Related: TEAM-002, NOTIF-001, TASK-001 · File: `stu-005-assign-a-student.md`

**DOC-STU-006 — Record counseling** · S4
- Role: M, S (own) · Nav: student detail → Counseling → **Record counseling** / **Edit counseling**
- Preconditions: active student without a login
- Workflow: Counseling completed, Career interest, Course/Country preference, Budget amount + currency, Remarks → save → "Counseling saved for {name}."
- Shots (4): empty card; form; budget error; saved view
- Validation: budget ≥0, ≤99,999,999.99, 2 decimals, full stop for decimals; remarks ≤2000
- Errors: "Counseling is recorded only for students without a login."; archived message; "Unable to save counseling."
- Related: STU-008 · File: `stu-006-record-counseling.md`

**DOC-STU-007 — Build a university shortlist** · S4
- Role: M, S (own) · Nav: student detail → University shortlist → **Add university to shortlist**
- Preconditions: active student; agency universities (UNI-001) or catalogue
- Workflow: Filter universities → University (Catalogue / Your agency) → Course or "Other (type a course)" → Intake, Tuition fee, Entry requirements → **Save to shortlist**; Edit / Remove → **Confirm remove**
- Shots (4): empty; add form; cards; remove confirm
- Validation: course 200, intake 120, fee 120, requirements 2000; max 50 entries
- Errors: "Choose a university."; "This student's shortlist is full (50 entries)"; "Course does not belong to selected university"; …
- Related: UNI-001, APP-002 · File: `stu-007-university-shortlist.md` · Open: U7

**DOC-STU-008 — Student journey and history** · S4 (re-shoot with applications in S6)
- Role: M, S (own) · Nav: student detail → **Journey**; History → **Show history**
- Preconditions: student; ideally an application through several steps
- Workflow: read 9-step tracker (Create … Enrollment) per application; history newest first, **Refresh**, paging
- Shots (3): new student; with application; history expanded
- Errors: "Unable to load the journey."; "Unable to load history."
- Related: APP-* · File: `stu-008-journey-and-history.md`

**DOC-STU-009 — Link an existing student account** · S4
- Role: M, S · Nav: Students → Actions → **Link student**
- Preconditions: an Overseas student account reference (seeded student)
- Workflow: Overseas student reference → submit → "Student linked."
- Shots (1) · Errors: "Overseas student not found"; "Student is already linked to this agency"; archived message
- Related: STU-001 (explain "Add student" vs "Link student") · File: `stu-009-link-a-student-account.md`

### Module UNI — Universities (`universities/`)

**DOC-UNI-001 — Manage the agency university list** · S4
- Role: M (add/edit/delete), S (view, search) · Nav: sidebar **Universities**
- Preconditions: none
- Workflow: **Add university** → Name, Country, City, Entry requirements → **Save university**; Edit; Delete → **Confirm delete**; search on Enter
- Shots (5): Master list; Staff view; form; validation error; in-use delete error
- Validation: Name/Country required; 200/120/120/2000 limits; 500 per agency
- Errors: "This university is already in your agency's list"; "This university is on N shortlist entries; remove it from them first"
- Related: STU-007 · File: `uni-001-agency-universities.md`

### Module APP — Applications (`applications/`)

**DOC-APP-001 — View and filter applications** · S5
- Role: M, S (own) · Nav: **Applications** → All applications / Draft / Submitted / Offer received / Visa / Enrolled / Withdrawn
- Preconditions: applications in several groups
- Workflow: pick filter → read cards (stage, ID, deadline "(in N days)", Next) → **View**/**Hide**; Previous/Next
- Shots (4): All; empty filter; deadline badge; Withdrawn view
- Errors: "The applications could not be loaded." + Retry · Note: All excludes withdrawn
- Related: APP-002..005 · File: `app-001-view-applications.md`

**DOC-APP-002 — Create an application** · S5
- Role: M, S (own) · Nav: Applications → **Create application**
- Preconditions: active student in scope
- Workflow: Linked student → University → Course → Intake → Application ID / Submitted on / deadlines → **Create application** → "Application created." (stage Enquiry)
- Shots (4): empty; filled; success; duplicate error
- Validation: intake 1–80 required; ID ≤140; dates 2000–2100; submitted not in future
- Errors: "An application for this university/course already exists"; "Too many applications created today -- try again later"; "Unarchive this student first"
- Related: STU-007, APP-005 · File: `app-002-create-an-application.md` · Open: U8

**DOC-APP-003 — Edit an application** · S5
- Role: M, S (own) · Nav: card **View** → **Edit** → **Save**
- Preconditions: not withdrawn; student not archived
- Workflow: change Course, Application ID, Intake, Submitted on, deadlines, Next action → "Saved."
- Shots (2): form; validation error
- Errors: "Offer deadline cannot be before the offer date"; "This application is withdrawn"; reload message
- Related: APP-004 · File: `app-003-edit-an-application.md`

**DOC-APP-004 — Application detail page** · S5 (re-shoot at Offer stage in S6)
- Role: M, S (own) · Nav: card **View**
- Workflow: read fields; sections Offer, Deposit, Visa, Enrollment, Change status, Status history; **Close**
- Shots (2): detail at Offer with history; withdrawn read-only note
- Errors: "This application is no longer available."; load error + Retry
- Related: APP-005..009 · File: `app-004-application-detail.md`

**DOC-APP-005 — Change status / withdraw** · S5
- Role: M, S (own) · Nav: detail → Change status → **Move to** → **Update status**; **Withdraw application** → **Yes, withdraw**
- Preconditions: not withdrawn/enrolled
- Workflow: forward only up to Status tracking; optional note ≤2000; withdrawal is final
- Shots (3): Move-to list; withdraw confirm; withdrawn result
- Errors: "This application changed since you opened it -- reload…"; "Cannot move from … -- an agent can only move an application forward"
- Related: APP-009, NOTIF-001 · File: `app-005-change-status-or-withdraw.md`

**DOC-APP-006 — Record or edit an offer** · S6
- Role: M, S (own) · Nav: detail → Offer → **Record offer** / **Edit offer** → **Save offer**
- Preconditions: offer-letter document uploaded with type "Offer letter" (DOC-002) if attaching
- Workflow: Offer type → Offer date → Offer deadline → Conditions (conditional) → Offer letter → save → "Offer saved." (stage moves to Offer if earlier)
- Shots (4): empty; conditional form; saved with letter; no-letter hint
- Validation: date not future; deadline ≥ offer date; conditions required for conditional, forbidden for unconditional
- Errors: "Choose an offer letter uploaded for this application"
- Related: DOC-002, APP-007 · File: `app-006-record-an-offer.md`

**DOC-APP-007 — Deposit terms and payment** · S6
- Role: M, S (own) · Nav: detail → Deposit → **Record deposit** / **Pay deposit** / **Download receipt**
- Preconditions: Razorpay test keys (S6.1)
- Workflow: Deposit required? → Amount ₹ → Due date → **Save deposit** → **Pay deposit** → Razorpay checkout → "Payment received. Confirming…" → **Refresh** → Paid + receipt
- Shots (7): no deposit; form; Awaiting payment; Razorpay test checkout; confirming; Paid + receipt; payment-unavailable warning
- Validation: amount >0, ≤99,999,999.99, 2 decimals, INR only; not-required has no amount/date
- Errors: "Payment not completed. You can try again."; "Online payment is unavailable right now. Nothing has been charged."; "Too many payment attempts…"; "The payment provider is unavailable -- nothing was charged…"
- Related: ADM-005 · File: `app-007-deposit-and-payment.md` · Open: U9

**DOC-APP-008 — Run the visa case** · S6
- Role: M, S (own) · Nav: detail → Visa → **Start visa case**; **Edit visa details**; **Move visa stage**; **Record decision**
- Preconditions: application at Offer or later, not enrolled/withdrawn
- Workflow: dates + documents checklist → start → move Checklist → Documentation → Interview prep → Tracking → Decision → record Approved/Refused/Withdrawn (final)
- Shots (6): no case; start form; checklist with unverified items; gate error; skip confirmation; decision + disclaimer
- Validation: interview ≥ application date; ≤8 checklist items; leaving checklist needs all verified
- Errors: "An offer is needed before a visa case"; "Cannot advance past the checklist stage -- not yet verified: …"; "The visa decision is recorded, so this case can no longer be changed"
- Related: DOC-004 · File: `app-008-visa-case.md`

**DOC-APP-009 — Confirm enrollment** · S6
- Role: M (Staff see "An agency Master confirms enrollment.") · Nav: detail → Enrollment → **Enroll student** → **Confirm enrollment** → **Yes, confirm enrollment**
- Preconditions: stage Offer / Visa documentation / Status tracking
- Workflow: Enrollment date, University student ID, Note → confirm → "Enrollment confirmed." (commission estimated); later **Edit enrollment details**
- Shots (5): Enroll button; confirm dialog; enrolled details; intake warning; Staff read-only note
- Validation: date 2000–2100 required; ID ≤60; note ≤2000; intake check is a warning only
- Errors: "Only an agency Master can confirm enrollment"; "An offer is needed before enrollment"
- Related: COMM-001, ADM-006 · File: `app-009-confirm-enrollment.md`

### Module DOC — Documents (`documents/`)

**DOC-DOC-001 — Browse and download documents** · S7
- Role: M, S (own) · Nav: **Documents → Pending / Uploaded**
- Workflow: read cards → **Download** / **Review** / **Replace file** / **History**; Previous/Next
- Shots (3): Pending; Uploaded; card with "Reason:"
- Errors: "The documents could not be loaded."; "The document could not be opened."; "Document is outside your assigned scope"
- Related: DOC-002..005 · File: `doc-001-browse-documents.md` · Open: U11

**DOC-DOC-002 — Upload a document** · S7
- Role: M, S (own) · Nav: Documents → **Upload document**
- Workflow: Student → Document type (+ Description for Other) → Application (required for Offer letter) → Fulfils request → File → **Upload document** → "Document uploaded. It is waiting for review."
- Shots (4): form; Other + description; offer letter needs application; file-type error
- Validation: PDF/JPEG/PNG by content; ≤20 MB (configurable); description 2–80 for Other
- Errors: "Upload a PDF, JPEG or PNG file"; "The file must be at most 20 MB"; "Too many documents uploaded today -- try again later"
- Related: APP-006, DOC-006 · File: `doc-002-upload-a-document.md`

**DOC-DOC-003 — Replace a document file** · S7
- Role: M, S (own) · Nav: card **Replace file** → **Upload new file**
- Workflow: choose file → "<name>: new file uploaded, waiting for review."
- Shots (2): replace control; success
- Errors: "Only documents your agency uploaded can be replaced"; "A counselor or administrator has reviewed this document, so it can't be replaced"
- Related: DOC-004 · File: `doc-003-replace-a-file.md`

**DOC-DOC-004 — Review a document** · S7
- Role: M (verify/reject/changes); S with *Verify documents* (Mark verified only) · Nav: card **Review**
- Workflow: Master: Decision → Reason (required for reject/changes) → **Save decision**; Staff: **Mark verified**
- Shots (3): Master form with reason; Staff Mark verified; rejected card
- Errors: "Your agency Master hasn't given you permission to verify documents"; "Only an agency Master can reject documents or request changes"; "Give a reason when you reject…"; "This document has already been reviewed"
- Related: TEAM-004, APP-008 · File: `doc-004-review-a-document.md`

**DOC-DOC-005 — Document history** · S7
- Role: M, S (own) · Nav: card **History** · Shots (1) · Errors: "The history could not be loaded."
- Related: DOC-004 · File: `doc-005-document-history.md`

**DOC-DOC-006 — Request an additional document** · S7
- Role: M, S (own) · Nav: Documents → **Request a document**; **Documents → Additional** → **Cancel request**
- Workflow: Student → Document type → Note → **Add request** → "Request added to Additional documents."; fulfil via upload "Fulfils request"
- Shots (3): request form; Additional list; cancelled notice
- Errors: "An open request for this document already exists"; "Too many document requests today -- try again later"
- Related: DOC-002, NOTIF-001 · File: `doc-006-request-a-document.md` · Open: U10

### Module TASK — Tasks (`tasks/`)

**DOC-TASK-001 — View tasks and follow-ups** · S5
- Role: M, S (own) · Nav: **Tasks & Follow-ups** → Open / Overdue / Done / Cancelled / All; dashboard **Open tasks**
- Shots (2): Open view; Overdue badge · Errors: "Unable to load tasks." + Retry
- Related: TASK-002, NOTIF-001 · File: `task-001-view-tasks.md`

**DOC-TASK-002 — Add, edit, complete or cancel a task** · S5
- Role: M, S (own) · Nav: **New task**; card **Edit** / **Mark done** / **Cancel task** → **Confirm cancel**
- Workflow: Student → Title → Due → Application → Notes → **Add task** → "“<title>” added."
- Shots (4): form with past-time hint; added; done; cancel confirm
- Validation: Title required ≤200; Due required; notes ≤2000; 100 open tasks per student
- Errors: "This task is closed"; "This student already has 100 open tasks…"; archived read-only text
- Related: STU-003 · File: `task-002-manage-a-task.md`

### Module NOTIF — Notifications (`notifications/`)

**DOC-NOTIF-001 — Read notifications** · S8
- Role: M, S · Nav: **Notifications** (badge) or top-bar badge
- Preconditions: events from S4–S7; reminders need worker + beat
- Workflow: read list ("new" badge) → **Open** marks read and goes to the related page; no "Mark all read"
- Shots (3): unread list; sidebar badge; empty state
- Related: STU-005, DOC-004/006, APP-005, TASK-002 · File: `notif-001-notifications.md` · Open: U14

### Module COMM — Commissions (`commissions/`)

**DOC-COMM-001 — View and claim commissions** · S8
- Role: M (Staff: hidden, 403) · Nav: **Commissions**
- Preconditions: an *eligible* commission (ADM-006)
- Workflow: read table → Claim commission form → commission reference → submit → "Commission claimed." (CLM-YYYYMMDD-XXXXXX)
- Shots (2): table; claim success
- Errors: "Commission not found"; "Commission cannot be claimed in its current status"
- Related: APP-009, ADM-006, RPT-003 · File: `comm-001-commissions.md` · Open: U18

### Module RPT — Reports (`reports/`)

**DOC-RPT-001 — Run agency reports** · S8
- Role: M; S with *View reports* (no Staff performance/Commission tabs, no Staff member filter) · Nav: **Reports**
- Workflow: choose tab (Students, Applications, Universities, Countries, Intakes, Staff performance, Enrollments) → From/To + filters → **Apply** / **Clear filters**; 50 rows per page
- Shots (9): 7 tabs; filtered; Staff C view
- Errors: "Couldn't load this report."; filter errors; Staff A refusal "Your agency Master hasn't given you access to reports"
- Related: RPT-002, TEAM-004 · File: `rpt-001-agency-reports.md`

**DOC-RPT-002 — Export a report to CSV** · S8
- Role: as RPT-001 · Nav: report → **Download CSV**
- Shots (1) · Validation: ≤10,000 rows; 30 exports / 10 min
- Errors: "This report has more than 10,000 rows; narrow the filters"; "You've downloaded a lot of reports in a short time…"
- Related: RPT-001 · File: `rpt-002-export-csv.md`

**DOC-RPT-003 — Commission report** · S8
- Role: M · Nav: Reports → **Commission** · Shots (1)
- Workflow: From/To → totals per currency; By status/university/country/intake; CSV
- Errors: "No commissions in this period." · Related: COMM-001 · File: `rpt-003-commission-report.md`

### Module TEAM — Team & staff (`team/`)

**DOC-TEAM-001 — Invite or deactivate a Master** · S3
- Role: M · Nav: **Team** → Invite a Master → **Send invite**; **Deactivate** → **Confirm deactivate**
- Workflow: Full name, Email, Phone → "Invite sent."; max 3 active Masters
- Shots (4): team list; invite form; limit reached; deactivate confirm
- Errors: "This agency already has 3 active Masters"; "An agency must keep at least one active Master"; 10 invites/24 h
- Related: AUTH-004 · File: `team-001-masters.md` · Open: U13

**DOC-TEAM-002 — Create a staff login** · S3
- Role: M · Nav: Team → Staff → **Add staff**
- Workflow: Full name, Email, Phone → "{code} created. A set-password link was emailed to {email}."
- Shots (4): empty list; form; success; list with badges
- Errors: "Email already exists"; email-not-delivered variant; 20 creates/resets per 24 h
- Related: AUTH-004, TEAM-004 · File: `team-002-create-staff.md`

**DOC-TEAM-003 — Edit, reset, deactivate, reactivate staff** · S3
- Role: M · Nav: staff row **Edit** / **Reset** / **Deactivate** / **Reactivate**
- Shots (3): edit; reset confirm; deactivated row
- Errors: "A link was just sent; wait N seconds…"; "Reactivate this staff member first"
- Related: AUTH-003 · File: `team-003-manage-staff.md`

**DOC-TEAM-004 — Set staff permissions** · S3
- Role: M · Nav: staff row **Permissions** → Verify documents / View reports → Save → "{code} permissions saved."
- Shots (2): form; Staff sidebar with Reports
- Related: DOC-004, RPT-001 · File: `team-004-staff-permissions.md` · Open: U12

**DOC-TEAM-005 — Staff activity** · S3 (re-shoot after S7)
- Role: M · Nav: staff row **Activity** · Shots (2): activity list; empty
- Errors: "Unable to load activity." · Related: PERF-001 · File: `team-005-staff-activity.md`

### Module PERF — Staff performance (`staff-performance/`)

**DOC-PERF-001 — View staff performance** · S8
- Role: M (Staff: link hidden; typed URL refused) · Nav: **Staff Performance**; dashboard **View staff performance**
- Workflow: From/To → **Apply**; Show funnel for; By staff member table
- Shots (4): default; filtered; one staff funnel; date error / Staff refusal
- Validation: "'To' must be on or after 'From'."
- Related: DASH-001, TEAM-005 · File: `perf-001-staff-performance.md`

### Module ADM — Agency administration (`docs/admin-manual/`, shots → `screenshots/admin-agencies/`)

**DOC-ADM-001 — Approve, reject, suspend, reinstate agencies** · S2
- Role: OA · Nav: Overseas Admin sidebar **Agents** → tabs Pending / Approved / Suspended / Rejected
- Workflow: search → **Approve** / **Reject** / **Suspend** → **Confirm suspend** / **Reinstate** → "{name} approved." etc.
- Shots (6): 4 tabs; suspend confirm; success notice
- Errors: "Cannot {action} an organisation that is {status}"; "Unable to load agent organisations."
- Related: AUTH-001, AUTH-003, ADM-004 · File: `adm-001-agency-approvals.md`

**DOC-ADM-002 — Agent network list** · S9
- Role: OA, SA (read) · Nav: **Agent network** → tabs All / Active / Suspended / Pending / Rejected; search
- Shots (3): All with counts; filtered; search no-match
- Related: ADM-003 · File: `adm-002-agent-network.md`

**DOC-ADM-003 — Agency detail and drill-down** · S9
- Role: OA, SA (read) · Nav: Agent network → agency name
- Workflow: figures; Commission and Deposits tables; Masters; Agency records Students (Active/Archived) / Applications; every drill-down is audited
- Shots (5): detail with two currencies; Students tab; Archived; Applications tab; not-found
- Related: ADM-004 · File: `adm-003-agency-detail.md`

**DOC-ADM-004 — Suspend / reinstate from agency detail** · S9
- Role: OA · Nav: agency detail → **Suspend** → **Confirm suspend**; **Reinstate**; pending/rejected → **Review in Agent Approvals**
- Shots (3): confirm; suspended + Reinstate; pending link
- Related: ADM-001, AUTH-003 · File: `adm-004-suspend-reinstate.md`

**DOC-ADM-005 — Deposit remittance and refund** · S9 (needs a paid deposit from S6)
- Role: OA (SA read-only) · Nav: **Agent deposits** → Paid / Remitted / Refunded / Awaiting payment / All
- Workflow: **Record remittance** (date, reference) → **Save remittance**; **Record refund** (date, amount, reason) → **Save refund** → **Yes, record refund**
- Shots (5): Paid tab; remit form; refund form; refund confirm; validation error
- Validation: date not future and not before paid date; refund ≤ paid amount; reference ≤100; reason ≤500
- Errors: "Only a paid deposit can be marked remitted"; "A refund cannot exceed the paid amount"
- Related: APP-007 · File: `adm-005-agent-deposits.md`

**DOC-ADM-006 — Commission amounts and payouts** · S8 (with COMM-001)
- Role: OA · Nav: **Commissions** → Set/adjust commission amount; Approve commission payout
- Workflow: commission reference + amount (+currency) → "Commission amount updated." (estimated → eligible); after Master claims, a different OA approves payout → "Payout approved -- commission marked paid."
- Shots (3): table with states; set amount; approve payout
- Errors: "Commission amount can no longer be adjusted once claimed"; "Commission must be claimed by the Agent before payout can be approved"; "The Overseas Admin who created this commission cannot also approve its own payout"
- Related: COMM-001, APP-009 · File: `adm-006-commissions.md`

**DOC-ADM-007 — Super Admin access to agency screens** · S9
- Role: SA · Nav: typed URLs (`/overseas/admin/agent-network`, `/agent-deposits`, `/agents`, `/commissions`) — no links in the Super Admin sidebar
- Shots (2): network without actions; deposits read-only
- Related: ADM-001..006 · File: `adm-007-super-admin-access.md` · Open: U15, U16

**DOC-ADM-008 — Resend a staff welcome link** · S3
- Role: OA · Nav: Users (role agent) → resend — **VERIFICATION REQUIRED**
- Shots (2) · Related: TEAM-002, AUTH-004 · File: `adm-008-resend-welcome-link.md` · Status: **code review partial** · Open: U17

**Estimated screenshots: 178** (AUTH 18 · DASH 4 · STU 28 · UNI 5 · APP 37 · DOC 16 · TASK 6 · NOTIF 3 · COMM 2 ·
RPT 11 · TEAM 15 · PERF 4 · ADM 29).

---

## Self-review (S1)
- **Coverage:** all 54 analysis features have a record and exactly one owning session (S2: 7, S3: 6, S4: 10, S5: 7,
  S6: 4, S7: 6, S8: 9, S9: 5 = 54). STU-008, TEAM-005 and APP-004 get extra screenshots in a later session.
- **Placeholders:** remaining "VERIFICATION REQUIRED" items are deliberate (U1–U19 in the analysis), not plan gaps.
- **Dependencies:** personas before features that need them (S2 agencies → S3 staff → S4 students → S5/S6
  applications → S7 documents → S8 aggregates → S9 admin money views).
