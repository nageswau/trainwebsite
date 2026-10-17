# Overseas BDM CRM User Documentation — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans. Work one session at a time, in this plan's
> order. Tick the checkboxes here and update `docs/bdm-crm/documentation-progress.md` at the end of every session.

**Goal:** Verified end-user, manager, administrator and role-based documentation for the EduSphere **Overseas BDM CRM**
(Agent BDM, School BDM, BDM Manager, plus the Overseas Admin / Super Admin BDM screens), with Playwright screenshots.

**Architecture:**
- **Feature files.** One Markdown file per Doc ID: BDM `docs/bdm-crm/user-manual/<module>/`, manager `docs/bdm-crm/manager-manual/<module>/`, admin `docs/bdm-crm/admin-manual/`.
- **Screenshots** in `docs/bdm-crm/screenshots/<module>/` (module = the manual folder's last segment, `admin` for admin-manual), indexed in `screenshot-index.md`.
- **Source of behaviour.** Code reviewed in Phase 1 (`documentation-analysis.md` + `discovery/`), confirmed in the browser before it is written.
- **Reproducibility.** Test-only Playwright capture specs in `apps/web/tests/doc-capture/bdm/`.

## Global Constraints
- **Scope.** The 117 Doc IDs below. Anything else → "Discovered functionality" in the progress file. College BDMs, the Management dashboards (pointer only, REF-002) and "Management tasks" are out.
  - Never edit `docs/school-crm/`, `docs/telecaller-crm/` or the Agent CRM docs at the top of `docs/`.
- **Code baseline.** `main` @ `6fee294d`. When `main` moves, re-check features whose files changed (`git diff --stat 6fee294d..<new> -- apps/`).
- **No product code changes.** Capture tooling under `apps/web/tests/doc-capture/` and `docs/tooling/` is test/docs only.
- **Screenshot settings.** Chromium 1440 × 900, light, `deviceScaleFactor` 1, locale `en-IN`, timezone `Asia/Kolkata`; viewport shots; `fullPage` only when a step needs the whole form (note it). One 390 px shot for NAV-001.
- **Never show passwords, tokens or keys.** Mask password inputs, "Demo accounts" cards and "Development only" boxes; never put a welcome/reset URL with a token in a doc or image; never paste the seed password; never screenshot Mailpit.
- **Test data only.** Docs personas use `@example.test`; every organisation, contact, trip and MoU created is prefixed `Docs `; fictional phone numbers (`+91 90000 0xxxx`). Exceptions (D6): the seeded EduSphere Partner Agency and Sunrise Public School appear as linked partners.
- **VERIFICATION REQUIRED** for anything not seen in the browser; leave it out of the numbered steps.
- **As-built.** Document P1–P20 neutrally (analysis §9). Never promise unbuilt items (analysis §1.4).
- **Writing style.** Simple English, numbered steps, bold UI labels exactly as on screen, one feature per file, mandatory template. Add **What each BDM type sees** (Agent vs School) and **What each role sees** tables where behaviour differs.
- **Terminology:** **Agent BDM**, **School BDM**, **BDM Manager** ("Manager" after first use), **Overseas Admin**, **Super Admin**, **Telecaller**; **organisation**, **contact**, **pipeline stage**, **Lost**, **MoU**, **onboarding request**, **appointment**, **meeting report**, **follow-up** / **task**, **activity**, **trip**, **travel report**, **daily report**, **meeting request**, **targets**, **Master view**.
- **Capture helpers.** `noPrefetch(context)` before navigating; `shoot(..., { element })` for long cards, `{ center }` for messages; `behavior: "instant"` scrolls; passwords only from `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`; IDs pass between specs via `DOCS_BDM_FILE` (scratchpad JSON).
- **Docker.** Owner approved (2026-10-17) Claude starting, seeding, resetting and snapshotting `bdmdocs` only. Never touch other compose projects.
- **Git.** Commit on `docs/bdm-crm-user-guide` with `docs: add <module> BDM CRM guide`. Stage explicit paths (`docs/bdm-crm/`, `apps/web/tests/doc-capture/bdm/`, shared tooling when changed). Never stage `graphify-out/`, `.env`, `docker-compose.docs.yml`. The owner pushes.

## Review Focus
1. **Agent vs School.** Every feature that differs by type documents both, with one screenshot per type.
2. **Same screen, different role.** Organisation, appointment and trip pages as BDM vs manager (read-only + reassign/restore/approve).
3. **Locked states.** Not-assigned organisation (read-only), archived, Lost, submitted daily report, completed/cancelled trip, declined meeting request (final), same-day windows.
4. **Overseas-only screens.** Docs BDM Manager has only Agent/School reports; College columns that still appear (P12) get a one-line note, never a College persona.
5. **Time-dependent behaviour (D5).** Record each capture date; S9 runs on a later day than S6; S10 ≥ 5 days after S5.
6. **Secrets.** Open every new PNG before committing.

## File structure
```
docs/bdm-crm/
  documentation-analysis.md  documentation-plan.md  documentation-progress.md  screenshot-index.md
  discovery/01..04-*.md
  user-manual/      README.md + account-access/ navigation/ my-day/ notifications/ calendar/ meeting-requests/ organisations/
                    pipeline/ mous/ onboarding/ appointments/ follow-ups/ activities/ travel/ daily-report/ reference/
  manager-manual/   README.md + navigation/ dashboard/ team/ organisations/ pipeline/ appointments/ activity/
                    daily-reports/ meeting-requests/ travel/ performance/ targets/
  admin-manual/     README.md + adm-001-… adm-011-…
  role-guides/      agent-bdm.md school-bdm.md bdm-manager.md overseas-admin-bdms.md super-admin-bdms.md
  demo-accounts.md  faq.md  troubleshooting.md  documentation-review-report.md
  screenshots/<module>/NN-<feature>-<step>.png
  pdf/
apps/web/tests/doc-capture/bdm/
```
Image links: manual feature files `../../screenshots/<module>/<file>.png`; admin-manual `../screenshots/admin/<file>.png`.

### Feature file template
```markdown
# <Feature name>
> Doc ID: DOC-BDM-XXX-NNN · Verified on <date> against `main` @ <commit> · Roles: <roles>

## Purpose
## Who Can Use This Feature
## Prerequisites
## How to Access
## Steps
### Step 1 — <action>
![<alt>](../../screenshots/<module>/<file>.png)
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

### Dependency order
S2 (stack, tooling, personas) → S3 (passwords, access) → S4 (organisations) → S5 (MoUs, onboarding) → S6 (appointments,
follow-ups, activities) → S7 (travel, approvals) → S8 (meeting requests, My Day, notifications) → **S9 on a later day**
(overdue, daily reports) → **S10 ≥ 5 days after S5** (manager oversight, alerts) → S11 (lifecycle, last) → S12 (guides, PDFs)
→ S13 (review). Rerun = reset `bdmdocs` (`down -v`, `up -d`, migrate, seed), clear Mailpit, rerun specs in order; restore the
previous session's `pg_dump` snapshot to iterate on one session.

### Standard session loop (S2–S11)
- [ ] **L1** Read the analysis, this plan, the progress file, the screenshot index and the relevant `discovery/` sections.
- [ ] **L2** Fetch `origin/main`; re-review changed files touching this session's routes. Check `bdmdocs` is up (start it if not — D3). Record URL, commit and **capture date**.
- [ ] **L3** Explore each feature in the browser as each relevant role and BDM type. Tick "Browser Verified" only for what was seen.
- [ ] **L4** Write/extend `apps/web/tests/doc-capture/bdm/bdm-sN-<module>.capture.ts`; run it; open every PNG.
- [ ] **L5** One feature file per Doc ID; **VERIFICATION REQUIRED** for unconfirmed points.
- [ ] **L6** `node docs/tooling/check-doc-links.mjs docs/bdm-crm`.
- [ ] **L7** Update `screenshot-index.md` and `documentation-progress.md`; snapshot the DB.
- [ ] **L8** Report; commit explicit paths; the owner pushes.

### S1 — Master planning — DONE 2026-10-17
- [x] Four parallel discovery passes; owner answers D1–D6; analysis (117 features), this plan, tracker, screenshot-index skeleton.

### S2 — Environment, capture tooling, admin provisioning (creates personas)
Features: ADM-001, ADM-002, ADM-005, ADM-006 (4).
- [ ] **S2.1** Stack: worktree `.claude/worktrees/bdm-docs`, `docker compose -p bdmdocs -f docker-compose.yml -f docker-compose.docs.yml` (never the Caddy override). Untracked `docker-compose.docs.yml` adds Mailpit `127.0.0.1:8028:8025`. Untracked `.env` = repo `.env` with `WEB_PORT=3040`, `API_PORT=8040`, `FRONTEND_URL=http://localhost:3040`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`, no SMTP credentials, `SMTP_FROM_EMAIL=no-reply@edusphere.local`, `ENVIRONMENT=development`. Worker and beat must run (`bdm012-reminders` every 300 s). Seed from `6fee294d`. Scratchpad: `docs-env.sh`, `reset-stack.sh`.
- [ ] **S2.2** Tooling (test-only): add `export const BDM_ROOT` to `apps/web/tests/doc-capture/shoot.ts` and a portal-aware `signIn()` (`/admin/login` for managers) with the default unchanged. **Use the same `signIn(portal)` shape as the telecaller docs S2** (cherry-pick it if that lands first) so the two branches merge cleanly. Add a `bdm` mode to `docs/tooling/build-pdfs.mjs` later (S12). Prove Agent/School specs still `--list`.
- [ ] **S2.3** Masking check on the two login pages.
- [ ] **S2.4** Standard loop. As Super Admin: create **Docs BDM Manager** (ADM-006). As Overseas Admin: create **Docs Agent BDM A**, **Docs Agent BDM B**, **Docs School BDM**, **Docs Spare BDM** (Employee IDs `DOCS-BDM-A`, `-B`, `-S`, `-X`; manager = Docs BDM Manager) (ADM-001); duplicate Employee ID error; edit (ADM-002); re-send link (ADM-005). Create a **Docs Telecaller** (Overseas) for S8 meeting requests.
- [ ] **S2.5** Snapshot `after-s2`.

### S3 — Account access and navigation
Features: AUTH-001, AUTH-002, AUTH-003, AUTH-004, AUTH-005, AUTH-006, AUTH-007, NAV-001, NAV-002 (9).
- [ ] Standard loop. Welcome links from Mailpit (AUTH-003) for each persona; wrong portal both ways; AUTH-004 delivery check (expect PARTIAL); profile pages and the P2 name-edit behaviour; access-unavailable cards; both sidebar tours (one 390 px mobile shot for NAV-001).

### S4 — Organisations, contacts, profiles, pipeline, leads
Features: UNI-001, ORG-001, ORG-002, ORG-003, ORG-004, ORG-005, CONT-001, PROF-001, PROF-002, PROF-003, PIPE-001, PIPE-002, PIPE-003, PIPE-004, LEAD-001, REF-001 (16).
- [ ] Standard loop as Docs Agent BDM A and Docs School BDM. ~8 Docs organisations across stages, contacts (1–20 rule), Agent and School profiles, type-change clear-first rule, duplicate warning, archive one (manager restores in S10), Lost + revive, stage history, pipeline board, a University-type organisation for UNI-001, student leads. Reference page from appendix 04 §4.

### S5 — MoUs, onboarding, partner links
Features: MOU-001, MOU-002, MOU-003, MOU-004, ONB-001, ONB-002, ORGP-001, ORGP-002, ADM-008, ADM-009, ADM-011 (11).
- [ ] Standard loop. MoUs in each status with a generated PDF (≤ 20 MB; PDF/JPEG/PNG); history and renewal. Agent org → Agreement Signed → onboarding request; School org → MoU Signed → onboarding request. As Overseas Admin link to **EduSphere Partner Agency** and **Sunrise Public School** (D6), then capture the Agent performance and School activity panels. BDM leads in `/overseas/admin/leads`. **Record the date — S10 must run ≥ 5 days later for the MoU 5-day alert (D5).**

### S6 — Appointments, follow-ups, activities, calendar
Features: CAL-001, APPT-001, APPT-002, APPT-004, APPT-005, APPT-006, APPT-007, FUP-002, FUP-003, FUP-004, ACT-001, ACT-002, ACT-003, ACT-004 (14).
- [ ] Standard loop. Book a batch of appointments ~3 minutes ahead, wait once, then confirm / reschedule / cancel / complete with meeting reports (Agent vs School outcomes) / no-show; same-day report edit and "Book the next meeting" (School). Follow-ups from reports and manual tasks with due dates **today and tomorrow** (they become overdue for S9). Activities incl. backdating; edit/delete today's; organisation timeline; calendar.

### S7 — Travel and approvals
Features: APPT-003, TRAV-001, TRAV-002, TRAV-003, TRAV-004, TRAV-005, TRAV-006, TRAV-007, TRAV-008, TRAV-009, TRAV-010, TRAV-011, TRAV-012, APPR-001, MTRIP-001, MTRIP-002 (16).
- [ ] Standard loop. Trips in every state: draft, submitted, withdrawn, rejected (reason) → fixed → resubmitted, approved, started, completed, cancelled; linked appointments; expenses; remarks; travel report. As Docs BDM Manager: approvals queue, approve, reject, travel report. Day-before reminder: plan a trip starting tomorrow (captured in S8/S9).

### S8 — Meeting requests, My Day, notifications
Features: DAY-001, DAY-002, DAY-003, DAY-004, DAY-005, NOTIF-001, NOTIF-002, NOTIF-003, MEET-001, MEET-002, MEET-003, MEET-004, APPT-008, MNOTIF-001, MMEET-001 (15).
- [ ] Standard loop. As the Docs Telecaller file a named request (to Docs Agent BDM A) and a pooled School request; as BDMs accept (book) and decline (reason). Manager meeting-request page. My Day (Agent and School tiles, targets card, requests card). Notifications: reminders, decision notices, email action links (Mailpit, not screenshotted); appointment reminder `?action=`; manager notifications.

### S9 — Daily reports and next-day states — run on a later day than S6
Features: FUP-001, RPT-001, RPT-002, RPT-003, RPT-004, MRPT-001, MRPT-002 (7).
- [ ] Standard loop. Overdue follow-ups tab (FUP-001). Live day report, submit with note (locks the day), Agent vs School tiles. Leave one BDM's previous day unsubmitted (AL-7 for S10). Manager 7-day grid and comment; BDM reads the comment.

### S10 — Manager oversight — run ≥ 5 days after S5
Features: MDASH-001, MDASH-002, MTEAM-001, MTEAM-002, MORG-001, MORG-002, MORG-003, MORG-004, MPIPE-001, MAPPT-001, MAPPT-002, MCAL-001, MFUP-001, MACT-001, MMOU-001, PERF-001, PERF-002, PERF-003, TGT-001, TGT-002, REF-002 (21).
- [ ] Standard loop as Docs BDM Manager. Dashboard tiles and alerts incl. AL-7 and the MoU 5-day alert (D5), team, Master view (College note per P12), organisations (reassign, restore the S4 archived org), MoU list, pipeline, appointments, calendar, follow-ups, activities, performance and drill-downs, targets (set one BDM, copy last month). REF-002 pointer page (no screenshot).

### S11 — Lifecycle (runs last)
Features: ADM-003, ADM-004, ADM-007, ADM-010 (4).
- [ ] Standard loop. Deactivate Docs Spare BDM with handover to Docs Agent BDM B; hand over an inactive BDM's work; reactivate. Create a **Docs Spare Manager** and move a BDM with a submitted trip under it; deactivate the Spare Manager with replacement Docs BDM Manager, and capture Super Admin fallback approvals at `/admin/bdm-travel-approvals` while the manager is inactive (ADM-010).

### S12 — Role guides, FAQ, troubleshooting, indexes, demo accounts, PDFs
- [ ] Role guides (`agent-bdm.md`, `school-bdm.md`, `bdm-manager.md`, `overseas-admin-bdms.md`, `super-admin-bdms.md`), `faq.md`, `troubleshooting.md`, the three manual READMEs, `demo-accounts.md` (D4: Docs BDM Manager ↔ Sanjay `bdm.manager@` — note Sanjay also manages College BDM Vivek; Docs Agent BDM A ↔ Rahul `bdm.agent@`; Docs School BDM ↔ Kavya `bdm.school@`). Add a `bdm` mode to `build-pdfs.mjs` and build the PDFs. Link check.

### S13 — Final review
- [ ] Parallel reviewers (accuracy vs code, secrets/screenshots, links/consistency, Agent-vs-School and role matrix). Fix findings; mark Reviewed PASSED / COMPLETE; write `documentation-review-report.md` with P1–P20 plus new findings.

---

## Feature records
Status at end of S1: code-reviewed at `6fee294d`, browser not verified, not documented. "Appx" = discovery file § with labels,
messages and file:line. Capture detail per feature is in the appendix rows (a) and (b).

### `user-manual/account-access/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| AUTH-001 | S3 | BDM | `auth-001-choose-your-bdm-portal-and-sign-in-as-an-agent-s.md` | 01 A1.1, 03 §1.1–1.3 |
| AUTH-002 | S3 | MGR | `auth-002-sign-in-as-a-bdm-manager-lands-on-dashboard.md` | 03 §1.3, 02 §0.1 |
| AUTH-003 | S3 | BDM, MGR | `auth-003-set-your-first-password-from-the-welcome-email.md` | 03 §1.4 |
| AUTH-004 | S3 | BDM, MGR | `auth-004-forgot-reset-your-password.md` | 03 §1.5 |
| AUTH-005 | S3 | BDM, MGR | `auth-005-change-your-password-and-sign-out.md` | 03 §1.5 |
| AUTH-006 | S3 | BDM, MGR | `auth-006-your-bdm-profile-and-the-account-profile-page.md` | 01 A1.3–A1.4, 03 §1.6 |
| AUTH-007 | S3 | BDM, MGR | `auth-007-access-unavailable-messages-no-bdm-profile-wrong.md` | 01 A1.1, 03 §0.2 |

### `user-manual/navigation/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| NAV-001 | S3 | BDM | `nav-001-bdm-portal-tour-sidebar-role-pill-agent-bdm-scho.md` | 01 A1.2 |

### `manager-manual/navigation/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| NAV-002 | S3 | MGR | `nav-002-manager-portal-tour-the-17-item-sidebar.md` | 02 §0.2 |

### `user-manual/my-day/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| DAY-001 | S8 | BDM | `day-001-my-day-today-s-appointments-upcoming-travel-foll.md` | 01 A2.2 |
| DAY-002 | S8 | Agent BDM | `day-002-my-day-agent-overview-tiles.md` | 01 A2.3 |
| DAY-003 | S8 | School BDM | `day-003-my-day-school-overview-tiles.md` | 01 A2.3 |
| DAY-004 | S8 | BDM | `day-004-my-day-monthly-targets-card.md` | 01 A2.4 |
| DAY-005 | S8 | BDM | `day-005-my-day-meeting-requests-card.md` | 01 A2.2 |

### `user-manual/notifications/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| NOTIF-001 | S8 | BDM | `notif-001-read-and-open-notifications.md` | 01 A3 |
| NOTIF-002 | S8 | BDM | `notif-002-reminders-appointment-travel-follow-up-mou-follo.md` | 01 A3.1 |
| NOTIF-003 | S8 | BDM | `notif-003-decision-notices-trip-approved-not-approved-onbo.md` | 01 A3.1 |

### `user-manual/calendar/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| CAL-001 | S6 | BDM | `cal-001-calendar-week-day-view-and-navigation.md` | 01 A4 |

### `user-manual/meeting-requests/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MEET-001 | S8 | BDM | `meet-001-meeting-request-inbox-and-filters-requests-from.md` | 01 A5, 03 §4.1 |
| MEET-002 | S8 | BDM | `meet-002-view-a-meeting-request.md` | 01 A5.3 |
| MEET-003 | S8 | BDM | `meet-003-accept-a-request-and-book-the-appointment.md` | 01 A5.3 |
| MEET-004 | S8 | BDM | `meet-004-decline-a-request-with-a-reason.md` | 01 A5.3 |

### `user-manual/organisations/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| UNI-001 | S4 | BDM | `uni-001-view-a-linked-university-master-record.md` | 01 A6 |
| ORG-001 | S4 | BDM | `org-001-browse-and-filter-your-module-s-organisations.md` | 01 B.0–B.1 |
| ORG-002 | S4 | BDM | `org-002-add-an-organisation-duplicate-warning.md` | 01 B.2 |
| ORG-003 | S4 | BDM | `org-003-open-an-organisation-read-only-when-not-assigned.md` | 01 B.3 |
| ORG-004 | S4 | BDM (assigned) | `org-004-edit-organisation-details.md` | 01 B.3 |
| ORG-005 | S4 | BDM (assigned) | `org-005-archive-an-organisation-your-manager-restores-it.md` | 01 B.3 |
| CONT-001 | S4 | BDM (assigned) | `cont-001-manage-contacts-add-edit-primary-delete-1-20.md` | 01 B.3 |
| PROF-001 | S4 | BDM | `prof-001-agent-organisation-details-type-profile.md` | 01 B.2–B.3 |
| PROF-002 | S4 | BDM | `prof-002-school-organisation-details-board-type-grades.md` | 01 B.2–B.3 |
| PROF-003 | S4 | BDM (assigned) | `prof-003-change-an-organisation-s-type-clear-first-rule.md` | 01 B.3 |
| LEAD-001 | S4 | BDM | `lead-001-add-and-view-student-leads-on-an-organisation.md` | 01 B.3, 03 §4.4 |

### `user-manual/pipeline/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| PIPE-001 | S4 | BDM (assigned) | `pipe-001-move-an-organisation-through-pipeline-stages-mov.md` | 01 B.3 |
| PIPE-002 | S4 | BDM (assigned) | `pipe-002-mark-an-organisation-lost-and-revive-it.md` | 01 B.3 |
| PIPE-003 | S4 | BDM | `pipe-003-read-the-stage-history.md` | 01 B.3 |
| PIPE-004 | S4 | BDM | `pipe-004-pipeline-board-mine-all-in-module-stage-tiles-lo.md` | 01 B.6 |

### `user-manual/reference/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| REF-001 | S4 | all | `ref-001-reference-lists-organisation-types-contact-roles.md` | 03 §5, 04 §4 |
| REF-002 | S10 | partner, SA | `ref-002-management-bdm-figures-pointer-only.md` | 03 §4.5 |

### `user-manual/mous/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MOU-001 | S5 | BDM (assigned) | `mou-001-start-and-edit-an-organisation-s-mou-status-date.md` | 01 B.4 |
| MOU-002 | S5 | BDM | `mou-002-upload-and-download-the-mou-document.md` | 01 B.4 |
| MOU-003 | S5 | BDM (assigned) | `mou-003-mou-history-expiry-and-renewal.md` | 01 B.4 |
| MOU-004 | S5 | BDM | `mou-004-mou-list-by-status.md` | 01 B.5 |

### `user-manual/onboarding/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| ONB-001 | S5 | Agent BDM | `onb-001-request-agent-onboarding-at-agreement-signed.md` | 01 B.3, 03 §4.2 |
| ONB-002 | S5 | School BDM | `onb-002-request-school-onboarding-mou-signed-active.md` | 01 B.3, 03 §4.3 |
| ORGP-001 | S5 | Agent BDM | `orgp-001-agent-performance-panel.md` | 01 B.3 |
| ORGP-002 | S5 | School BDM | `orgp-002-school-activity-panel.md` | 01 B.3 |

### `user-manual/appointments/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| APPT-001 | S6 | BDM | `appt-001-view-and-filter-your-appointments.md` | 01 C.1 |
| APPT-002 | S6 | BDM | `appt-002-book-an-appointment-overlap-warning.md` | 01 C.2 |
| APPT-003 | S7 | BDM | `appt-003-link-an-appointment-to-a-trip.md` | 01 C.2–C.3 |
| APPT-004 | S6 | BDM | `appt-004-appointment-detail-edit-details-and-history.md` | 01 C.3 |
| APPT-005 | S6 | BDM | `appt-005-confirm-reschedule-or-cancel-an-appointment.md` | 01 C.3 |
| APPT-006 | S6 | BDM | `appt-006-complete-with-a-meeting-report-or-mark-no-show.md` | 01 C.3 |
| APPT-007 | S6 | BDM | `appt-007-edit-the-meeting-report-the-same-day-book-the-ne.md` | 01 C.3 |
| APPT-008 | S8 | BDM | `appt-008-act-on-an-appointment-reminder.md` | 01 C.3, A3.1 |

### `user-manual/follow-ups/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| FUP-001 | S9 | BDM | `fup-001-follow-ups-tabs-counts-and-filters-incl-overdue.md` | 01 C.4 |
| FUP-002 | S6 | BDM | `fup-002-add-a-follow-up-or-task.md` | 01 C.4 |
| FUP-003 | S6 | BDM | `fup-003-mark-done-edit-or-cancel-a-task.md` | 01 C.4 |
| FUP-004 | S6 | BDM | `fup-004-follow-ups-created-from-meeting-reports.md` | 01 C.4 |

### `user-manual/activities/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| ACT-001 | S6 | BDM | `act-001-your-activities-for-a-day-with-counts.md` | 01 C.5 |
| ACT-002 | S6 | BDM | `act-002-log-an-activity-including-backdating.md` | 01 C.5 |
| ACT-003 | S6 | BDM | `act-003-edit-or-delete-today-s-activity.md` | 01 C.5 |
| ACT-004 | S6 | BDM | `act-004-organisation-activity-timeline.md` | 01 C.5 |

### `user-manual/travel/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| TRAV-001 | S7 | BDM | `trav-001-view-and-filter-your-trips.md` | 01 D.1 |
| TRAV-002 | S7 | BDM | `trav-002-plan-a-new-trip-draft.md` | 01 D.2 |
| TRAV-003 | S7 | BDM | `trav-003-open-a-trip-details-appointments-productivity.md` | 01 D.3 |
| TRAV-004 | S7 | BDM | `trav-004-edit-a-draft-or-rejected-trip.md` | 01 D.3 |
| TRAV-005 | S7 | BDM | `trav-005-submit-a-trip-for-approval-or-withdraw-it.md` | 01 D.0.1, D.3 |
| TRAV-006 | S7 | BDM | `trav-006-handle-a-rejected-trip-reason-fix-resubmit.md` | 01 D.3 |
| TRAV-007 | S7 | BDM | `trav-007-start-complete-or-cancel-a-trip.md` | 01 D.0.1 |
| TRAV-008 | S7 | BDM | `trav-008-record-trip-expenses.md` | 01 D.3 |
| TRAV-009 | S7 | BDM | `trav-009-trip-remarks.md` | 01 D.3 |
| TRAV-010 | S7 | BDM | `trav-010-trip-itinerary-appointments-linked-to-a-trip.md` | 01 D.3 |
| TRAV-011 | S7 | BDM | `trav-011-travel-report-of-a-completed-trip.md` | 01 D.4 |
| TRAV-012 | S7 | BDM | `trav-012-travel-notifications-and-the-day-before-reminder.md` | 01 D, A3.1 |

### `user-manual/daily-report/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| RPT-001 | S9 | BDM | `rpt-001-view-a-day-s-live-report.md` | 01 D.6 |
| RPT-002 | S9 | BDM | `rpt-002-submit-the-daily-report-with-a-note-locks-the-da.md` | 01 D.6 |
| RPT-003 | S9 | BDM | `rpt-003-read-a-submitted-report-and-your-manager-s-comme.md` | 01 D.6 |
| RPT-004 | S9 | BDM | `rpt-004-what-each-count-means-agent-vs-school-tiles.md` | 01 D.6.1 |

### `manager-manual/dashboard/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MDASH-001 | S10 | MGR | `mdash-001-read-the-bdm-overview-tiles.md` | 02 §1 |
| MDASH-002 | S10 | MGR | `mdash-002-act-on-dashboard-alerts-al-1-al-7.md` | 02 §1 |
| MNOTIF-001 | S8 | MGR | `mnotif-001-manager-notifications.md` | 02 §15 |

### `manager-manual/team/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MTEAM-001 | S10 | MGR | `mteam-001-view-the-bdms-who-report-to-you.md` | 02 §2 |
| MTEAM-002 | S10 | MGR | `mteam-002-read-the-master-view-type-bdm-linked-organisatio.md` | 02 §3 |

### `manager-manual/organisations/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MORG-001 | S10 | MGR | `morg-001-find-the-team-s-organisations.md` | 02 §4.1 |
| MORG-002 | S10 | MGR | `morg-002-read-an-organisation-s-profile-and-panels.md` | 02 §4.2 |
| MORG-003 | S10 | MGR | `morg-003-reassign-an-organisation-to-another-bdm-on-your.md` | 02 §4.2 |
| MORG-004 | S10 | MGR | `morg-004-restore-an-archived-organisation.md` | 02 §4.2 |
| MMOU-001 | S10 | MGR | `mmou-001-review-the-team-s-mous-by-status.md` | 02 §11 |

### `manager-manual/pipeline/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MPIPE-001 | S10 | MGR | `mpipe-001-team-pipeline-by-type-and-stage.md` | 02 §5 |

### `manager-manual/appointments/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MAPPT-001 | S10 | MGR | `mappt-001-filter-the-team-s-appointments.md` | 02 §6 |
| MAPPT-002 | S10 | MGR | `mappt-002-read-an-appointment-and-its-meeting-report.md` | 02 §6 |
| MCAL-001 | S10 | MGR | `mcal-001-view-a-bdm-s-calendar.md` | 02 §7 |

### `manager-manual/activity/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MFUP-001 | S10 | MGR | `mfup-001-review-the-team-s-follow-ups-and-tasks.md` | 02 §8 |
| MACT-001 | S10 | MGR | `mact-001-review-the-team-s-activities-for-a-day.md` | 02 §9 |

### `manager-manual/daily-reports/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MRPT-001 | S9 | MGR | `mrpt-001-check-daily-report-submission-7-day-grid.md` | 02 §10 |
| MRPT-002 | S9 | MGR | `mrpt-002-read-a-daily-report-and-comment.md` | 02 §10 |

### `manager-manual/meeting-requests/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| MMEET-001 | S8 | MGR | `mmeet-001-review-meeting-requests-team-and-open-pool.md` | 02 §12, 03 §4.1 |

### `manager-manual/travel/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| APPR-001 | S7 | MGR | `appr-001-work-the-travel-approval-queue.md` | 02 §13, 03 §3 |
| MTRIP-001 | S7 | MGR | `mtrip-001-approve-or-reject-a-trip.md` | 02 §14, 03 §3 |
| MTRIP-002 | S7 | MGR | `mtrip-002-read-a-completed-trip-s-travel-report.md` | 02 §14 |

### `manager-manual/performance/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| PERF-001 | S10 | MGR | `perf-001-performance-by-bdm-type-for-a-period.md` | 02 §16 |
| PERF-002 | S10 | MGR | `perf-002-drill-into-one-bdm-type.md` | 02 §16 |
| PERF-003 | S10 | MGR | `perf-003-drill-into-one-bdm-organisations-and-trips.md` | 02 §16 |

### `manager-manual/targets/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| TGT-001 | S10 | MGR | `tgt-001-team-targets-for-a-month-copy-last-month.md` | 02 §17 |
| TGT-002 | S10 | MGR | `tgt-002-set-one-bdm-s-monthly-targets.md` | 02 §17 |

### `admin-manual/`
| ID | S | Roles | File | Appx |
|---|---|---|---|---|
| ADM-001 | S2 | OA, SA | `adm-001-create-an-agent-or-school-bdm.md` | 03 §2.1–2.2 |
| ADM-002 | S2 | OA, SA | `adm-002-find-and-edit-a-bdm.md` | 03 §2.3–2.4 |
| ADM-003 | S11 | OA, SA | `adm-003-deactivate-a-bdm-with-handover.md` | 03 §2.5 |
| ADM-004 | S11 | OA, SA | `adm-004-hand-over-an-inactive-bdm-s-work-reactivate.md` | 03 §2.5 |
| ADM-005 | S2 | OA, SA | `adm-005-re-send-a-bdm-s-set-password-link.md` | 03 §1.4 |
| ADM-006 | S2 | SA | `adm-006-create-a-bdm-manager.md` | 03 §2.6 |
| ADM-007 | S11 | SA | `adm-007-deactivate-a-bdm-manager-and-move-the-team.md` | 03 §2.6 |
| ADM-008 | S5 | OA | `adm-008-link-an-agency-from-an-agent-onboarding-request.md` | 03 §4.2 |
| ADM-009 | S5 | OA | `adm-009-create-or-link-a-school-from-a-school-onboarding.md` | 03 §4.3 |
| ADM-010 | S11 | SA | `adm-010-fallback-travel-approvals-when-the-manager-is-in.md` | 03 §3 |
| ADM-011 | S5 | OA | `adm-011-bdm-leads-in-the-admin-lead-list.md` | 03 §4.4 |

## Self-review (S1)
- 117 unique IDs; each has one record above, one row in the progress tracker and one session: S2 4 + S3 9 + S4 16 + S5 11 + S6 14 + S7 16 + S8 15 + S9 7 + S10 21 + S11 4 = 117.
- D4 → S2 personas and S12 `demo-accounts.md`; D5 → S9 / S10 timing; D6 → S5 partner links.
