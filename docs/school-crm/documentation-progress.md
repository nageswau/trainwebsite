# School CRM Documentation — Progress Tracker

| | |
|---|---|
| Code baseline | `main` @ `ce1f07c2` (S1 discovery). Record any later `main` used for browser work here, with the affected features re-checked. |
| Stack used for browser work | `schooldocs` compose project from worktree `.claude/worktrees/school-docs` (detached at docs commit `24a22627` = `main` `ce1f07c2` + docs). Web http://localhost:3020, api :8020. Untracked `docker-compose.docs.yml` adds Mailpit on **127.0.0.1:8026** (the Agent CRM docs stack holds 8025). Untracked `.env` = repo `.env` with `FRONTEND_URL`/ports changed, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, no SMTP credentials, **`SMTP_FROM_EMAIL=no-reply@edusphere.local`** (without it the app reports "email is not configured"), `EMAIL_WEBHOOK_URL` empty. Owner approved Claude starting, seeding and resetting this stack (2026-10-05). |
| Docs branch | `docs/school-crm-user-guide` (from `main` @ `ce1f07c2`) |
| Last session | S2 Environment, capture tooling, school administration — 2026-10-05 |
| Next session | S3 — Account access and Team. Start from the S2 data: rerun `sch-s2-admin.capture.ts` on a fresh DB (≈35 s), or restore the S2 snapshot if one exists in the session scratchpad. |

**Column values:**
- **Code Reviewed:** YES / PARTIAL / NO. YES at S1 means reviewed from source at `ce1f07c2`, with file:line evidence in `discovery/`.
- **Browser Verified:** YES / PARTIAL / NO.
- **Screenshot:** YES / NO / N/A.
- **Documented:** YES / DRAFT / NO.
- **Reviewed:** PASSED / FAILED / NO.

A feature is **COMPLETE** only when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES (or N/A), Documented = YES
and Reviewed = PASSED.

**Totals (after S2):** 86 features · 7 browser-verified · 7 documented · 0 complete (final review is S12).

