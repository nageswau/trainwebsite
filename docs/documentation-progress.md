# Agent CRM Documentation — Progress Tracker

| | |
|---|---|
| Code baseline | `main` @ `e376c25c`; 2026-10-05 docs branch merged `main` @ `6a9be770` (+42 commits, bdm-006 etc.) — only Agent-scope-adjacent change is BDM "Appointments" sidebar links in `navigation.ts`; Agent CRM analysis unchanged. Browser work may use a stack from `6a9be770`. |
| Stack used for browser work | `agentdocs` compose project from worktree `.claude/worktrees/agent-docs` @ `717d6aa8` (= main `6a9be770` + docs); web http://localhost:3010, api :8010; SMTP → local Mailpit (`docker-compose.docs.yml`, UI http://localhost:8025; `EMAIL_ENABLED` is not read by the app); Razorpay test keys present |
| Last session | S4 — 2026-10-05 |
| Next session | S5 — Applications core + tasks (DOC-APP-001..005, DOC-TASK-001..002) |

Column values: **Code Reviewed** YES / PARTIAL / NO (YES at S1 = reviewed from source at HEAD with file:line evidence in
`documentation-analysis.md`); **Browser Verified** YES / PARTIAL / NO; **Screenshot** YES / NO / N/A;
**Documented** YES / DRAFT / NO; **Reviewed** PASSED / FAILED / NO. A feature is **COMPLETE** only when Code Reviewed =
YES, Browser Verified = YES, Screenshot = YES (or N/A), Documented = YES and Reviewed = PASSED.

