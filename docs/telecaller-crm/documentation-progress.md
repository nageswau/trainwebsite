# Overseas Telecaller CRM Documentation — Progress Tracker

| | |
|---|---|
| Code baseline | `main` @ `6fee294d` (S1 discovery). Record any later `main` used for browser work here, with the affected features re-checked. |
| Stack used for browser work | `teldocs` compose project from worktree `.claude/worktrees/tel-docs` (branch `docs/telecaller-crm-user-guide`). Web http://localhost:3030, api :8030, Mailpit 127.0.0.1:8027 via untracked `docker-compose.docs.yml`. Untracked `.env` per plan S2.1. Owner approved Claude starting, seeding, resetting and snapshotting this stack only (2026-10-17). **Not started yet.** |
| Docs branch | `docs/telecaller-crm-user-guide` (from `main` @ `6fee294d`) |
| Last session | S1 Master planning — 2026-10-17 |
| Next session | S2 — Environment, capture tooling, admin provisioning (creates the Docs personas) |

**Column values:** Code Reviewed YES / PARTIAL / NO (YES at S1 = reviewed from source at `6fee294d`, evidence in `discovery/`) · Browser Verified YES / PARTIAL / NO · Screenshot YES / NO / N/A · Documented YES / DRAFT / NO · Reviewed PASSED / FAILED / NO.

A feature is **COMPLETE** only when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES (or N/A), Documented = YES and Reviewed = PASSED.

**Totals (after S1):** 82 features · 82 code-reviewed · 0 browser-verified · 0 documented · 0 COMPLETE.

