# Overseas BDM CRM Documentation — Progress Tracker

| | |
|---|---|
| Code baseline | `main` @ `6fee294d` (S1 discovery). Record any later `main` used for browser work here, with affected features re-checked. |
| Stack used for browser work | `bdmdocs` compose project from worktree `.claude/worktrees/bdm-docs` (branch `docs/bdm-crm-user-guide`). Web http://localhost:3040, api :8040, Mailpit 127.0.0.1:8028 via untracked `docker-compose.docs.yml`; untracked `.env` per plan S2.1. Owner approved Claude starting, seeding, resetting and snapshotting this stack only (2026-10-17). **Not started yet.** |
| Docs branch | `docs/bdm-crm-user-guide` (from `main` @ `6fee294d`) |
| Last session | S1 Master planning — 2026-10-17 |
| Next session | S2 — Environment, capture tooling, admin provisioning (creates the Docs personas) |
| Timing (D5) | S9 must run on a later day than S6; S10 ≥ 5 days after S5. Record capture dates in the session log. |

**Column values:** Code Reviewed YES / PARTIAL / NO · Browser Verified YES / PARTIAL / NO · Screenshot YES / NO / N/A ·
Documented YES / DRAFT / NO · Reviewed PASSED / FAILED / NO. **COMPLETE** = all five satisfied.

**Totals (after S1):** 117 features · 117 code-reviewed · 0 browser-verified · 0 documented · 0 COMPLETE.

