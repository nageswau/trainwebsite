# Overseas Counselor CRM Documentation — Progress Tracker

| | |
|---|---|
| Code baseline | `main` @ `045d8c40` (S1 discovery). Record any later `main` used for browser work here, with the affected features re-checked. |
| Stack used for browser work | `cnsdocs` compose project from worktree `.claude/worktrees/cns-docs` (branch `docs/counselor-crm-user-guide`). Web http://localhost:3050, api :8050, Mailpit 127.0.0.1:8029 via untracked `docker-compose.docs.yml`. Untracked `.env` per plan S2.1. Owner approved Claude starting, seeding, resetting and snapshotting this stack only (2026-10-29). Started 2026-10-30 (S2) at `045d8c40`; seeded; snapshots `after-seed`, `after-s2` in the session scratchpad. |
| Docs branch | `docs/counselor-crm-user-guide` (from `main` @ `045d8c40`) |
| Day 1 (D3 calendar) | **2026-10-30** (S5). S9 must run on or after **2026-11-02**. |
| Last session | S11 Guides and supporting pages (early) — 2026-10-30 |
| Next session | S9 — Time-based states, dashboards, admin oversight (**not before 2026-11-02**); S10 lifecycle can run first |

**Column values:** Code Reviewed YES / PARTIAL / NO (YES at S1 = reviewed from source at `045d8c40`, evidence in `discovery/`) · Browser Verified YES / PARTIAL / NO · Screenshot YES / NO / N/A · Documented YES / DRAFT / NO · Reviewed PASSED / FAILED / NO.

A feature is **COMPLETE** only when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES (or N/A), Documented = YES and Reviewed = PASSED.

**Totals (after S8):** 85 features · 85 code-reviewed · 66 browser-verified (+7 partial) · 66 documented (+7 draft) · 0 COMPLETE.

