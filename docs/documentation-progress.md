# Agent CRM Documentation — Progress Tracker

| | |
|---|---|
| Code baseline | `main` @ `e376c25c`; 2026-10-05 docs branch merged `main` @ `6a9be770` (+42 commits, bdm-006 etc.) — only Agent-scope-adjacent change is BDM "Appointments" sidebar links in `navigation.ts`; Agent CRM analysis unchanged. Browser work may use a stack from `6a9be770`. |
| Stack used for browser work | `agentdocs` compose project from worktree `.claude/worktrees/agent-docs` @ `717d6aa8` (= main `6a9be770` + docs); web http://localhost:3010, api :8010; `EMAIL_ENABLED=false`; Razorpay test keys present |
| Last session | S2 — 2026-10-05 |
| Next session | S3 — Team & staff (DOC-TEAM-001..005, DOC-ADM-008) + close AUTH-003/004 partials |

Column values: **Code Reviewed** YES / PARTIAL / NO (YES at S1 = reviewed from source at HEAD with file:line evidence in
`documentation-analysis.md`); **Browser Verified** YES / PARTIAL / NO; **Screenshot** YES / NO / N/A;
**Documented** YES / DRAFT / NO; **Reviewed** PASSED / FAILED / NO. A feature is **COMPLETE** only when Code Reviewed =
YES, Browser Verified = YES, Screenshot = YES (or N/A), Documented = YES and Reviewed = PASSED.

| ID | Module | Feature | Code Reviewed | Browser Verified | Screenshot | Documented | Reviewed |
|---|---|---|---|---|---|---|---|
| DOC-AUTH-001 | Account access | Register an agency | YES | YES | YES | YES | NO |
| DOC-AUTH-002 | Account access | Sign in and sign out | YES | YES | YES | YES | NO |
| DOC-AUTH-003 | Account access | "Access unavailable" states | YES | PARTIAL (deactivated member → S3) | YES | DRAFT | NO |
| DOC-AUTH-004 | Account access | Forgot / reset password; first-time set-password link | YES | PARTIAL (invitation link → S3) | YES | DRAFT | NO |
| DOC-AUTH-005 | Account access | Change password | YES | YES | YES | YES | NO |
| DOC-AUTH-006 | Account access | My profile | YES | PARTIAL (save success + notification settings not exercised) | YES | DRAFT | NO |
| DOC-DASH-001 | Dashboard | Agency dashboard — Master | YES | NO | NO | NO | NO |
| DOC-DASH-002 | Dashboard | Agency dashboard — Staff | YES | NO | NO | NO | NO |
| DOC-STU-001 | Students | Find students | YES | NO | NO | NO | NO |
| DOC-STU-002 | Students | Add a student | YES | NO | NO | NO | NO |
| DOC-STU-003 | Students | View and edit a student record | YES | NO | NO | NO | NO |
| DOC-STU-004 | Students | Archive / unarchive a student | YES | NO | NO | NO | NO |
| DOC-STU-005 | Students | Assign a student to staff | YES | NO | NO | NO | NO |
| DOC-STU-006 | Students | Record counseling | YES | NO | NO | NO | NO |
| DOC-STU-007 | Students | Build a university shortlist | YES | NO | NO | NO | NO |
| DOC-STU-008 | Students | Journey and history | YES | NO | NO | NO | NO |
| DOC-STU-009 | Students | Link an existing student account | YES | NO | NO | NO | NO |
| DOC-UNI-001 | Universities | Manage the agency university list | YES | NO | NO | NO | NO |
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
| DOC-TEAM-001 | Team | Invite or deactivate a Master | YES | NO | NO | NO | NO |
| DOC-TEAM-002 | Team | Create a staff login | YES | NO | NO | NO | NO |
| DOC-TEAM-003 | Team | Edit, reset, deactivate, reactivate staff | YES | NO | NO | NO | NO |
| DOC-TEAM-004 | Team | Set staff permissions | YES | NO | NO | NO | NO |
| DOC-TEAM-005 | Team | Staff activity | YES | NO | NO | NO | NO |
| DOC-PERF-001 | Staff performance | View staff performance | YES | NO | NO | NO | NO |
| DOC-ADM-001 | Agency administration | Approve / reject / suspend / reinstate agencies | YES | PARTIAL (Reinstate → S9) | YES | DRAFT | NO |
| DOC-ADM-002 | Agency administration | Agent network list | YES | NO | NO | NO | NO |
| DOC-ADM-003 | Agency administration | Agency detail and drill-down | YES | NO | NO | NO | NO |
| DOC-ADM-004 | Agency administration | Suspend / reinstate from detail | YES | NO | NO | NO | NO |
| DOC-ADM-005 | Agency administration | Deposit remittance and refund | YES | NO | NO | NO | NO |
| DOC-ADM-006 | Agency administration | Commission amounts and payouts | YES | NO | NO | NO | NO |
| DOC-ADM-007 | Agency administration | Super Admin access to agency screens | YES | NO | NO | NO | NO |
| DOC-ADM-008 | Agency administration | Resend a staff welcome link | PARTIAL | NO | NO | NO | NO |

**Totals:** 54 features · Code reviewed 53 YES, 1 PARTIAL · Browser verified 3 YES, 4 PARTIAL · Screenshots 24 / ~178 ·
Documented 3 YES, 4 DRAFT · Reviewed 0 · **COMPLETE 0**.

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
| U4 | AUTH-001 | S2 | Partly: duplicate email verified; empty/short fields are blocked by the browser before submit. |

## Discovered functionality not in the original plan
| Date | Session | What | Where | Action |
|---|---|---|---|---|
| 2026-10-05 | S2 | Portal tables (dashboard open applications, admin Agent Masters) have Search records, Filter by column, sortable headings and Rows per page (10/25/50) | generic data table | Document in each module where the table appears |
| 2026-10-05 | S2 | In non-production stacks the forgot-password page shows a "Development only: reset link" | `/overseas/forgot-password` | Masked in screenshots; not documented for users |
| 2026-10-05 | S2 | Agency codes derive from the agency name (Docs… → DOC, DOC2, DOC3…) | registration | Mentioned in AUTH-001 |
| 2026-10-05 | S2 | Login-page and sidebar logo render very small inside a white box | `/overseas/login`, sidebar | UI note for review report (LOW) |
| 2026-10-05 | S2 | Profile validation shows the raw server text "String should have at least 2 characters" | `/account/profile` | Documented as-is; note for review report |

## Session log
| Session | Date | Commit | Stack / URL | Outcome |
|---|---|---|---|---|
| S1 Master planning | 2026-10-05 | `e376c25c` | none (no browser) | Analysis, plan, tracker created |
| S2 part 1 (no stack) | 2026-10-05 | `e376c25c` | none — waiting for a `main` stack | Index, capture tooling, link checker; AUTH-006 code-reviewed |
| S2 | 2026-10-05 | `717d6aa8` | agentdocs, :3010 | 24 screenshots; AUTH-001..006 + ADM-001 written; test agencies Docs Pending/Rejected/Suspended/Second created |
