# Overseas Counselor CRM Documentation — Final Review Report (S12)

> Review date 2026-11-01 · Code baseline `main` @ `045d8c40` (unchanged since S1) · Docs branch `docs/counselor-crm-user-guide`

## 1. Result
| | |
|---|---|
| Features in scope | 85 (`DOC-CNS-*`, analysis §3) |
| Browser-verified and documented | 85 |
| Reviewed **PASSED** / **COMPLETE** | 85 / 85 |
| Partial | 0 |
| Pages | 85 feature pages, 2 manual indexes, 3 role guides, demo-accounts, FAQ, troubleshooting |
| Screenshots | 240 PNGs, all indexed, all referenced, all checked for secrets |
| Link check | `node docs/tooling/check-doc-links.mjs docs/counselor-crm` → All links OK |
| PDFs | `node docs/tooling/build-pdfs.mjs counselor` → User Manual, Admin Manual, Role Guides, FAQ and Troubleshooting, Documentation Plan (`pdf/`) |

## 2. How the review was done
Three independent reviewers worked in parallel, each reporting findings only; all fixes were made by the main session.
1. **Accuracy, counselor pages** (48 pages: account access to students). It found 0 HIGH, 3 MEDIUM and 9 LOW issues, all fixed.
2. **Accuracy, applications to arrival, admin manual, guides, FAQ, troubleshooting, demo-accounts** (44 files). It found 7 MEDIUM and 6 LOW issues, all fixed. `demo-accounts.md` contains no secrets.
3. **Screenshots and safety.** It opened 107 PNGs (every login, calendar, admin, navigation, handoff and escalation shot, plus a sample of the rest), hashed all of them, and cross-checked them against the index and the pages.
   - **Secrets:** none found. Password inputs, the "Demo accounts" / "Demo super admin" cards and the iCal feed URL are all masked, and no token or reset link is visible.

The main session also ran a structure check: every page has its Doc ID, "Verified on" line and template sections. Two pages missing **Expected Result** were fixed.

## 3. Changes made in review
| Area | Change |
|---|---|
| Notices | Reminder, assignment and escalation notices **are emailed**; this was confirmed in `notification_deliveries` (New lead assigned: 6 sent; Overdue work escalated: 1 sent). The pages that said notices "show nowhere" now say they arrive by email but have no page in the portal (FUP-003, HO-001, STU-010, CFG-002, ESC-002, ADM-003, admin README, Overseas Admin guide, FAQ). |
| Intake | It can be changed by recording **Deferred** with a **New intake**. Fixed in APP-001, APP-002, APP-008, the FAQ and the Overseas Admin guide. |
| Outcomes | APP-007 now lists the fields for each outcome, and makes clear that only **On hold** pauses stage changes. |
| Gate | Complete also includes **Approved** (CV/SOP); clarified that there is no check when no template and no checklist exist (APP-005, DOC-001, FAQ). |
| Admin | Previous counselor keeps the student while holding one of their applications (ADM-003); "closed" includes terminal outcomes (ADM-004); email templates have a Subject and a 5000-character limit (CFG-003); table heading "Overseas counselors" / "Total" (PERF-001). |
| Smaller | Visa offer rule applies to agency applications only; Converted happens within about 15 minutes; call follow-up checkbox not shown for closing outcomes; WhatsApp/SMS need a valid mobile; New lead assigned is immediate; appointment **Cancel** button and "Appointment rescheduled."; dashboard ordering; export cap 5,000; task About links; task two-year limit; meeting notes 2000 characters; disabled WhatsApp/email messages. |
| Screenshots | 2 byte-identical sign-in shots removed and the pages re-pointed; `arrival/05` and `escalation/03` re-captured to show the panel and the Overdue filter; 2 unused Super Admin shots and 1 unused chat shot removed; 2 Super Admin shots and the overdue-tasks shot now referenced; a note added on the no-show shot's timing; "DUDocs University" explained (P33). |

## 4. Product findings (owner)
Full list in [documentation-analysis.md §12](documentation-analysis.md): **P1–P33**. Browser-confirmed: P1, P2, P3, P4, P7, P8, P10, P13, P16 (part), P18, P19, P23–P33. The others remain code-read candidates that the docs describe as built. Highest impact for counselors and admins:
- **P13** Agency enrolment: the Enrolment panel offers **Confirm enrolment** to the counselor, while stage moves say only the agency's Master confirms.
- **P19** Deactivating a counselor is immediate, with no warning and no handover of their leads, students, applications or tasks.
- **P1 / P31** Reminder and escalation notices are emailed but have no page in the counselor or Overseas Admin portal.
- **P18** On phones the portal menu has no Sign out (workaround: My profile → Logout).
- **P28** A document uploaded "Not tied to an application" never reaches the counselor's review queue.
- **P2 / P32** Return is offered on closed leads; a Converted lead still shows open follow-ups and the next-action prompt.

## 5. Notes for readers of this set
- **Owner decision D3 changed on 2026-10-30.** The overdue and expired states (S9) were prepared by moving test dates back in the documentation database and running the expiry jobs by hand. Every affected screenshot is marked "state prepared by data setup" in the [screenshot index](screenshot-index.md).
- About 40 behaviours rest on builder defaults (NEEDS_CONFIRMATION/UNVERIFIED decisions, appendix 04 §3). They are documented as built (D4).
- All data in the screenshots is fictional **Docs** test data or seeded demo data. See [demo-accounts.md](demo-accounts.md).

## 6. Open owner items
| # | Item |
|---|---|
| O1 | Decide fixes for product findings P1–P33. |
| O2 | Confirm or change the ~40 default-based behaviours (appendix 04 §3). |
| O3 | Re-check pages whose code changes after `045d8c40` (`git diff --stat 045d8c40..<new> -- apps/`). |