| ID | Module | Feature | Code Reviewed | Browser Verified | Screenshot | Documented | Reviewed |
|---|---|---|---|---|---|---|---|
| DOC-AUTH-001 | Account access | Register an agency | YES | YES | YES | YES | NO |
| DOC-AUTH-002 | Account access | Sign in and sign out | YES | YES | YES | YES | NO |
| DOC-AUTH-003 | Account access | "Access unavailable" states | YES | YES (deactivated member: refused at sign-in) | YES | YES | NO |
| DOC-AUTH-004 | Account access | Forgot / reset password; first-time set-password link | YES | YES | YES | YES | NO |
| DOC-AUTH-005 | Account access | Change password | YES | YES | YES | YES | NO |
| DOC-AUTH-006 | Account access | My profile | YES | PARTIAL (save success + notification settings not exercised) | YES | DRAFT | NO |
| DOC-DASH-001 | Dashboard | Agency dashboard — Master | YES | NO | NO | NO | NO |
| DOC-DASH-002 | Dashboard | Agency dashboard — Staff | YES | NO | NO | NO | NO |
| DOC-STU-001 | Students | Find students | YES | YES | YES | YES | NO |
| DOC-STU-002 | Students | Add a student | YES | YES | YES | YES | NO |
| DOC-STU-003 | Students | View and edit a student record | YES | YES | YES | YES | NO |
| DOC-STU-004 | Students | Archive / unarchive a student | YES | PARTIAL (unarchive not exercised) | YES | DRAFT | NO |
| DOC-STU-005 | Students | Assign a student to staff | YES | YES | YES | YES | NO |
| DOC-STU-006 | Students | Record counseling | YES | YES | YES | YES | NO |
| DOC-STU-007 | Students | Build a university shortlist | YES | YES | YES | YES | NO |
| DOC-STU-008 | Students | Journey and history | YES | PARTIAL (journey with applications → S5/S6) | YES | DRAFT | NO |
| DOC-STU-009 | Students | Link an existing student account | YES | YES | YES | YES | NO |
| DOC-UNI-001 | Universities | Manage the agency university list | YES | PARTIAL (edit not exercised) | YES | DRAFT | NO |
| DOC-APP-001 | Applications | View and filter applications | YES | NO | NO | NO | NO |
| DOC-APP-002 | Applications | Create an application | YES | NO | NO | NO | NO |
| DOC-APP-003 | Applications | Edit an application | YES | NO | NO | NO | NO |
| DOC-APP-004 | Applications | Application detail page | YES | NO | NO | NO | NO |
| DOC-APP-005 | Applications | Change status / withdraw | YES | NO | NO | NO | NO |
| DOC-APP-006 | Applications | Record or edit an offer | YES | NO | NO | NO | NO |
| DOC-APP-007 | Applications | Deposit terms and payment (Razorpay) | YES | NO | NO | NO | NO |
| DOC-APP-008 | Applications | Run the visa case | YES | NO | NO | NO | NO |
| DOC-APP-009 | Applications | Confirm enrollment | YES | NO | NO | NO | NO |
| DOC-DOC-001 | Documents | Browse and download documents | YES | NO | NO | NO | NO |
| DOC-DOC-002 | Documents | Upload a document | YES | NO | NO | NO | NO |
| DOC-DOC-003 | Documents | Replace a document file | YES | NO | NO | NO | NO |
| DOC-DOC-004 | Documents | Review a document | YES | NO | NO | NO | NO |
| DOC-DOC-005 | Documents | Document history | YES | NO | NO | NO | NO |
| DOC-DOC-006 | Documents | Request an additional document | YES | NO | NO | NO | NO |
| DOC-TASK-001 | Tasks | View tasks and follow-ups | YES | NO | NO | NO | NO |
| DOC-TASK-002 | Tasks | Add, edit, complete or cancel a task | YES | NO | NO | NO | NO |
| DOC-NOTIF-001 | Notifications | Read notifications | YES | NO | NO | NO | NO |
| DOC-COMM-001 | Commissions | View and claim commissions | YES | NO | NO | NO | NO |
| DOC-RPT-001 | Reports | Run agency reports | YES | NO | NO | NO | NO |
| DOC-RPT-002 | Reports | Export a report to CSV | YES | NO | NO | NO | NO |
| DOC-RPT-003 | Reports | Commission report | YES | NO | NO | NO | NO |
| DOC-TEAM-001 | Team | Invite or deactivate a Master | YES | PARTIAL (3-Master limit not reproduced) | YES | DRAFT | NO |
| DOC-TEAM-002 | Team | Create a staff login | YES | YES | YES | YES | NO |
| DOC-TEAM-003 | Team | Edit, reset, deactivate, reactivate staff | YES | PARTIAL (sign-in after reactivation not exercised) | YES | DRAFT | NO |
| DOC-TEAM-004 | Team | Set staff permissions | YES | YES | YES | YES | NO |
| DOC-TEAM-005 | Team | Staff activity | YES | YES | YES | YES | NO |
| DOC-PERF-001 | Staff performance | View staff performance | YES | NO | NO | NO | NO |
| DOC-ADM-001 | Agency administration | Approve / reject / suspend / reinstate agencies | YES | PARTIAL (Reinstate → S9) | YES | DRAFT | NO |
| DOC-ADM-002 | Agency administration | Agent network list | YES | NO | NO | NO | NO |
| DOC-ADM-003 | Agency administration | Agency detail and drill-down | YES | NO | NO | NO | NO |
| DOC-ADM-004 | Agency administration | Suspend / reinstate from detail | YES | NO | NO | NO | NO |
| DOC-ADM-005 | Agency administration | Deposit remittance and refund | YES | NO | NO | NO | NO |
| DOC-ADM-006 | Agency administration | Commission amounts and payouts | YES | NO | NO | NO | NO |
| DOC-ADM-007 | Agency administration | Super Admin access to agency screens | YES | NO | NO | NO | NO |
| DOC-ADM-008 | Agency administration | Resend a staff welcome link | YES | YES | YES | YES | NO |

**Totals:** 54 features · Code reviewed 54 YES · Browser verified 17 YES, 7 PARTIAL · Screenshots 78 / ~178 ·
Documented 17 YES, 7 DRAFT · Reviewed 0 · **COMPLETE 0**.

## Deliverables outside the feature rows
| Deliverable | Session | Status |
|---|---|---|
| `docs/screenshot-index.md` | S2 | YES (empty table) |
| Capture tooling (`apps/web/playwright.docs.config.ts`, `apps/web/tests/doc-capture/shoot.ts`) | S2 | YES (type-checks; 0 specs yet) |
| `docs/tooling/check-doc-links.mjs` | S2 | YES (runs, all links OK) |
| `docs/admin-manual/README.md`, `docs/user-manual/README.md` | S10 | NO |
| Role guides: Agency Master, Agency Staff, Overseas Admin (agencies), Super Admin (agencies) | S10 | NO |
| `docs/faq.md`, `docs/troubleshooting.md` | S10 | NO |
| `docs/documentation-review-report.md` | S11 | NO |