| ID | Module | Feature | Session | Code Reviewed | Browser Verified | Screenshot | Documented | Reviewed |
|---|---|---|---|---|---|---|---|---|
| DOC-CNS-AUTH-001 | Account access | Sign in to the Overseas portal | S3 | YES | YES | YES | YES | NO |
| DOC-CNS-AUTH-002 | Account access | Set your first password from the welcome email | S3 | YES | YES | YES | YES | NO |
| DOC-CNS-AUTH-003 | Account access | Forgot / reset your password | S3 | YES | YES | YES | YES | NO |
| DOC-CNS-AUTH-004 | Account access | Change your password | S3 | YES | YES | YES | YES | NO |
| DOC-CNS-AUTH-005 | Account access | My profile | S3 | YES | YES | YES | YES | NO |
| DOC-CNS-AUTH-006 | Account access | Sign out, ended sessions, deactivated account | S3 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-NAV-001 | Navigation | Portal tour: 15-item sidebar, top bar, mobile menu | S3 | YES | YES | YES | YES | NO |
| DOC-CNS-DASH-001 | Dashboard | Counselor dashboard (action tiles + application table) | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-SRCH-001 | Dashboard | Quick search | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-LEAD-001 | Leads | My leads list | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-002 | Leads | Record a new walk-in lead | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-003 | Leads | Lead detail page layout | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-004 | Leads | Lead details: view and edit contact, consent, referral | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-005 | Leads | Next action | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-006 | Leads | Change stage, record loss, close a lead | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-007 | Leads | Lead qualification | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-008 | Leads | Return a lead to the telecaller | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-LEAD-009 | Leads | Student and milestones panel (read only) | S4 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-CONV-001 | Conversion | Convert a lead to a new student | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-CONV-002 | Conversion | Link / unlink an existing student account | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-ACT-001 | Activity | Log a call | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-ACT-002 | Activity | Record a WhatsApp message | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-ACT-003 | Activity | Email a lead | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-ACT-004 | Activity | Log a meeting | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-ACT-005 | Activity | Lead notes | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-ACT-006 | Activity | Lead activity timeline | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-CHAT-001 | Chat | Counselor Chat with students | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-FUP-001 | Follow-ups | Follow-ups on a lead | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-FUP-002 | Follow-ups | Overdue follow-ups on the Tasks page | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-FUP-003 | Follow-ups | Automatic reminders (what triggers them, where they show) | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-TASK-001 | Tasks | My tasks | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-CAL-001 | Calendar | Appointments page and lead appointments | S5 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-CAL-002 | Calendar | Calendar and iCal feed | S5 | YES | YES | YES | YES | NO |
| DOC-CNS-REP-001 | Reports | My performance | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-UNI-001 | Universities | Partner universities list | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-UNI-002 | Universities | University 360 view (incl. course commission display) | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-001 | Students | Students page: Application Tracking table and filters | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-002 | Students | My students card (Source filter, search) | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-003 | Students | Add a walk-in student / edit pending / resend link | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-004 | Students | Student 360: header, tabs, Overview | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-005 | Students | Structured profile (Academic / Preferences / English) | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-006 | Students | Internal student notes | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-007 | Students | Activities and History tabs | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-STU-008 | Students | Archive a student / Archived Students | S10 | YES | NO | NO | NO | NO |
| DOC-CNS-STU-009 | Students | Overseas consent (read only for staff) | S10 | YES | NO | NO | NO | NO |
| DOC-CNS-STU-010 | Students | When a student or application is reassigned to you | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-001 | Applications | Add an application from the 360 | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-002 | Applications | Intake Month YYYY picker | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-003 | Applications | Applications tab list (EduSphere ID) | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-004 | Applications | Advance an application's stage | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-005 | Applications | Sub-status and the Ready-for-Submission gate | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-006 | Applications | Journey stage | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-007 | Applications | Record an outcome / resume | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-008 | Applications | Application details (fields and dates) | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-009 | Applications | Application status history | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-APP-010 | Applications | Agency vs direct applications | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-OFR-001 | Offers | Record, close or decide an offer | S7 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-OFR-002 | Offers | Offer conditions | S7 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-OFR-003 | Offers | Admission interviews | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-DOC-001 | Documents | Application document checklist | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-DOC-002 | Documents | Documents page and document status | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-DOC-003 | Documents | Request documents from the student | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-DOC-004 | Documents | Upload a document for the student (incl. offer letter) | S7 | YES | YES | YES | YES | NO |
| DOC-CNS-VISA-001 | Visa | Start and track a visa case | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-FIN-001 | Finance | University deposit record | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-FIN-002 | Finance | Finance tab: fees, payments, deposits, refunds | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-FIN-003 | Finance | Upload a deposit receipt / payment proof | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-ARR-001 | Arrival | Confirm enrolment (agency commission note) | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-ARR-002 | Arrival | Arrival and orientation | S8 | YES | YES | YES | YES | NO |
| DOC-CNS-HO-001 | Handoffs | A telecaller hands a lead to you | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-HO-002 | Handoffs | A website enquiry becomes your lead | S4 | YES | YES | YES | YES | NO |
| DOC-CNS-HO-003 | Handoffs | Agency students and applications | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-HO-004 | Handoffs | Self-registered students | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-ADM-001 | Admin: accounts | Create a counselor account | S2 | YES | YES | YES | YES | NO |
| DOC-CNS-ADM-002 | Admin: accounts | Manage counselor users: set-up status, re-send link, edit, deactivate | S2 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-ADM-003 | Admin: accounts | Assign / change a student's counselor (with reason) | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-ADM-004 | Admin: accounts | Assign / change an application's counselor (with reason) | S6 | YES | YES | YES | YES | NO |
| DOC-CNS-ESC-001 | Admin: escalation | Counselor tasks (admin view) | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-ESC-002 | Admin: escalation | Overdue by counselor and the escalation notice | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-PERF-001 | Admin: performance | Team performance | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-PERF-002 | Admin: performance | One counselor's report | S9 | YES | NO | NO | NO | NO |
| DOC-CNS-CFG-001 | Admin: config | Document checklist templates | S2 | YES | YES | YES | YES | NO |
| DOC-CNS-CFG-002 | Admin: config | Reminder rules and Run now | S2 | YES | PARTIAL | YES | DRAFT | NO |
| DOC-CNS-CFG-003 | Admin: config | Counselor message templates | S2 | YES | YES | YES | YES | NO |
| DOC-CNS-CFG-004 | Admin: config | Archived students: admin restore | S10 | YES | NO | NO | NO | NO |

