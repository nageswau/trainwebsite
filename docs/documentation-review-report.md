# Agent CRM Documentation — Final Review Report (Phase 9 / S11)

| | |
|---|---|
| Date | 2026-10-05 |
| Scope | Agent CRM user manual (46 pages), admin manual (8 pages + index), 4 role guides, FAQ, troubleshooting |
| Code baseline | `main` @ `6a9be770` (docs branch `docs/agent-crm-user-guide`); browser stack built from docs commit `717d6aa8` |
| Method | (1) scripted checks; (2) two independent fresh-context reviewers compared every page with the source code (file:line evidence); (3) every finding re-checked in code before fixing |
| Result | **All documentation findings fixed.** 54/54 features documented and reviewed; **42 COMPLETE**, 12 complete except for browser confirmation of one detail each (listed in §5). |

---

## 1. Scripted checks

| Check | Result |
|---|---|
| Broken links / image paths (`docs/tooling/check-doc-links.mjs`) | 0 |
| Features without a page | 0 of 54 |
| Pages missing a template section (Purpose … Related Features) | 0 of 54 |
| Screenshots referenced but missing | 0 |
| Screenshots never referenced | 1 → fixed (`team/17-staff-team-refused.png` now used in DOC-TEAM-001) |
| Byte-identical duplicate screenshots | 2 pairs → fixed (removed `team/05-staff-empty.png`, `admin-agencies/35-super-admin-commissions.png`; pages repointed; capture specs no longer create them) |
| Screenshot index vs files | 191 rows = 191 files, no duplicates |
| Terminology (enrolment/enrollment, counselling, "log in", "Agent Master") | 1 hit ("Enrolment" in an example value) → fixed. "Application status" occurrences are real UI labels/notification titles (kept). |

## 2. Documentation findings (all FIXED)

| # | Severity | Where | Problem | Fix |
|---|---|---|---|---|
| D1 | CRITICAL | comm-001, faq, troubleshooting, agency-master, adm-006 | Docs said an **estimated** commission cannot be claimed. The code accepts the claim (`workflows.py:2574`) and a claim locks the amount (`:2620`) — a user following the old text could freeze a commission at 0. | Pages now say: claim only **eligible** commissions; an estimated claim is accepted but locks the amount at 0; the 409 is for already-claimed/paid. |
| D2 | HIGH | analysis §4/§5/§8, adm-001, adm-006 | Super Admin was described as seeing read-only Agents/Commissions tables. Browser + code: those pages show "Access unavailable — Workspace not found" (`services/portal.py:1254`, `api/portal.py:41-42`). | Corrected in adm-001, adm-006, adm-007, role guide and analysis (marked "corrected in S11"). |
| D3 | MEDIUM | dash-001 | Said "Claimable commission" is always labelled INR. The panel formats each currency separately (`lib/agentDashboard.ts` formatMoney). | Replaced with the per-currency explanation; analysis §12.2 #6 withdrawn. |
| D4 | MEDIUM | rpt-001 | From/To described as creation dates for every tab; Enrollments filters by enrollment date (`agent_reports.py:451-455`). | Clarified. |
| D5 | MEDIUM | app-009 | Intake/enrollment-date warning described as shown before confirming; it appears on the saved details afterwards (`AgentApplicationEnrollment.tsx:132`). | Clarified; points to **Edit enrollment details**. |
| D6 | MEDIUM | auth-003, team-003 | Deactivation described only as "Invalid credentials". A signed-in deactivated staff member gets "Your account was deactivated by your agency…" (`deps.py`), a Master "User unavailable"; the "Your Master account is deactivated" card is effectively unreachable. | Added both messages; analysis §12.2 #2 corrected. |
| D7 | MEDIUM | notif-001 | Listed "Document verification pending" / "Assignment due soon" as agency notifications — they are IT-student seed rows (`seed.py:578-581`). | Removed; replaced with the email-only delivery note. |
| D8 | LOW | rpt-001 | Quoted server text "date_to must be on or after date_from"; users see "'To' must be on or after 'From'." | Fixed. |
| D9 | LOW | doc-002 | Upload limit described as 500 files; it counts uploads **and replacements**. | Fixed. |
| D10 | LOW | notif-001, faq | "Deadlines within three days"; reminders fire only at exactly 3, 1 and 0 days (`agent_notifications.py:162`). | Fixed. |
| D11 | LOW | adm-005 | Remit/refund 403 attributed to Super Admin; Super Admin has no buttons — the 403 is for direct API calls. | Fixed. |
| D12 | LOW | adm-003 | Claims row described with Currency/Amount; it is a count only. | Fixed. |
| D13 | LOW | adm-006 | Commission creation tied to "a Master confirms enrollment"; any move to Enrolled triggers it; manual commissions start eligible. | Fixed. |
| D14 | LOW | super-admin guide, adm-007 | "Cannot approve/suspend…" stated as absolute; it is a screen restriction — the API accepts some actions. | Reworded; product finding P2. |