## Unresolved verification items
Open items U1–U19 are listed in `docs/documentation-analysis.md` §12.1. Close each one here with the session and result.

| Item | Feature | Session | Result |
|---|---|---|---|
| U2 | AUTH-005 | S2 | Closed: a pending agent can open Change password. |
| 12.2 #1 | AUTH-003 | S2 | Confirmed in browser: rejected agency sees "Agent registration is pending approval". |
| U7 | STU-007 | S4 | Closed: the same university can be shortlisted twice (accepted). |
| U6 | STU-002 | S4 | Open: network-error wording not reproduced. |
| U3 | AUTH-003 | S3 | Closed: deactivated staff are refused at sign-in with "Invalid credentials". |
| U13 | TEAM-001 | S3 | Closed: Team page shows Masters twice (Team table + "Team — {agency}" card) — documented. |
| U17 | ADM-008 | S3 | Closed: Users > Re-send link works for awaiting-setup staff. |
| U4 | AUTH-001 | S2 | Partly: duplicate email verified; empty/short fields are blocked by the browser before submit. |

## Discovered functionality not in the original plan
| Date | Session | What | Where | Action |
|---|---|---|---|---|
| 2026-10-05 | S2 | Portal tables (dashboard open applications, admin Agent Masters) have Search records, Filter by column, sortable headings and Rows per page (10/25/50) | generic data table | Document in each module where the table appears |
| 2026-10-05 | S2 | In non-production stacks the forgot-password page shows a "Development only: reset link" | `/overseas/forgot-password` | Masked in screenshots; not documented for users |
| 2026-10-05 | S2 | Agency codes derive from the agency name (Docs… → DOC, DOC2, DOC3…) | registration | Mentioned in AUTH-001 |
| 2026-10-05 | S2 | Login-page and sidebar logo render very small inside a white box | `/overseas/login`, sidebar | UI note for review report (LOW) |
| 2026-10-05 | S2 | Profile validation shows the raw server text "String should have at least 2 characters" | `/account/profile` | Documented as-is; note for review report |
| 2026-10-05 | S3 | `EMAIL_ENABLED` in .env is not read by the API; welcome/invite emails go via SMTP, password-reset emails via `EMAIL_WEBHOOK_URL` | config | Docs stack routes SMTP to local Mailpit; note for review report |
| 2026-10-05 | S3 | An invite-pending Master already shows a Deactivate button | Team card | Documented |
| 2026-10-05 | S3 | Staff opening a Master-only page get an Access unavailable card with "Go to your dashboard" | `/overseas/agent/team` | Documented |
| 2026-10-05 | S4 | Link student picker suggests only students who registered themselves and are not yet linked; shows a masked email | Students > Link student | Documented (STU-009) |
| 2026-10-05 | S4 | Shortlist prefills tuition fee/intake from the catalogue course | Shortlist form | Documented |

## Session log
| Session | Date | Commit | Stack / URL | Outcome |
|---|---|---|---|---|
| S1 Master planning | 2026-10-05 | `e376c25c` | none (no browser) | Analysis, plan, tracker created |
| S2 part 1 (no stack) | 2026-10-05 | `e376c25c` | none — waiting for a `main` stack | Index, capture tooling, link checker; AUTH-006 code-reviewed |
| S2 | 2026-10-05 | `717d6aa8` | agentdocs, :3010 | 24 screenshots; AUTH-001..006 + ADM-001 written; test agencies Docs Pending/Rejected/Suspended/Second created |
| S3 | 2026-10-05 | `717d6aa8` | agentdocs, :3010 + Mailpit :8025 | 21 screenshots; TEAM-001..005 + ADM-008 written, AUTH-003/004 completed; staff Asha/Bala/Chitra/Dev/Esha in EduSphere Partner Agency |
| S4 | 2026-10-05 | `717d6aa8` | agentdocs, :3010 | 33 screenshots; STU-001..009 + UNI-001 written; Neha Sharma (assigned to Asha) + 20 paging students, Kabir archived, Farah Ali linked, agency universities Northbridge/Harbour Point |