## Unresolved items
| # | Item | Owner / session |
|---|---|---|
| U1 | Product findings P1–P22 (analysis §12) — code-read candidates; confirm or drop in the covering session, then owner decides fixes. | Sessions / Owner |
| U2 | ~40 default-based decisions (appendix 04 §3) — documented as built (D4); owner to confirm separately. | Owner |
| U3 | Browser-only unknowns in analysis §11 (dashboard Status cell, walk-in lead initial stage, timeline wording, reminder email, SA view of /overseas/admin/users, unassigned agency application notice, lost-reason owner). | S4 / S6 / S9 |
| U4 | Escalation threshold and expiry-job timing must be re-read in S9 before relying on the Day 1 + 3 rule. | S9 |
| U5 | `shoot.ts` changes (COUNSELOR_ROOT, `#calendar-feed-url` mask, "Demo super admin" mask, `signIn(..., portal)`) are on this branch only; the telecaller/BDM doc branches have not changed shoot.ts, so whichever merges second takes these. | Merge time |
| U6 | ADM-002 deactivate/reactivate steps and the deactivated sign-in message (AUTH-006) are captured in S10 (Docs Counselor C). | S10 |
| U7 | CFG-002 **Run reminders now** and populated Recent reminders are captured in S9. | S9 |
| U8 | Forward links (9 after S8, all to S9 pages) in the S2 admin pages point to pages written in S3–S9 (file names fixed in plan §Planned file names); link check is expected to list them until then. | S3–S9 |
| U10 | LEAD-009 milestone rows and the Converted badge need an application/enrolment (S7–S8). | S7/S8 |
| U11 | CAL-001 **Mark no-show** on CAP-000002 (Docs Lead Farah, 31 Oct 13:00) and the P8 text; TASK-001 admin-given task ("Given by") — both in S9. | S9 |
| U12 | OFR-001 automatic **Expired** (A1 offer deadline 31 Oct; 00:10 IST job) and the overdue English test request (due 31 Oct) — S9. OFR-002 mark a condition **Met** with evidence — S9. APP-010/P13 checked in S8 (counselor gets the Confirm enrolment form on an agency application; not submitted). | S8/S9 |
| U13 | S11 written before S9/S10: READMEs list S9/S10 pages as *(coming)*; Super Admin rows marked † (code only) until checked in S9/S10. | S9/S10 |
| U9 | Docs University + Docs MSc Data Science / Docs MBA (commission 10% / 12%) moved from S2 to S7 prep (University Master add → publish → add courses). | S7 |

## Discovered functionality (outside the 85 IDs)
| Item | Where | Note |
|---|---|---|
| School Applications | counselor sidebar item 8 | S3: opens "School-Linked Overseas Applications" (start an Overseas application for a School student by Student ID); noted in NAV-001 only, outside the 85 IDs. |
| Management tasks | counselor sidebar item 15 (`/account/management-tasks`) | Shared page; mention in NAV-001 only. |
| Lead owner change by admin | API only (P15) | No UI — not a doc feature. |
| Manage users table overflow | `/overseas/admin/users` at 1440 px | Table 716 px inside a 500 px panel: Status badge clipped, Action column off-screen; acting on a row scrolls the name out of view. Recorded as product finding P23. |
| Website enquiries auto-distributed | HO-002 | With no distribution rules, the website lead was still assigned automatically to an active Overseas telecaller (Docs Telecaller); the counselor walk-in got Imran. The manager's unassigned queue was not needed. |
| Public enquiry email validation | `/overseas/contact` | `.test` email addresses are rejected ("We could not submit your enquiry…"); the website lead uses `docs.lead.chen@example.com`. |
| Public registration email validation | `/overseas/register` | Like the enquiry form, uses an `example.com` address for the self-registered Docs student. |
| Converted lead's qualification copied to the profile | STU-005 | Asha's lead qualification became Qualification 1 on her profile. |
| Visa checklist gate | VISA-001 | A visa case can't move past preparation until every visa checklist document is uploaded and Verified ("Cannot advance past the checklist stage -- not yet verified: …"). |
| Enrolment before visa | ARR-001 | Enrolment can be confirmed with no visa decision. |
| Admin sign-in demo card | `/admin/login` | Titled "Demo super admin" (not "Demo accounts"), so the old `shoot()` mask missed it; mask extended in S2. |