| ID | Module | Feature | Session | Code Reviewed | Browser Verified | Screenshot | Documented | Reviewed |
|---|---|---|---|---|---|---|---|---|
| DOC-TEL-AUTH-001 | Account access | Choose your portal (Telecaller sign-in chooser) | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-002 | Account access | Sign in as an Overseas telecaller (where you land) | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-003 | Account access | Sign in as a Telecaller Manager (lands on Team) | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-004 | Account access | Set your first password from the welcome email | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-005 | Account access | Forgot / reset your password | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-006 | Account access | Change your password | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-007 | Account access | Your profile: view details, update your mobile (name locked) | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-AUTH-008 | Account access | Sign out, ended sessions and "access unavailable" messages | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-NAV-001 | Navigation | Telecaller portal tour: sidebar, role label, unread badge | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-NAV-002 | Navigation | Manager portal tour: the 16-item sidebar | S3 | YES | NO | NO | NO | NO |
| DOC-TEL-NAV-003 | Navigation | Notifications and the nine alert types | S8 | YES | NO | NO | NO | NO |
| DOC-TEL-DASH-001 | Dashboard | Today's tiles (10 tiles with hints) | S8 | YES | NO | NO | NO | NO |
| DOC-TEL-DASH-002 | Dashboard | Today's follow-ups and appointments cards | S8 | YES | NO | NO | NO | NO |
| DOC-TEL-DASH-003 | Dashboard | My targets (6 KPIs) | S8 | YES | NO | NO | NO | NO |
| DOC-TEL-DASH-004 | Dashboard | Daily activity for a chosen day | S8 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-001 | Leads | My Leads: search, filters, paging | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-002 | Leads | Create a lead | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-003 | Leads | Duplicate warning and "Add enquiry to this lead" | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-004 | Leads | Open a lead: header, Call button, panels, read-only state | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-005 | Leads | Set priority | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-006 | Leads | Edit lead details (contact, product) | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-LEAD-007 | Leads | Change stage / close a lead (reasons, no reopen) | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-QUAL-001 | Leads | Qualification form (Basic + Overseas requirement) | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-TIME-001 | Leads | Read the lead activity timeline | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-CALL-001 | Calls | Log a call (13 outcomes, stage effects, next follow-up) | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-CALL-002 | Calls | Edit or delete today's call | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-FUP-001 | Follow-ups | Add, reschedule, complete or cancel a follow-up on a lead | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-FUP-002 | Follow-ups | Today's and overdue follow-ups page | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-APPT-001 | Appointments | Book a counselling appointment | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-APPT-002 | Appointments | Reschedule or cancel an appointment | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-MSG-001 | Messages | Send and record a WhatsApp message; delete today's record | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-MSG-002 | Messages | Send an email and track delivery | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-CONT-001 | Content library | Use the call script, templates and brochure links on a lead | S6 | YES | NO | NO | NO | NO |
| DOC-TEL-MEET-001 | Meeting requests | Request a BDM meeting | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-MEET-002 | Meeting requests | Track my BDM meeting requests | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-HAND-001 | Handover | Hand a lead over to a counselor | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-HAND-002 | Handover | Follow a handed-over lead: read-only view, returns, student link, milestones, conversion | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-TEAM-001 | Manager: team | View the telecallers who report to you | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-TEAM-002 | Manager: team | A telecaller's daily activity and targets | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-001 | Manager: leads | Browse, search and filter team leads | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-002 | Manager: leads | Enter a new lead (distributed or queued; duplicate panel) | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-003 | Manager: leads | Open a team lead: stage, priority, details, qualification | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-004 | Manager: leads | Reopen a closed lead | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-005 | Manager: leads | Assign or change the counselor on a lead | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-006 | Manager: leads | Assign unassigned leads in bulk | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-MLEAD-007 | Manager: leads | Reassign leads between telecallers | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-DIST-001 | Distribution | How routing works (product → city → round robin → queue) | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-DIST-002 | Distribution | Create a product or city rule | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-DIST-003 | Distribution | Change or delete a rule | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-IMP-001 | Import | Download and fill in the CSV template | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-IMP-002 | Import | Import leads for a campaign; read the per-row report | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-IMP-003 | Import | Review past imports | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-CAT-001 | Catalogue | Manage products | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-CAT-002 | Catalogue | Manage campaigns | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-CONT-002 | Content library | Write call scripts | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-CONT-003 | Content library | Create and preview WhatsApp/email templates | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-CONT-004 | Content library | Upload brochures and copy 7-day links | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-TGT-001 | Targets | Set team default targets (daily/monthly) | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-TGT-002 | Targets | Override targets for one telecaller | S4 | YES | NO | NO | NO | NO |
| DOC-TEL-MFUP-001 | Manager: follow-ups | Monitor team follow-ups | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-ALRT-001 | Alerts | Set team alert thresholds (and what triggers each alert) | S4/S8 | YES | NO | NO | NO | NO |
| DOC-TEL-PERF-001 | Performance | Compare telecallers over a date range; export CSV | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-RPT-001 | Reports | Source / Course / Campaign funnel reports | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-RPT-002 | Reports | Telecaller activity report | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-RPT-003 | Reports | Counselor handover report | S9 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-001 | Admin | Create a Telecaller Manager | S2 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-002 | Admin | Create an Overseas telecaller | S2 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-003 | Admin | Find and edit a telecaller (Employee ID, manager, mobile) | S2 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-004 | Admin | Re-send a set-password link | S2 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-005 | Admin | Deactivate a telecaller and hand over open leads | S10 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-006 | Admin | Reassign the open work of an inactive telecaller | S10 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-007 | Admin | Move a telecaller to the other team | S10 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-008 | Admin | Reactivate a telecaller | S10 | YES | NO | NO | NO | NO |
| DOC-TEL-ADM-009 | Admin | Deactivate a Telecaller Manager (with replacement) | S10 | YES | NO | NO | NO | NO |
| DOC-TEL-CNS-001 | Counselor | See leads handed to you | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-CNS-002 | Counselor | Open a handed-over lead (details, milestones, activity) | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-CNS-003 | Counselor | Link / unlink the student account | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-CNS-004 | Counselor | Return a lead to the telecaller | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-CNS-005 | Counselor | Conversion when the student enrols (and admin unlink) | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-CNS-006 | Counselor | BDM side of meeting requests (touchpoint note only) | S7 | YES | NO | NO | NO | NO |
| DOC-TEL-INTAKE-001 | Intake | A website enquiry becomes (or joins) a lead | S5 | YES | NO | NO | NO | NO |
| DOC-TEL-INTAKE-002 | Intake | Lead sources reference (13 sources) | S5 | YES | NO | NO | NO | NO |

## Unresolved items
| # | Item | Owner / session |
|---|---|---|
| U1 | Product findings P1–P17 (analysis §12) — documented as built; owner to decide fixes. | Owner |
| U2 | Forgot-password delivery on the docs stack (P8) — AUTH-005 likely PARTIAL. | S3 |
| U3 | Manager lead page **Call** button behaviour; "Management tasks" sidebar item. | S3 / S9 |
| U4 | Exact text of "New lead assigned", "Lead not contacted", "Lead returned for follow-up" alerts. | S8 |

## Discovered functionality (outside the 82 IDs)
_None yet._

## Session log
| Session | Date | Commit | Summary |
|---|---|---|---|
| S1 | 2026-10-17 | (this commit) | Four discovery appendices; owner answers D1–D6; analysis (82 features in 26 modules), plan (S2–S12), tracker, screenshot-index skeleton. |