Verification items answered from code during review (now documented, marked "from the application code"):
profile save / notification-settings messages, WhatsApp/SMS scope, unarchive message, task-edit message, 3-Master limit
behaviour, sign-in after reactivation, document requests do not notify students, "Payment not completed" message.

## 3. Product findings for the owner (as-built behaviour, not changed)

Documentation describes these neutrally. Severity is for the product, not the docs.

| # | Severity | Finding | Evidence |
|---|---|---|---|
| P1 | HIGH | A Master can claim an **estimated** commission (amount 0); the claim locks the amount and an Overseas Admin can still approve a ₹0 payout. | `workflows.py:2574`, `:2620`; `admin.py:1298` |
| P2 | MEDIUM | Super Admin: Agents/Commissions pages fail ("Workspace not found") and network/deposit screens hide actions, but the **API accepts** org approve/reject/suspend/reinstate, set-amount and approve-payout from super_admin. UI and API disagree. | `admin.py:1146-1149, 1272-1276, 1293`; `workflows.py:119-120` |
| P3 | MEDIUM | `.env` contains `EMAIL_ENABLED`, which the API never reads; with SMTP credentials present, welcome/invite emails are sent for real. Easy to misconfigure test stacks. | no `email_enabled` in `apps/api/app` |
| P4 | MEDIUM | Claiming a commission requires pasting its raw UUID; the agency table shows raw status words (`eligible`, `payout_pending`). | Commissions page (DOC-COMM-001) |
| P5 | LOW | A rejected agency sees the same "pending approval" text; agencies get no email/notification on approval, rejection or suspension. | `rbac.py:101-103`; DOC-AUTH-003 |
| P6 | LOW | Over-limit deposit refund is only refused after the confirmation step (server check). | DOC-ADM-005 |
| P7 | LOW | Task "Student" picker shows full emails of students with a login, while Link student masks them. | DOC-TASK-002 vs DOC-STU-009 |
| P8 | LOW | Profile validation shows raw server text "String should have at least 2 characters". | DOC-AUTH-006 |
| P9 | LOW | Logo renders very small inside a white box on sign-in page and sidebar. | screenshots `account-access/*` |
| P10 | LOW | Manual commission creation API has no screen; commission CSV export is not audited/throttled like other exports (code reading, not browser-verified). | `workflows.py:2584`, `:2543-2560` |

## 4. Coverage of the review checklist

| Checked | Result |
|---|---|
| Missing features / undocumented workflows | None (54/54; discovered items logged in the progress tracker) |
| Incorrect instructions, steps, field names, navigation paths | Verified by browser runs per session; D4–D14 fixed |
| Permissions / roles | Master vs Staff vs permission variants vs admin verified in browser; D1, D2, D6 fixed |
| Validation details | Captured from the browser; server-only messages marked "from the application code" |
| Screenshots: missing, broken, duplicated | Fixed (§1) |
| Terminology | Consistent (Agency Master, Agency Staff, Overseas Admin, Super Admin, stage, student, document request) |
| Outdated documentation | Analysis corrected in place (marked "corrected in S11") |

## 5. Completion status

A feature is COMPLETE when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES, Documented = YES and Final
Review = PASSED. **42 features are COMPLETE.** These 12 passed review but keep one detail that was confirmed only in
code, not in the browser:

| Feature | Detail not browser-verified |
|---|---|
| DOC-AUTH-006 | Save messages for profile and notification settings |
| DOC-STU-004 | Unarchive message |
| DOC-STU-008 | Journey steps once a student has applications |
| DOC-UNI-001 | Editing an agency university |
| DOC-APP-007 | Steps inside the Razorpay window; "Payment not completed" message (payment itself confirmed via signed test webhook) |
| DOC-APP-009 | Intake/enrollment-date warning |
| DOC-TASK-002 | Editing a task |
| DOC-DOC-006 | Student-with-login side of requests (code: not notified) |
| DOC-NOTIF-001 | "Deadline tomorrow" title (code-confirmed; not produced by the test data) |
| DOC-TEAM-001 | 3-Master limit note |
| DOC-TEAM-003 | Signing in again after reactivation (code: allowed with the existing password) |
| DOC-ADM-003 | Archived sub-filter of agency records |

Recommended next step: one short browser pass on the docs stack for these 12 details, then mark them COMPLETE.

## 6. Reproducibility

- Capture specs: `apps/web/tests/doc-capture/s2…s9-*.capture.ts`, config `apps/web/playwright.docs.config.ts`
  (1440×900, password inputs / demo card / dev reset links masked).
- Each spec builds its own data through the UI; run them in order on a freshly seeded stack. The S6 deposit payment
  uses a signed Razorpay **test** webhook; S8 runs the daily reminder job once.
- Link check: `node docs/tooling/check-doc-links.mjs`.