## Session log
| Session | Date | Commit | Summary |
|---|---|---|---|
| S1 | 2026-10-29 | d77592f3 | Four discovery appendices; owner answers D1–D7; analysis (85 features in 24 modules, findings P1–P22), plan (S2–S12), tracker, screenshot-index skeleton. |
| S2 | 2026-10-30 | (this commit) | cnsdocs stack (3050/8050/8029) up from 045d8c40; shoot.ts COUNSELOR_ROOT + feed-URL and "Demo super admin" masks + signIn portal; build-pdfs counselor mode; OA created Docs Counselor A/B/C, Docs Telecaller, Docs UK admission checklist, Docs offer update template; 21 PNGs; ADM-001, CFG-001, CFG-003 documented, ADM-002 and CFG-002 draft (finish in S10/S9); P4 confirmed; P23 found. |
| S3 | 2026-10-30 | (this commit) | Docs Counselor A/B/C set passwords from Mailpit; AUTH-001..005 + NAV-001 documented, AUTH-006 draft (deactivated sign-in in S10); 27 PNGs incl. 390 px menu; all 15 sidebar headings verified; P18 confirmed with workaround (My profile → public header Logout); wrong-portal message captured. |
| S4 | 2026-10-30 | (this commit) | Docs Telecaller password; telecaller created Asha/Bilal/Esha and handed them to Counselor A; website enquiry Chen auto-assigned and handed over; Counselor A walk-in Divya, duplicate panel, next action, Qualified, details, qualification, convert Asha, close Bilal (lost reason), return Esha, link/unlink Divya. 37 PNGs; 12 documented + LEAD-009 draft; P2 confirmed. |
| S5 | 2026-10-30 | (this commit) | Day 1. Telecaller added Farah/Gita/Hari and booked CAP-000001..4 with Counselor A (one open appointment per lead; 60-min slots can't overlap); on Divya: 2 calls, WhatsApp record, email (delivered to Mailpit), meeting, note, follow-ups (2 open due 31 Oct + Chen 31 Oct 12:00, 1 done, 1 rescheduled, 1 cancelled); tasks (SOP checklist due 31 Oct open, pipeline review +7, 1 done, 1 cancelled); chat to Asha; calendar feed created (URL masked); CAP-000001 completed, CAP-000003 confirmed, CAP-000004 cancelled. 27 PNGs; 10 documented + CAL-001 draft; P10 confirmed; P24–P26 found. |
| S6 | 2026-10-30 | (this commit) | Self-registered student (example.com); Counselor A added Docs Walk-in Student + Docs Pending Walk-in (edit, resend, duplicate); Asha 360 profile (academic/preferences/IELTS), 2 notes; OA moved Ananya's agency application Ritika → Counselor A (reason), assigned the self-registered student to A, moved the walk-in student A → B → A with reasons; SA has no counsellor column. 30 PNGs; 12 documented; P27 found. |
| S7 | 2026-10-30 | (this commit) | S7a: OA created + published Docs University (UK, 10 %) with Docs MSc Data Science (12 %) and Docs MBA. S7b: A1 Asha MSc DS Sep 2027 (APP-000003): uploads tied to A1, Passport/Transcripts verified, English test request due 31 Oct (open), SOP request cancelled, checklist from template, gate blocked then passed (English test/SOP not required), Ready for submission → Submitted → Offer, conditional offer deadline 31 Oct + condition + interview 31 Oct, details, history; A2 walk-in MBA: on hold → resume → unconditional offer accepted. 36 PNGs; 14 documented + 3 draft; P28–P30 found. |
| S8 | 2026-10-30 | (this commit) | OA created a manual INR 15,000 fee for the walk-in student; A2: deposit GBP 3,000 Pending, payment proof + deposit receipt uploaded; passport (tied to A2) + offer letter verified; visa case Passport+Offer letter → Preparing → Appointment booked → Submitted → Decision pending → Approved; enrolment confirmed; arrival + orientation saved. Ananya advanced to Offer and the Enrolment form opened (P13 confirmed, not submitted). Universities list + Docs University 360 (no commission shown). 19 PNGs; 8 documented, APP-010 completed. |
| S11 | 2026-10-30 | (this commit) | Written early (owner choice): user-manual/README, admin-manual/README (Super Admin differences), role guides (counselor, Overseas Admin, Super Admin), demo-accounts, FAQ, troubleshooting. To be refreshed after S9/S10. |