| ID | Module | Feature | Session | Code Reviewed | Browser Verified | Screenshot | Documented | Reviewed |
|---|---|---|---|---|---|---|---|---|
| DOC-BDM-AUTH-001 | Account access | Choose your BDM portal and sign in as an Agent/School BDM | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-AUTH-002 | Account access | Sign in as a BDM Manager (lands on Dashboard) | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-AUTH-003 | Account access | Set your first password from the welcome email | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-AUTH-004 | Account access | Forgot / reset your password | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-AUTH-005 | Account access | Change your password and sign out | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-AUTH-006 | Account access | Your BDM profile and the account profile page | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-AUTH-007 | Account access | "Access unavailable" messages (no BDM profile, wrong role, wrong portal) | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-NAV-001 | Navigation | BDM portal tour: sidebar, role pill (Agent BDM / School BDM), unread badge | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-NAV-002 | Navigation | Manager portal tour: the 17-item sidebar | S3 | YES | NO | NO | NO | NO |
| DOC-BDM-DAY-001 | My Day | My Day: today's appointments, upcoming travel, follow-ups | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-DAY-002 | My Day | My Day: Agent overview tiles | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-DAY-003 | My Day | My Day: School overview tiles | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-DAY-004 | My Day | My Day: monthly targets card | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-DAY-005 | My Day | My Day: meeting requests card | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-NOTIF-001 | Notifications | Read and open notifications | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-NOTIF-002 | Notifications | Reminders (appointment, travel, follow-up, MoU follow-up/renewal) and email action links | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-NOTIF-003 | Notifications | Decision notices (trip approved / not approved, onboarding outcome, handover) | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-CAL-001 | Calendar | Calendar: week/day view and navigation | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-MEET-001 | Meeting requests | Meeting request inbox and filters (requests from telecallers) | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-MEET-002 | Meeting requests | View a meeting request | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-MEET-003 | Meeting requests | Accept a request and book the appointment | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-MEET-004 | Meeting requests | Decline a request with a reason | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-UNI-001 | Organisations | View a linked University Master record | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-ORG-001 | Organisations | Browse and filter your module's organisations | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-ORG-002 | Organisations | Add an organisation (duplicate warning) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-ORG-003 | Organisations | Open an organisation (read-only when not assigned to you) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-ORG-004 | Organisations | Edit organisation details | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-ORG-005 | Organisations | Archive an organisation (your manager restores it) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-CONT-001 | Organisations | Manage contacts (add, edit, primary, delete; 1–20) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PROF-001 | Organisations | Agent organisation details (type profile) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PROF-002 | Organisations | School organisation details (board, type, grades) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PROF-003 | Organisations | Change an organisation's type (clear-first rule) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PIPE-001 | Pipeline | Move an organisation through pipeline stages (moving back needs a reason) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PIPE-002 | Pipeline | Mark an organisation Lost and revive it | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PIPE-003 | Pipeline | Read the stage history | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-PIPE-004 | Pipeline | Pipeline board (Mine / All in module, stage tiles, Lost) | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-LEAD-001 | Organisations | Add and view student leads on an organisation | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-REF-001 | Reference | Reference lists: organisation types, contact roles, pipeline stages per module | S4 | YES | NO | NO | NO | NO |
| DOC-BDM-MOU-001 | MoUs | Start and edit an organisation's MoU (status, dates, signing) | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-MOU-002 | MoUs | Upload and download the MoU document | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-MOU-003 | MoUs | MoU history, expiry and renewal | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-MOU-004 | MoUs | MoU list by status | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-ONB-001 | Onboarding | Request Agent onboarding (at Agreement Signed) | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-ONB-002 | Onboarding | Request School onboarding (MoU Signed / Active) | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-ORGP-001 | Onboarding | Agent performance panel | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-ORGP-002 | Onboarding | School activity panel | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-001 | Appointments | View and filter your appointments | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-002 | Appointments | Book an appointment (overlap warning) | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-003 | Appointments | Link an appointment to a trip | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-004 | Appointments | Appointment detail, edit details and history | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-005 | Appointments | Confirm, reschedule or cancel an appointment | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-006 | Appointments | Complete with a meeting report, or mark no-show | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-007 | Appointments | Edit the meeting report the same day; book the next meeting | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-APPT-008 | Appointments | Act on an appointment reminder | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-FUP-001 | Follow-ups | Follow-ups: tabs, counts and filters (incl. Overdue) | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-FUP-002 | Follow-ups | Add a follow-up or task | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-FUP-003 | Follow-ups | Mark done, edit or cancel a task | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-FUP-004 | Follow-ups | Follow-ups created from meeting reports | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-ACT-001 | Activities | Your activities for a day, with counts | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-ACT-002 | Activities | Log an activity (including backdating) | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-ACT-003 | Activities | Edit or delete today's activity | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-ACT-004 | Activities | Organisation activity timeline | S6 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-001 | Travel | View and filter your trips | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-002 | Travel | Plan a new trip (draft) | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-003 | Travel | Open a trip (details, appointments, productivity) | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-004 | Travel | Edit a draft or rejected trip | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-005 | Travel | Submit a trip for approval, or withdraw it | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-006 | Travel | Handle a rejected trip (reason, fix, resubmit) | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-007 | Travel | Start, complete or cancel a trip | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-008 | Travel | Record trip expenses | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-009 | Travel | Trip remarks | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-010 | Travel | Trip itinerary: appointments linked to a trip | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-011 | Travel | Travel report of a completed trip | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-TRAV-012 | Travel | Travel notifications and the day-before reminder | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-RPT-001 | Daily report | View a day's live report | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-RPT-002 | Daily report | Submit the daily report with a note (locks the day) | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-RPT-003 | Daily report | Read a submitted report and your manager's comment | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-RPT-004 | Daily report | What each count means (Agent vs School tiles) | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-MDASH-001 | Manager: dashboard | Read the BDM overview tiles | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MDASH-002 | Manager: dashboard | Act on dashboard alerts (AL-1 … AL-7) | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MNOTIF-001 | Manager: dashboard | Manager notifications | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-MTEAM-001 | Manager: team | View the BDMs who report to you | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MTEAM-002 | Manager: team | Read the Master view (type → BDM → linked organisations) | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MORG-001 | Manager: organisations | Find the team's organisations | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MORG-002 | Manager: organisations | Read an organisation's profile and panels | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MORG-003 | Manager: organisations | Reassign an organisation to another BDM on your team | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MORG-004 | Manager: organisations | Restore an archived organisation | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MPIPE-001 | Manager: pipeline | Team pipeline by type and stage | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MAPPT-001 | Manager: appointments | Filter the team's appointments | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MAPPT-002 | Manager: appointments | Read an appointment and its meeting report | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MCAL-001 | Manager: appointments | View a BDM's calendar | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MFUP-001 | Manager: activity | Review the team's follow-ups and tasks | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MACT-001 | Manager: activity | Review the team's activities for a day | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MRPT-001 | Manager: daily reports | Check daily-report submission (7-day grid) | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-MRPT-002 | Manager: daily reports | Read a daily report and comment | S9 | YES | NO | NO | NO | NO |
| DOC-BDM-MMOU-001 | Manager: organisations | Review the team's MoUs by status | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-MMEET-001 | Manager: meeting requests | Review meeting requests (team and open pool) | S8 | YES | NO | NO | NO | NO |
| DOC-BDM-APPR-001 | Manager: travel | Work the travel approval queue | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-MTRIP-001 | Manager: travel | Approve or reject a trip | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-MTRIP-002 | Manager: travel | Read a completed trip's travel report | S7 | YES | NO | NO | NO | NO |
| DOC-BDM-PERF-001 | Manager: performance | Performance by BDM type for a period | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-PERF-002 | Manager: performance | Drill into one BDM type | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-PERF-003 | Manager: performance | Drill into one BDM (organisations and trips) | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-TGT-001 | Manager: targets | Team targets for a month; copy last month | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-TGT-002 | Manager: targets | Set one BDM's monthly targets | S10 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-001 | Admin | Create an Agent or School BDM | S2 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-002 | Admin | Find and edit a BDM | S2 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-003 | Admin | Deactivate a BDM with handover | S11 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-004 | Admin | Hand over an inactive BDM's work; reactivate | S11 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-005 | Admin | Re-send a BDM's set-password link | S2 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-006 | Admin | Create a BDM Manager | S2 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-007 | Admin | Deactivate a BDM Manager and move the team | S11 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-008 | Admin | Link an agency from an Agent onboarding request | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-009 | Admin | Create or link a school from a School onboarding request | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-010 | Admin | Fallback travel approvals when the manager is inactive | S11 | YES | NO | NO | NO | NO |
| DOC-BDM-ADM-011 | Admin | BDM leads in the admin lead list | S5 | YES | NO | NO | NO | NO |
| DOC-BDM-REF-002 | Reference | Management BDM figures (pointer only) | S10 | YES | NO | NO | NO | NO |

## Unresolved items
| # | Item | Owner / session |
|---|---|---|
| U1 | Product findings P1–P20 (analysis §9) — documented as built; owner decides fixes. | Owner |
| U2 | Forgot-password delivery (03 Q1) — AUTH-004 likely PARTIAL. | S3 |
| U3 | Agent commission display is undecided in code ("awaiting a decision"). | Owner |
| U4 | Reassign picker and inactive BDMs (02 Q10); Super Admin reactivating a manager (03 Q2). | S10 / S11 |
| U5 | Shared `signIn(portal)` change must match the telecaller docs branch (04 Q7). | S2 |

## Discovered functionality (outside the IDs)
_None yet._

## Session log
| Session | Date | Commit | Summary |
|---|---|---|---|
| S1 | 2026-10-17 | (this commit) | Four discovery appendices; owner answers D1–D6; analysis (117 features), plan (S2–S13), tracker, screenshot-index skeleton. |