| ID | Module | Feature | Code Reviewed | Browser Verified | Screenshot | Documented | Reviewed |
|---|---|---|---|---|---|---|---|
| DOC-SCH-AUTH-001 | Account access | Sign in to the School portals (and where each role lands) | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-002 | Account access | Accept a school invitation and set up your login | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-003 | Account access | Set your first password from a welcome link | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-004 | Account access | Forgot / reset your password | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-005 | Account access | Change your password | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-006 | Account access | My profile and notification settings | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-007 | Account access | Sign out and session expiry | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-008 | Account access | "Access unavailable" messages (signed out, wrong portal, deactivated, other school's student) | YES | NO | NO | NO | NO |
| DOC-SCH-AUTH-009 | Account access | Find your way around: sidebar, role label, mobile menu | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-001 | Dashboards | Coordinator dashboard (20 KPI tiles, Your school, Upcoming activities, Results & guidance) | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-002 | Dashboards | Principal dashboard (School at a glance, Your school roster, Results & guidance) | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-003 | Dashboards | Teacher dashboard (Your students, Results & guidance) | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-004 | Dashboards | Parent dashboard: My children, Upcoming sessions, Important notifications (incl. children at several schools) | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-005 | Dashboards | Academic Team dashboard: layout and sections | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-006 | Dashboards | Career Counselor dashboard: layout and sections | YES | NO | NO | NO | NO |
| DOC-SCH-DASH-007 | Dashboards | Psychometric Team dashboard: layout and sections | YES | NO | NO | NO | NO |
| DOC-SCH-STU-001 | Students & roster | View the student roster | YES | NO | NO | NO | NO |
| DOC-SCH-STU-002 | Students & roster | Add one student | YES | NO | NO | NO | NO |
| DOC-SCH-STU-003 | Students & roster | Edit a student (incl. teacher assignment) | YES | NO | NO | NO | NO |
| DOC-SCH-STU-004 | Students & roster | Link a parent to a student | YES | NO | NO | NO | NO |
| DOC-SCH-STU-005 | Students & roster | Upload the roster in bulk (CSV) | YES | NO | NO | NO | NO |
| DOC-SCH-STU-006 | Students & roster | Student profile and journey timeline (grade/transfer history, scorecard, funding cases) | YES | NO | NO | NO | NO |
| DOC-SCH-STU-007 | Students & roster | Add, replace or remove a student photo | YES | NO | NO | NO | NO |
| DOC-SCH-STU-008 | Students & roster | Download a student progress report (PDF) | YES | NO | NO | NO | NO |
| DOC-SCH-STU-009 | Students & roster | Promote or hold back students for the new academic year | YES | NO | NO | NO | NO |
| DOC-SCH-XFER-001 | Transfers | Request a transfer out to another school | YES | NO | NO | NO | NO |
| DOC-SCH-XFER-002 | Transfers | Request a student from another school (by Student ID) | YES | NO | NO | NO | NO |
| DOC-SCH-XFER-003 | Transfers | Track and cancel transfer requests | YES | NO | NO | NO | NO |
| DOC-SCH-ACT-001 | Activities & attendance | Schedule an activity | YES | NO | NO | NO | NO |
| DOC-SCH-ACT-002 | Activities & attendance | Mark attendance for an activity | YES | NO | NO | NO | NO |
| DOC-SCH-ACT-003 | Activities & attendance | Give feedback on a completed EduSphere activity | YES | NO | NO | NO | NO |
| DOC-SCH-ACT-004 | Activities & attendance | View activity feedback | YES | NO | NO | NO | NO |
| DOC-SCH-ACT-005 | Activities & attendance | Take daily class attendance | YES | NO | NO | NO | NO |
| DOC-SCH-TEAM-001 | Team | Invite a Principal, Teacher or Parent | YES | NO | NO | NO | NO |
| DOC-SCH-TEAM-002 | Team | View your team and pending invites | YES | NO | NO | NO | NO |
| DOC-SCH-TEAM-003 | Team | Deactivate or reactivate a team account | YES | NO | NO | NO | NO |
| DOC-SCH-RPT-001 | Reports & analytics | Download the school report (PDF) | YES | NO | NO | NO | NO |
| DOC-SCH-RPT-002 | Reports & analytics | School summary: metric tiles, students by grade, service delivery, activities & attendance | YES | NO | NO | NO | NO |
| DOC-SCH-RPT-003 | Reports & analytics | Grade-wise comparison | YES | NO | NO | NO | NO |
| DOC-SCH-RPT-004 | Reports & analytics | Student development, at-risk students and top performers | YES | NO | NO | NO | NO |
| DOC-SCH-RPT-005 | Reports & analytics | Student progress scorecards | YES | NO | NO | NO | NO |
| DOC-SCH-RPT-006 | Reports & analytics | Global education pipeline | YES | NO | NO | NO | NO |
| DOC-SCH-ENT-001 | Entitlements | View your school's partnership entitlements | YES | NO | NO | NO | NO |
| DOC-SCH-ENT-002 | Entitlements | Partnership tiers explained (what each tier includes; "not included" messages) | YES | NO | NO | NO | NO |
| DOC-SCH-NOTIF-001 | Notifications | Notifications for school staff | YES | NO | NO | NO | NO |
| DOC-SCH-NOTIF-002 | Notifications | Notifications for parents (what triggers them) | YES | NO | NO | NO | NO |
| DOC-SCH-PAR-001 | Parent | Your child's profile and progress page | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-001 | Academic Team | Portfolio progress | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-002 | Academic Team | Upload a result as Draft | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-003 | Academic Team | Verify and publish results (two-person rule) | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-004 | Academic Team | Bulk entry: results (CSV) | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-005 | Academic Team | Test preparation (IELTS / SAT): start and record the score | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-006 | Academic Team | Foreign language classes: start and mark certified | YES | NO | NO | NO | NO |
| DOC-SCH-ACAD-007 | Academic Team | Bulk entry: test preparation and language classes (CSV) | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-001 | Career Counselor | Add a career guidance / counselling record | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-002 | Career Counselor | Edit a record and move its status | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-003 | Career Counselor | Record a student's career preferences | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-004 | Career Counselor | Set a student's career goal (360° view) | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-005 | Career Counselor | Find and create skills batches | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-006 | Career Counselor | Edit, close or reopen a skills batch | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-007 | Career Counselor | Enrol students and change enrolment status (complete, certify, withdraw) | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-008 | Career Counselor | Add sessions and take batch attendance | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-009 | Career Counselor | Add assessments and record scores | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-010 | Career Counselor | Open a funding support case | YES | NO | NO | NO | NO |
| DOC-SCH-CAR-011 | Career Counselor | Move a funding case through its stages or close it | YES | NO | NO | NO | NO |
| DOC-SCH-PSY-001 | Psychometric Team | Assign a psychometric assessment | YES | NO | NO | NO | NO |
| DOC-SCH-PSY-002 | Psychometric Team | Attach an assessment report | YES | NO | NO | NO | NO |
| DOC-SCH-PSY-003 | Psychometric Team | Record or edit assessment results | YES | NO | NO | NO | NO |
| DOC-SCH-PSY-004 | Psychometric Team | Bulk entry: assessments (CSV) | YES | NO | NO | NO | NO |
| DOC-SCH-S360-001 | Student 360° | Student 360° view: the 16 tabs and what each role sees | YES | NO | NO | NO | NO |
| DOC-SCH-PORT-001 | Digital Portfolio | Digital Portfolio overview and completion % | YES | NO | NO | NO | NO |
| DOC-SCH-PORT-002 | Digital Portfolio | Add, edit or delete portfolio entries | YES | NO | NO | NO | NO |
| DOC-SCH-PORT-003 | Digital Portfolio | Record a Skill India certification | YES | NO | NO | NO | NO |
| DOC-SCH-PORT-004 | Digital Portfolio | Internship tracking and certificate upload (Platinum) | YES | NO | NO | NO | NO |
| DOC-SCH-PORT-005 | Digital Portfolio | Write the personal statement | YES | NO | NO | NO | NO |
| DOC-SCH-SADM-001 | School administration | Partner Schools list | YES | YES | YES | YES | NO |
| DOC-SCH-SADM-002 | School administration | Create a school and seed its Coordinator | YES | YES | YES | YES | NO |
| DOC-SCH-SADM-003 | School administration | Edit a school profile and change its partnership tier | YES | YES | YES | YES | NO |
| DOC-SCH-SADM-004 | School administration | Onboard several schools by CSV | YES | YES | YES | YES | NO |
| DOC-SCH-SADM-005 | School administration | Create school staff accounts (Academic Team / Career Counselor / Psychometric Team) and their school portfolio | YES | YES | YES | YES | NO |
| DOC-SCH-SADM-006 | School administration | Start an overseas application for a school student | YES | NO | NO | NO | NO |
| DOC-SCH-SADM-007 | School administration | Review school transfer requests (approve / reject) | YES | NO | NO | NO | NO |
| DOC-SCH-SADM-008 | School administration | School Analytics | YES | NO | NO | NO | NO |
| DOC-SCH-SADM-009 | School administration | Activity Feedback across schools | YES | NO | NO | NO | NO |
| DOC-SCH-SADM-010 | School administration | Re-send a set-password link to a school user (Users page) | YES (Users panel reviewed S2) | YES | YES | YES | NO |
| DOC-SCH-SADM-011 | School administration | Super Admin and the school screens (what Super Admin can and cannot open) | YES | YES | YES | YES | NO |

## Deliverables outside the feature rows
| Deliverable | Session | Status |
|---|---|---|
| `documentation-analysis.md` | S1 | DONE |
| `documentation-plan.md` | S1 | DONE |
| `documentation-progress.md` (this file) | S1 | DONE |
| `screenshot-index.md` (skeleton) | S1 | DONE (no rows yet) |
| `discovery/01..04` evidence appendices | S1 | DONE |
| Capture tooling: `shoot()` options `root` / `center` / `element`, instant scrolling, bounded `networkidle`; `noPrefetch()`; `mailLink(pattern)` + `inviteLink()`; `tests/doc-capture/school/`; link-check root argument | S2 | DONE (Agent CRM specs still list and type-check) |
| `user-manual/README.md`, `admin-manual/README.md` | S11 | NO |
| Role guides (9): school-coordinator, principal, teacher, parent, academic-team, career-counselor, psychometric-team, overseas-admin-schools, super-admin-schools | S11 | NO |
| `faq.md`, `troubleshooting.md` | S11 | NO |
| `documentation-review-report.md` | S12 | NO |

## Unresolved verification items
All items from `documentation-analysis.md` §12.1 are open. Owner-dependent ones:
- **U3:** decided (see the table below).
- **U1 / U2:** session length and the reset email. These decide how AUTH-004 / AUTH-007 are written.
- **U12:** the Users page re-send flow, which needs a code review in S2.

| ID | Item | Session | Status |
|---|---|---|---|
| U1 | Session ends at ~60 min (no refresh call) | S3 | OPEN |
| U2 | Reset email carries a token, not a link (webhook only) | S3 | OPEN |
| U3 | Active academic year: no admin UI | S6 | DECIDED 2026-10-05: in S6 Claude gives the owner the exact `POST`/`PATCH /overseas-admin/academic-years` calls (as Overseas Admin); the owner runs them on the docs stack. The guide says the year is set up by EduSphere and notes the missing admin screen. |
| U4 | `/school/coordinator/students/new` message | S4 | OPEN |
| U5 | Over-length fields / malformed DOB → probable 500 | S4, S5, S7 | OPEN |
| U6 | Browser-native validation wording | all | OPEN |
| U7 | Pydantic 422 wording on admin forms | S2 → later | OPEN (not reachable through the S2 happy/error paths; messages marked "From code" in SADM-002/004) |
| U8 | Parent notifications never marked read | S10 | OPEN |
| U9 | "Upcoming session" time in UTC? | S5 | OPEN |
| U10 | Delivery channels enabled in the docs stack | S2 | PARTIAL: email works (Mailpit). WhatsApp/SMS not configured on the docs stack, so those channels are documented from code only. |
| U11 | Super Admin "Workspace not found" on three school pages | S2 | CONFIRMED in browser (Schools, School Staff, School Applications); Transfers and Activity Feedback open with the Overseas Admin sidebar/label; Analytics opens with the SA sidebar. Documented in SADM-011. |
| U12 | Users page re-send set-password for school users | S2 | CLOSED: same Users panel as Agent CRM DOC-ADM-008 (`WorkflowPanel.tsx:446` shows it to Overseas Admin on `users`); re-send verified for a school specialist. |
| U13 | Template example row imported as a real student | S4 | OPEN |
| U14 | Teacher portfolio editing as seen by a Teacher | S7 | OPEN |
| U15 | What moves school-linked applications past `enquiry` | S9 | OPEN |
| U16 | 360° tab list at mobile width | S9 | OPEN |

## Discovered functionality not in the original plan
Record anything found during browser work that has no Doc ID here, with a recommendation.

| Found in | What | Recommendation |
|---|---|---|
| S2 | Tier-change notices are also **emailed**. The school's Coordinator gets "Your partnership is now {Tier} -- {School}" or "Your partnership changed from {A} to {B} -- {School}". The acting Overseas Admin gets "Tier change recorded: {School}, {A} → {B} -- {School}". | Folded into SADM-003 "Expected Result". NOTIF-001 (S10) covers the in-app side. |

## Product findings for the owner (as-built, documented, not changed)
See `documentation-analysis.md` §12.2 (17 items). Notable:
- Super Admin is blocked from Schools / School Staff / School Applications.
- Staff school portfolios cannot be changed after the account is created.
- There is no academic-year admin UI.
- Frontend role guards are inconsistent.
- Parent notifications never clear.
- Several raw codes are shown to users.
- **New in S2 (cosmetic):** the login page's large logo is invisible. The page uses the light-on-dark logo (`logo-on-dark`) inside a white box (`/overseas/login`; the same is seen in the Agent CRM screenshot). Documented as-is.

## Session log
| Session | Date | Summary |
|---|---|---|
| S2 | 2026-10-05 | Owner approved Claude running and resetting the `schooldocs` stack.

**Stack set-up:**
- Built and seeded from `ce1f07c2`, with Mailpit on :8026.
- The first run reported "email is not configured" until `SMTP_FROM_EMAIL` was added to the docs `.env`.
- Chromium on Docker Desktop left Next.js router-prefetch streams open, which stalled screenshots (the 6-connections-per-host limit). Added the test-only `noPrefetch()`.
- The site's `html{scroll-behavior:smooth}` broke screenshot framing. Helper scrolls are now instant, with new `center` / `element` options.

**Capture and docs:**
- `sch-s2-admin.capture.ts` runs green in about 35 s and creates the D2/D3/D4/D18 data: Docs Bronze (Silver→Bronze notices), Docs No-Tier, Docs Platinum Two, Docs Renewal (+30 d), Docs Expired (yesterday), plus staff Docs AT/CC/PT and Docs Empty Portfolio Counselor.
- 23 screenshots reviewed: no secrets, correct states.
- SADM-001..005, 010 and 011 written.
- U11 confirmed, U12 closed, U10 partial. |
| S1 | 2026-10-05 | Owner chose `docs/school-crm/` (not the top-level Agent CRM paths) and the scope "school portals + admin school management". Graphify orientation plus four parallel source-discovery passes at `ce1f07c2`. Wrote the analysis (16 modules, 86 features, 10 roles, 54 routes, ~140 endpoints), the plan (S2–S12), this tracker, the screenshot-index skeleton and the discovery appendices (seed password redacted). No browser work. |
