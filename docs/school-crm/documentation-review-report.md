# School CRM Documentation — Final Review Report (S12)

| | |
|---|---|
| Date | 2026-10-06 |
| Scope | School CRM user manual (75 pages + index), admin manual (11 pages + index), 9 role guides, FAQ, troubleshooting, screenshot index |
| Code baseline | `main` @ `ce1f07c2` (docs branch `docs/school-crm-user-guide`; the branch's application code is identical to the baseline). Browser stack `schooldocs` built from the same commit. |
| Method | (1) Scripted checks. (2) Four independent fresh-context reviewers compared every page with the source code, with file:line evidence; slices: account/team/students/transfers · activities/academic/portfolio/psychometric · career counselor/360°/dashboards/parent/notifications · reports/entitlements/admin manual/FAQ/troubleshooting. (3) Each finding re-checked in the code before fixing. |
| Result | **All 29 documentation findings fixed.** 86/86 features documented and reviewed; **83 COMPLETE**, 3 PARTIAL (§5). |

---

## 1. Scripted checks

| Check | Result |
|---|---|
| Broken links / image paths (`node docs/tooling/check-doc-links.mjs docs/school-crm`) | 0 |
| Features without a page / pages without a tracker row | 0 / 0 (86 = 86) |
| Pages missing a template section (Purpose … Related Features) | 5 (no **Tips**: CAR-005, CAR-009, CAR-010, PSY-001, PSY-004) → fixed |
| Screenshots referenced but missing / never referenced | 0 / 0 |
| Byte-identical duplicate screenshots | 3 pairs → fixed: `account-access/17-reset-password-form.png` (same page as `04-set-password-form.png`) and `account-access/23-session-expired.png` (same page as `12-access-signed-out.png`) removed, pages repointed, `sch-s3` no longer creates them; `portfolio/13-portfolio-complete-view.png` was a framing fault (identical to 12) → `sch-s7` now frames the entry sections and the shot was re-captured on the after-S7 snapshot |
| Screenshot index vs files | 227 rows = 227 files, no duplicate rows |
| Forward references ("written in session Sn", "checked in S10") | 10 pages in S11 + 5 pages in S12 → replaced by links or by what was actually observed |
| Terminology (role names, enrol/enroll, counselling, "log in") | Consistent; "Counsellor" occurs only in real UI labels |
| Secrets (passwords in docs or specs) | None |

## 2. Documentation findings (all FIXED)

| # | Severity | Where | Problem | Fix |
|---|---|---|---|---|
| D1 | MEDIUM | auth-004, troubleshooting | Said a newer reset link replaces the older one. Each reset link stays valid for its own 30 minutes (`auth.py:218-238`); only a password change cancels them (`:316-323`). Only first-password links are superseded by a re-send (`services/provisioning.py`). | Corrected cause/resolution in both pages. |
| D2 | MEDIUM | stu-002, auth-002 | "Invite email sent to {email}" was described as proof the parent got an email. Invites from a student record always show it, even when email fails (`schools.py:844-874`, `SchoolStudentsPanel.tsx:25`); "share the link manually" exists only on the Team page. | Both pages explain the difference. |
| D3 | MEDIUM | notif-001 | "{student} has joined {school}" said to open Transfers; it opens the student's page (`school_transfers.py:478-484`). | Fixed. |
| D4 | MEDIUM | notif-001 | Rejection notice said to go to "the student's school"; it goes to the coordinator who filed the request, with a Student-ID-only title for incoming requests (`school_transfers.py:540-556`). | Fixed (also in xfer-003). |
| D5 | MEDIUM | s360-001 | One row claimed identical visibility for Skills, Foreign Languages, Activities and Edusphere Programs; the API differs per tab and role (`student_360.py:85-133`). | Row split into four accurate rows. |
| D6 | MEDIUM | dash-001, troubleshooting | Coordinator dashboard described with a per-card "This section couldn't load"; a failure shows the whole-page "Access unavailable" (`coordinator/dashboard/page.tsx:22-25`). | Fixed; troubleshooting notes which pages use the per-card message. |
| D7 | MEDIUM | sadm-010 | Told admins to send a deactivated user to "Forgot your password?"; that does nothing for inactive accounts (`auth.py:221`), and re-send requires reactivation (`admin.py:598-599`). | Fixed. |
| D8 | MEDIUM | rpt-003 | Grade columns given as 9–12 with Grade 8 under "Other grades"; Grade 8 has its own column (`school_analytics.py:133-151`). | Fixed; VERIFICATION REQUIRED note removed. |
| D9 | LOW | team-002 | Expired invitations were implied to disappear; they stay in Pending invites until someone tries the link (`schools.py:226-228, 281-284`). | Tip added. |
| D10 | LOW | stu-009 | "Promotion clears the roll number"; Hold back clears it too (`schools.py:1730-1751`). | Fixed. |
| D11 | LOW | stu-009 | New label "must contain the new grade number"; a typed label is saved as is (`schools.py:637-639`). | Fixed. |
| D12 | LOW | xfer-003 | Missing the incoming-request rejection title. | Added. |
| D13 | LOW | stu-004, stu-007 | Quoted raw API field names; the UI shows "Parent's email …" / "Photo …" (`lib/schoolStudents.ts:117-125`). | Fixed. |
| D14 | LOW | port-004 | Listed a permanent hint and a server message the UI never shows as validation messages (`PortfolioEntryForm.tsx:83`, `InternshipFields.tsx:38`). | Fixed. |
| D15 | LOW | port-005 | Personal statement marked required; saving an empty box clears it (`PortfolioPanel.tsx:148`). | Fixed. |
| D16 | LOW | acad-005 | Target score "free text"; stored as 20 characters max (`models.py:2251`). | Fixed. |
| D17 | LOW | psy-004 | Prerequisites omitted the per-row tier check (`school_bulk.py`). | Added. |
| D18 | LOW | dash-001 | "Completed" guidance/counselling tiles also count Follow-up Required and pre-tracking records (`schemas.py:1713-1727`). | Fixed. |
| D19 | LOW | dash-006 | Records described as "your" records; the list shows every counselor's records for portfolio students (`schools.py:2205-2217`). | Fixed. |
| D20 | LOW | s360-001 | Header said grade and date of birth show for every role; service roles see name and school only (`student_360.py:74-77`). | Fixed. |
| D21 | LOW | rpt-004 | "Grade other" range wrong (outside 8–12, not 9–12); "Grade unspecified" missing. | Fixed. |
| D22 | LOW | rpt-003 | University applications excludes withdrawn/rejected (`school_analytics.py:227-261`). | Fixed. |
| D23 | LOW | rpt-004 | Empty-state texts of the at-risk / top-performer lists misquoted (`SchoolStudentDevelopment.tsx:80-102`). | Fixed. |
| D24 | LOW | rpt-006 | Visa column omitted "In progress" (`school_global_education.py:44-71`). | Fixed. |
| D25 | LOW | sadm-006 | Tier message attributed to schools with no tier; no-tier and expired give their own messages (`schools.py:1079-1088`). | Split into three rows; prerequisite says "unexpired". |
| D26 | LOW | sadm-007 | Said the rejection notice carries the admin's note; the note is shown on the coordinator's Transfers list instead (`SchoolTransfersPanel.tsx:142`). | Fixed. |
| D27 | LOW | sadm-003 | Stale-tier message lacked the UI's "Not saved:" prefix (`AdminSchoolEditPanel.tsx:130`). | Fixed. |
| D28 | LOW | sadm-002 | VERIFICATION REQUIRED on duplicate name+city; the single form does not check it, the CSV upload does. | Resolved from code. |
| D29 | LOW | 5 feature pages | Missing **Tips** section (template). | Added. |

## 3. Product findings for the owner (as-built behaviour, not changed)

Documentation describes these neutrally. Severity is for the product, not the docs. The session-by-session list is in
`documentation-progress.md` ("Product findings for the owner").

| # | Severity | Finding | Evidence |
|---|---|---|---|
| P1 | HIGH | Forgot-password sends no email unless EduSphere's message webhook is configured (U2); school users cannot reset their own password on a plain SMTP setup. | AUTH-004; Mailpit count unchanged in S3 |
| P2 | MEDIUM | Parent invitations created from a student record always report "Invite email sent", even when the email failed; there is no re-send/copy link for invitations at all. | `schools.py:844-874`; STU-002, TEAM-001 |
| P3 | MEDIUM | Parent notifications are never marked read; the "{n} unread" badge never clears (U8). | NOTIF-002, S10 |
| P4 | MEDIUM | "Upcoming session" notification text states the time in UTC (U9). | ACT-001, NOTIF-002 |
| P5 | MEDIUM | Single-result form accepts marks above the maximum (75/50 = 150%) and a colleague can verify it; bulk entry rejects the same row. | ACAD-002 |
| P6 | MEDIUM | No sign-out on phones/narrow windows; sidebar Sign out lands on the site home page. | AUTH-007, AUTH-009 |
| P7 | MEDIUM | Super Admin gets "Workspace not found" on Schools, School Staff, School Applications; Transfers/Feedback open with the Overseas Admin sidebar. | SADM-011 |
| P8 | MEDIUM | Specialist school portfolios cannot be changed after the account is created; no academic-year admin screen (U3). | SADM-005, STU-009 |
| P9 | MEDIUM | Expired partnership: the school's Entitlements page shows only the past date, no warning. | ENT-001 |
| P10 | LOW | Over-length text (student name, activity title, subject, target score) gives only "Something went wrong.". | STU-002, ACT-001, ACAD-002/005 |
| P11 | LOW | Reports "Students by grade" groups by Grade/Class text; dashboard, grade-wise comparison and scorecards use the grade level, so numbers differ. | RPT-002 |
| P12 | LOW | Mark-attendance card always reopens with everyone ticked; duplicate-feedback error shown in a green box. | ACT-002, ACT-003 |
| P13 | LOW | Several Career Counselor screens need a reload after saving (career goal, close batch). | CAR-004, CAR-006 |
| P14 | LOW | Roster template's example row ("Jane Doe") is importable; students cannot be deleted from the screen. | STU-005 (U13) |
| P15 | LOW | Expired invitations stay in "Pending invites"; the create-school form allows a duplicate name+city (the CSV upload does not). | TEAM-002, SADM-002 |
| P16 | LOW | Raw codes shown to users (`guidance_session` in the portfolio, lowercase result/assessment statuses); `/students/new` shows "[object Object]". | PORT-001, ACAD-003, STU-001 |
| P17 | LOW | Psychometric report URL accepts any text on the single form and cannot be changed after attaching. | PSY-002 |

## 4. Coverage of the review checklist

| Checked | Result |
|---|---|
| Code (baseline `ce1f07c2`) | Every page compared by a reviewer; 29 findings, all fixed |
| Permission matrix, routes, APIs | Role/scope statements checked per page (school roles, service-role portfolios, 360° tab visibility, admin vs Super Admin); D4, D5, D7, D19, D20 fixed |
| Screenshots | 227 reviewed during S2–S10; duplicates fixed (§1) |
| Plan and tracker | 86 features ↔ 86 pages ↔ 86 tracker rows; screenshot index ↔ files |
| Validation messages | Browser-observed where possible; others marked *(from code)*; D13, D14, D23, D27 fixed |
| Outdated text | Forward references and "will be checked in S10" notes resolved |

## 5. Completion status

A feature is COMPLETE when Code Reviewed = YES, Browser Verified = YES, Screenshot = YES, Documented = YES and
Reviewed = PASSED. **83 features are COMPLETE.** These 3 passed review but remain PARTIAL in the browser:

| Feature | Detail not browser-verified | What would close it |
|---|---|---|
| DOC-SCH-AUTH-004 | The reset email itself (none is sent without the message webhook, U2); the reset form was verified with the development link | A stack with the message webhook configured |
| DOC-SCH-AUTH-007 | Expiry after ~60 minutes was simulated by removing the access cookie (U1) | Waiting out a real 60-minute session |
| DOC-SCH-SADM-006 | How school-linked applications move past `enquiry` (U15) | Owner / EduSphere application team to confirm the screen |

Open items for the owner: **U7** (exact Pydantic 422 wording on admin forms, marked *(from code)*), **U10** (WhatsApp/SMS
delivery not configured on the docs stack), **U15** (above). All other U-items are closed or confirmed and documented.

## 6. Reproducibility

- Capture specs: `apps/web/tests/doc-capture/school/sch-s2…sch-s10-*.capture.ts`, config
  `apps/web/playwright.docs.config.ts` (1440×900; passwords from `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`).
- Run them in order on a freshly seeded `schooldocs` stack (web :3020, API :8020, Mailpit :8026, `.env` needs
  `SMTP_FROM_EMAIL`). S6 creates and activates academic year 2027-28 through the Overseas Admin API.
- Link check: `node docs/tooling/check-doc-links.mjs docs/school-crm`.
- Duplicate check: `sha256sum docs/school-crm/screenshots/*/*.png | sort | uniq -D -w64`.
