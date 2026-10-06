# School CRM — Screenshot Index

Captured with Playwright (Chromium), viewport **1440 × 900** unless noted, light theme, locale en-IN, timezone Asia/Kolkata.
Files live under `docs/school-crm/screenshots/<module>/`. Element shots capture one card only (the viewport is grown
so the whole card fits); they are marked "(element shot)".

| Capture run | Stack | Date |
|---|---|---|
| S2 — `apps/web/tests/doc-capture/school/sch-s2-admin.capture.ts` | `schooldocs` from `main` @ `ce1f07c2` (+ docs commits), web :3020 | 2026-10-05 |
| S3 — `sch-s3-access-team.capture.ts` (after S2 on the same DB) | same | 2026-10-06 |
| S4 — `sch-s4-students.capture.ts` (after S3 on the same DB) | same | 2026-10-06 |
| S5 — `sch-s5-activities.capture.ts` (after S4 on the same DB) | same | 2026-10-06 |
| S6 — `sch-s6-transfers-promotion.capture.ts` (after S5 on the same DB; creates and activates academic year 2027-28 through the admin API) | same | 2026-10-06 |
| S7 — `sch-s7-academic-portfolio.capture.ts` (after S6 on the same DB) | same | 2026-10-06 |
| S8 — `sch-s8-career-counselor.capture.ts` (after S7 on the same DB) | same | 2026-10-06 |
| S9 — `sch-s9-psy-360-pathway.capture.ts` (after S8 on the same DB) | same | 2026-10-06 |

| Screenshot | Module | Feature | Step | Role | Description |
|---|---|---|---|---|---|
| [account-access/01-login-page.png](screenshots/account-access/01-login-page.png) | Account access | DOC-SCH-AUTH-001 | Login page (password and demo card masked) | Visitor | Overseas Education Portal sign-in page used by every school role |
| [admin-schools/01-schools-list.png](screenshots/admin-schools/01-schools-list.png) | School administration | DOC-SCH-SADM-001 | 1 Open the list | Overseas Admin | Partner Schools list with the seeded school |
| [admin-schools/02-schools-search.png](screenshots/admin-schools/02-schools-search.png) | School administration | DOC-SCH-SADM-001 | 2 Search | Overseas Admin | List filtered by "Docs" |
| [admin-schools/03-create-school-filled.png](screenshots/admin-schools/03-create-school-filled.png) | School administration | DOC-SCH-SADM-002 | 1 Fill in | Overseas Admin | Create school form filled in (element shot of the card) |
| [admin-schools/04-create-school-success.png](screenshots/admin-schools/04-create-school-success.png) | School administration | DOC-SCH-SADM-002 | 2 Created | Overseas Admin | Green success with School code and emailed link |
| [admin-schools/05-create-school-email-exists.png](screenshots/admin-schools/05-create-school-email-exists.png) | School administration | DOC-SCH-SADM-002 | Error | Overseas Admin | "Email already exists" |
| [admin-schools/06-edit-school-lookup.png](screenshots/admin-schools/06-edit-school-lookup.png) | School administration | DOC-SCH-SADM-003 | 1 Look up | Overseas Admin | School ID entered |
| [admin-schools/07-edit-school-loaded.png](screenshots/admin-schools/07-edit-school-loaded.png) | School administration | DOC-SCH-SADM-003 | 1 Loaded | Overseas Admin | Edit school profile form loaded (element shot of the card) |
| [admin-schools/08-edit-school-upgrade-saved.png](screenshots/admin-schools/08-edit-school-upgrade-saved.png) | School administration | DOC-SCH-SADM-003 | 3a Upgrade | Overseas Admin | Bronze → Silver saved, newly available services |
| [admin-schools/09-edit-school-downgrade-confirm.png](screenshots/admin-schools/09-edit-school-downgrade-confirm.png) | School administration | DOC-SCH-SADM-003 | 3b Confirm downgrade | Overseas Admin | Downgrade confirmation listing lost services |
| [admin-schools/10-edit-school-downgrade-saved.png](screenshots/admin-schools/10-edit-school-downgrade-saved.png) | School administration | DOC-SCH-SADM-003 | 3b Saved | Overseas Admin | "Partnership is now Bronze." |
| [admin-schools/11-edit-school-no-changes.png](screenshots/admin-schools/11-edit-school-no-changes.png) | School administration | DOC-SCH-SADM-003 | Validation | Overseas Admin | "No changes to save." |
| [admin-schools/12-edit-school-not-found.png](screenshots/admin-schools/12-edit-school-not-found.png) | School administration | DOC-SCH-SADM-003 | Validation | Overseas Admin | "No school found with that School ID" |
| [admin-schools/13-bulk-onboard-panel.png](screenshots/admin-schools/13-bulk-onboard-panel.png) | School administration | DOC-SCH-SADM-004 | 1 Template | Overseas Admin | Download button and Column reference |
| [admin-schools/14-bulk-onboard-result.png](screenshots/admin-schools/14-bulk-onboard-result.png) | School administration | DOC-SCH-SADM-004 | 4 Result | Overseas Admin | 2 added, 3 rejected rows with reasons |
| [admin-schools/15-bulk-onboard-file-error.png](screenshots/admin-schools/15-bulk-onboard-file-error.png) | School administration | DOC-SCH-SADM-004 | File error | Overseas Admin | "Missing required column: coordinator_email" |
| [admin-schools/16-school-staff-list.png](screenshots/admin-schools/16-school-staff-list.png) | School administration | DOC-SCH-SADM-005 | 1 List | Overseas Admin | School staff table with portfolio counts |
| [admin-schools/17-school-staff-form.png](screenshots/admin-schools/17-school-staff-form.png) | School administration | DOC-SCH-SADM-005 | 3 Portfolio | Overseas Admin | Academic Team account with 2 schools selected |
| [admin-schools/18-school-staff-created.png](screenshots/admin-schools/18-school-staff-created.png) | School administration | DOC-SCH-SADM-005 | 4 Created | Overseas Admin | "Account created for …" |
| [admin-schools/19-users-resend-link.png](screenshots/admin-schools/19-users-resend-link.png) | School administration | DOC-SCH-SADM-010 | 1 Find | Overseas Admin | Users page, account Awaiting setup with Re-send link |
| [admin-schools/20-users-resend-result.png](screenshots/admin-schools/20-users-resend-result.png) | School administration | DOC-SCH-SADM-010 | 2 Re-sent | Overseas Admin | "New link created for …" |
| [admin-schools/21-superadmin-workspace-not-found.png](screenshots/admin-schools/21-superadmin-workspace-not-found.png) | School administration | DOC-SCH-SADM-011 | Limitation | Super Admin | Schools page: Access unavailable — Workspace not found |
| [admin-schools/22-superadmin-transfers-overseas-sidebar.png](screenshots/admin-schools/22-superadmin-transfers-overseas-sidebar.png) | School administration | DOC-SCH-SADM-011 | Limitation | Super Admin | School Transfers opened with the Overseas Admin sidebar |
| [account-access/02-login-invalid-credentials.png](screenshots/account-access/02-login-invalid-credentials.png) | Account access | DOC-SCH-AUTH-001 | Error | Visitor | "Invalid credentials" |
| [account-access/03-login-wrong-portal.png](screenshots/account-access/03-login-wrong-portal.png) | Account access | DOC-SCH-AUTH-001 | Error | School Coordinator | School account used on the IT sign-in page |
| [account-access/04-set-password-form.png](screenshots/account-access/04-set-password-form.png) | Account access | DOC-SCH-AUTH-003 | 2 Choose password | School Coordinator (new) | Welcome link page "Choose a new password" (password masked) |
| [account-access/05-first-sign-in-coordinator-dashboard.png](screenshots/account-access/05-first-sign-in-coordinator-dashboard.png) | Account access | DOC-SCH-AUTH-001/003/009 | 3 Landing | School Coordinator | First sign-in: dashboard of a new school; also the sidebar example |
| [account-access/06-set-password-invalid-link.png](screenshots/account-access/06-set-password-invalid-link.png) | Account access | DOC-SCH-AUTH-003 | Error | Visitor | "Reset token is invalid or expired" |
| [account-access/07-reset-link-missing-token.png](screenshots/account-access/07-reset-link-missing-token.png) | Account access | DOC-SCH-AUTH-003 | Error | Visitor | Reset link missing its token |
| [account-access/08-invite-accept-form.png](screenshots/account-access/08-invite-accept-form.png) | Account access | DOC-SCH-AUTH-002 | 2 Choose password | Teacher (invited) | "Set up your EduSphere login" (password masked) |
| [account-access/09-invite-accepted-teacher-dashboard.png](screenshots/account-access/09-invite-accepted-teacher-dashboard.png) | Account access | DOC-SCH-AUTH-002 | 3 Signed in | Teacher | Teacher dashboard right after accepting |
| [account-access/10-invite-already-used.png](screenshots/account-access/10-invite-already-used.png) | Account access | DOC-SCH-AUTH-002 | Error | Visitor | Invitation already used |
| [account-access/11-login-deactivated.png](screenshots/account-access/11-login-deactivated.png) | Account access | DOC-SCH-AUTH-008, TEAM-003 | Error | Teacher (deactivated) | Deactivated account: "Invalid credentials" |
| [account-access/12-access-signed-out.png](screenshots/account-access/12-access-signed-out.png) | Account access | DOC-SCH-AUTH-008 | Signed out | Visitor | "Access unavailable — Not authenticated" |
| [account-access/13-access-wrong-role.png](screenshots/account-access/13-access-wrong-role.png) | Account access | DOC-SCH-AUTH-008 | Wrong role | Teacher | "Principal role required" |
| [account-access/14-access-other-school-student.png](screenshots/account-access/14-access-other-school-student.png) | Account access | DOC-SCH-AUTH-008 | Other school | School Coordinator | "This student is at a different institution" |
| [account-access/15-forgot-password-form.png](screenshots/account-access/15-forgot-password-form.png) | Account access | DOC-SCH-AUTH-004 | 1 Request | Teacher | Reset your password form |
| [account-access/16-forgot-password-sent.png](screenshots/account-access/16-forgot-password-sent.png) | Account access | DOC-SCH-AUTH-004 | 1 Sent | Teacher | Neutral confirmation (development box masked) |
| [account-access/17-reset-password-form.png](screenshots/account-access/17-reset-password-form.png) | Account access | DOC-SCH-AUTH-004 | 2 New password | Teacher | Choose a new password (masked) |
| [account-access/18-change-password-form.png](screenshots/account-access/18-change-password-form.png) | Account access | DOC-SCH-AUTH-005 | 1 Form | Teacher | Change your password (masked) |
| [account-access/19-change-password-wrong-current.png](screenshots/account-access/19-change-password-wrong-current.png) | Account access | DOC-SCH-AUTH-005 | Error | Teacher | "Incorrect current password" |
| [account-access/20-change-password-success.png](screenshots/account-access/20-change-password-success.png) | Account access | DOC-SCH-AUTH-005 | 2 Saved | Teacher | "Your password was changed." |
| [account-access/21-profile-saved.png](screenshots/account-access/21-profile-saved.png) | Account access | DOC-SCH-AUTH-006 | 1 Saved | Teacher | "Your profile was updated." |
| [account-access/22-notification-settings-saved.png](screenshots/account-access/22-notification-settings-saved.png) | Account access | DOC-SCH-AUTH-006 | 2 Saved | Teacher | WhatsApp ticked, "Notification settings saved." |
| [account-access/23-session-expired.png](screenshots/account-access/23-session-expired.png) | Account access | DOC-SCH-AUTH-007 | Session ended | Teacher | "Not authenticated" after the access cookie was removed |
| [account-access/25-mobile-menu-coordinator.png](screenshots/account-access/25-mobile-menu-coordinator.png) | Account access | DOC-SCH-AUTH-009 | Menu | School Coordinator | Mobile menu at **390 × 844** |
| [team/01-team-list.png](screenshots/team/01-team-list.png) | Team | DOC-SCH-TEAM-002 | 1 Team | School Coordinator | Your team before invitations |
| [team/02-invite-form-filled.png](screenshots/team/02-invite-form-filled.png) | Team | DOC-SCH-TEAM-001 | 1 Fill in | School Coordinator | Invite a team member (Teacher) |
| [team/03-invite-sent.png](screenshots/team/03-invite-sent.png) | Team | DOC-SCH-TEAM-001 | 2 Sent | School Coordinator | "Invite sent to … It's valid for 7 days." |
| [team/04-invite-email-exists.png](screenshots/team/04-invite-email-exists.png) | Team | DOC-SCH-TEAM-001 | Error | School Coordinator | "Email already exists" |
| [team/05-team-and-pending-invites.png](screenshots/team/05-team-and-pending-invites.png) | Team | DOC-SCH-TEAM-002 | 2 Pending | School Coordinator | Your team + Pending invites (element shot of main) |
| [team/06-teacher-deactivated.png](screenshots/team/06-teacher-deactivated.png) | Team | DOC-SCH-TEAM-003 | 1 Deactivated | School Coordinator | "Docs Teacher B deactivated." |
| [students/01-roster.png](screenshots/students/01-roster.png) | Students & roster | DOC-SCH-STU-001 | 1 Roster | School Coordinator | Student roster with row actions (seeded students) |
| [students/02-roster-empty.png](screenshots/students/02-roster-empty.png) | Students & roster | DOC-SCH-STU-001 | Empty | School Coordinator | Empty roster of a new school |
| [students/03-add-student-filled.png](screenshots/students/03-add-student-filled.png) | Students & roster | DOC-SCH-STU-002 | 1 Fill in | School Coordinator | Add one student, all groups filled (element shot) |
| [students/04-add-student-success.png](screenshots/students/04-add-student-success.png) | Students & roster | DOC-SCH-STU-002 | 2 Added | School Coordinator | Added + parent invite sent |
| [students/05-add-student-roll-conflict.png](screenshots/students/05-add-student-roll-conflict.png) | Students & roster | DOC-SCH-STU-002 | Error | School Coordinator | Roll number already used |
| [students/06-edit-student.png](screenshots/students/06-edit-student.png) | Students & roster | DOC-SCH-STU-003 | 1 Edit | School Coordinator | Edit form, section changed (element shot) |
| [students/07-edit-student-saved.png](screenshots/students/07-edit-student-saved.png) | Students & roster | DOC-SCH-STU-003 | 2 Saved | School Coordinator | "Student updated." with pending-invite note |
| [students/08-link-parent-form.png](screenshots/students/08-link-parent-form.png) | Students & roster | DOC-SCH-STU-004 | 1 Email | School Coordinator | Link a parent to Kabir Nair |
| [students/09-link-parent-success.png](screenshots/students/09-link-parent-success.png) | Students & roster | DOC-SCH-STU-004 | 2 Linked | School Coordinator | "Parent linked to this student." |
| [students/10-link-parent-already-linked.png](screenshots/students/10-link-parent-already-linked.png) | Students & roster | DOC-SCH-STU-004 | Error | School Coordinator | Parent already linked |
| [students/11-bulk-template-and-columns.png](screenshots/students/11-bulk-template-and-columns.png) | Students & roster | DOC-SCH-STU-005 | 1 Template | School Coordinator | Download template + Column reference |
| [students/13-bulk-upload-result.png](screenshots/students/13-bulk-upload-result.png) | Students & roster | DOC-SCH-STU-005 | 4 Result | School Coordinator | 11 added, 6 rejected with reasons (element shot) |
| [students/14-student-profile-header.png](screenshots/students/14-student-profile-header.png) | Students & roster | DOC-SCH-STU-006 | 1 Details | School Coordinator | Profile card of Aarav Mehta (initials) |
| [students/15-student-journey-timeline.png](screenshots/students/15-student-journey-timeline.png) | Students & roster | DOC-SCH-STU-006 | 2 Timeline | School Coordinator | Journey timeline events |
| [students/16-student-progress-scorecard.png](screenshots/students/16-student-progress-scorecard.png) | Students & roster | DOC-SCH-STU-006 | 3 Scorecard | School Coordinator | Progress report card + Progress scorecard |
| [students/17-photo-too-big.png](screenshots/students/17-photo-too-big.png) | Students & roster | DOC-SCH-STU-007 | Error | School Coordinator | "Photo must be at most 2 MB" |
| [students/18-photo-saved.png](screenshots/students/18-photo-saved.png) | Students & roster | DOC-SCH-STU-007 | 1 Saved | School Coordinator | Generated initials avatar uploaded, "Photo saved." |
| [students/19-photo-remove-confirm.png](screenshots/students/19-photo-remove-confirm.png) | Students & roster | DOC-SCH-STU-007 | 3 Remove | School Coordinator | Confirm remove / Cancel |
| [students/20-progress-report-downloaded.png](screenshots/students/20-progress-report-downloaded.png) | Students & roster | DOC-SCH-STU-008 | 1 Downloaded | School Coordinator | "Report downloaded." |
| [students/21-student-profile-principal.png](screenshots/students/21-student-profile-principal.png) | Students & roster | DOC-SCH-STU-006 | Role view | Principal | Principal's view of the student page |
| [students/22-student-profile-teacher.png](screenshots/students/22-student-profile-teacher.png) | Students & roster | DOC-SCH-STU-006 | Role view | Teacher | Teacher's view (assigned student) |
| [activities/01-schedule-activity-form.png](screenshots/activities/01-schedule-activity-form.png) | Activities | DOC-SCH-ACT-001 | 1 Fill in | School Coordinator | Schedule an activity (Career seminar, next week) |
| [activities/02-activity-scheduled.png](screenshots/activities/02-activity-scheduled.png) | Activities | DOC-SCH-ACT-001 | 2 Scheduled | School Coordinator | "Docs Career Seminar scheduled." |
| [activities/03-activities-list.png](screenshots/activities/03-activities-list.png) | Activities | DOC-SCH-ACT-001 | 3 List | School Coordinator | Activities with Mark attendance / Give feedback |
| [activities/04-mark-attendance.png](screenshots/activities/04-mark-attendance.png) | Activities | DOC-SCH-ACT-002 | 2 Untick | School Coordinator | Mark attendance card, two students unticked (element shot) |
| [activities/05-attendance-recorded.png](screenshots/activities/05-attendance-recorded.png) | Activities | DOC-SCH-ACT-002 | 3 Saved | School Coordinator | "Attendance recorded for 18 student(s)." |
| [activities/06-feedback-awaiting.png](screenshots/activities/06-feedback-awaiting.png) | Activities | DOC-SCH-ACT-003 | 1 Find | School Coordinator | Activity feedback, Awaiting feedback |
| [activities/07-feedback-form.png](screenshots/activities/07-feedback-form.png) | Activities | DOC-SCH-ACT-003 | 2 Fill in | School Coordinator | Feedback form filled (element shot) |
| [activities/08-feedback-saved.png](screenshots/activities/08-feedback-saved.png) | Activities | DOC-SCH-ACT-003 | 3 Saved | School Coordinator | "Feedback saved for Docs Parent Orientation." |
| [activities/09-feedback-duplicate.png](screenshots/activities/09-feedback-duplicate.png) | Activities | DOC-SCH-ACT-003 | Error | School Coordinator | Second tab: already submitted, Copy text / Dismiss |
| [activities/10-feedback-submitted-view.png](screenshots/activities/10-feedback-submitted-view.png) | Activities | DOC-SCH-ACT-003 | 4 View | School Coordinator | Submitted feedback expanded |
| [activities/11-schedule-tier-not-included.png](screenshots/activities/11-schedule-tier-not-included.png) | Activities | DOC-SCH-ACT-001 | Error | School Coordinator (Bronze) | Monthly campus visit not in Bronze |
| [activities/12-schedule-no-tier.png](screenshots/activities/12-schedule-no-tier.png) | Activities | DOC-SCH-ACT-001 | Error | School Coordinator (no tier) | "This school has no active partnership tier." |
| [activities/13-schedule-tier-expired.png](screenshots/activities/13-schedule-tier-expired.png) | Activities | DOC-SCH-ACT-001 | Error | School Coordinator (expired) | "This school's partnership expired on …" |
| [activities/14-principal-feedback.png](screenshots/activities/14-principal-feedback.png) | Activities | DOC-SCH-ACT-004 | 2 Read | Principal | Principal feedback page with View feedback open |
| [activities/15-daily-attendance-unmarked.png](screenshots/activities/15-daily-attendance-unmarked.png) | Activities | DOC-SCH-ACT-005 | 1 Day | Teacher | Today, nothing marked |
| [activities/16-daily-attendance-marked.png](screenshots/activities/16-daily-attendance-marked.png) | Activities | DOC-SCH-ACT-005 | 2 Mark | Teacher | Mark all present + Absent/Late/Excused |
| [activities/17-daily-attendance-saved.png](screenshots/activities/17-daily-attendance-saved.png) | Activities | DOC-SCH-ACT-005 | 3 Saved | Teacher | "Attendance saved for 10 students on …" |
| [activities/18-daily-attendance-future-date.png](screenshots/activities/18-daily-attendance-future-date.png) | Activities | DOC-SCH-ACT-005 | Note | Teacher | Future date cannot be marked |
| [activities/19-daily-attendance-before-enrolment.png](screenshots/activities/19-daily-attendance-before-enrolment.png) | Activities | DOC-SCH-ACT-005 | Note | Teacher | None enrolled on the chosen past date |
| [admin-schools/23-activity-feedback-list.png](screenshots/admin-schools/23-activity-feedback-list.png) | School administration | DOC-SCH-SADM-009 | 1 List | Overseas Admin | Activity Feedback across schools |
| [admin-schools/24-activity-feedback-school-filter.png](screenshots/admin-schools/24-activity-feedback-school-filter.png) | School administration | DOC-SCH-SADM-009 | 2 Filter | Overseas Admin | Filtered to Docs Bronze School (none) |
| [transfers/01-request-transfer-form.png](screenshots/transfers/01-request-transfer-form.png) | Transfers | DOC-SCH-XFER-001 | 1 Form | School Coordinator | Request a transfer (destination + reason) |
| [transfers/02-transfer-requested.png](screenshots/transfers/02-transfer-requested.png) | Transfers | DOC-SCH-XFER-001 | 2 Pending | School Coordinator | "Transfer requested" badge on the profile |
| [transfers/03-incoming-request-form.png](screenshots/transfers/03-incoming-request-form.png) | Transfers | DOC-SCH-XFER-002 | 1 Form | School Coordinator (Docs Platinum Two) | Request a student by Student ID |
| [transfers/04-incoming-request-sent.png](screenshots/transfers/04-incoming-request-sent.png) | Transfers | DOC-SCH-XFER-002 | 2 Sent | School Coordinator (Docs Platinum Two) | Neutral confirmation |
| [transfers/05-transfer-requests-pending.png](screenshots/transfers/05-transfer-requests-pending.png) | Transfers | DOC-SCH-XFER-003 | 1 Pending | School Coordinator | Pending requests with Cancel |
| [transfers/06-transfer-cancelled.png](screenshots/transfers/06-transfer-cancelled.png) | Transfers | DOC-SCH-XFER-003 | 2 Cancelled | School Coordinator | "Request cancelled." |
| [transfers/07-transfer-requests-all.png](screenshots/transfers/07-transfer-requests-all.png) | Transfers | DOC-SCH-XFER-003 | 3 All | School Coordinator | Approved / Rejected (admin note) / Cancelled / Pending |
| [transfers/08-transfer-history-on-profile.png](screenshots/transfers/08-transfer-history-on-profile.png) | Transfers | DOC-SCH-XFER-003 | 5 History | School Coordinator (Docs Platinum Two) | Transfer history card at the new school |
| [admin-schools/25-transfers-pending-queue.png](screenshots/admin-schools/25-transfers-pending-queue.png) | School administration | DOC-SCH-SADM-007 | 1 Queue | Overseas Admin | Pending transfer requests |
| [admin-schools/26-transfer-warnings.png](screenshots/admin-schools/26-transfer-warnings.png) | School administration | DOC-SCH-SADM-007 | 2 Warnings | Overseas Admin | No staff school portfolio + pending parent invite warnings |
| [admin-schools/27-transfer-approve-confirm.png](screenshots/admin-schools/27-transfer-approve-confirm.png) | School administration | DOC-SCH-SADM-007 | 3a Confirm | Overseas Admin | Approval consequences + Confirm approval |
| [admin-schools/28-transfer-approved.png](screenshots/admin-schools/28-transfer-approved.png) | School administration | DOC-SCH-SADM-007 | 3a Approved | Overseas Admin | "Moved Docs Student Vihaan to Docs Platinum Two …" |
| [admin-schools/29-transfer-reject-note.png](screenshots/admin-schools/29-transfer-reject-note.png) | School administration | DOC-SCH-SADM-007 | 3b Reject | Overseas Admin | Note for the requesting coordinator |
| [admin-schools/30-transfers-all.png](screenshots/admin-schools/30-transfers-all.png) | School administration | DOC-SCH-SADM-007 | 4 All | Overseas Admin | Status filter All |
| [students/23-promotion-all-in-current-year.png](screenshots/students/23-promotion-all-in-current-year.png) | Students & roster | DOC-SCH-STU-009 | 1 Before | School Coordinator | Every student "Already in 2026-27" (new year not opened) |
| [students/24-promotion-list.png](screenshots/students/24-promotion-list.png) | Students & roster | DOC-SCH-STU-009 | 2 Select | School Coordinator | All selected, actions Promote/Hold back |
| [students/25-promotion-confirm.png](screenshots/students/25-promotion-confirm.png) | Students & roster | DOC-SCH-STU-009 | 3 Confirm | School Coordinator | "Promote 16 and hold back 1 into 2027-28?" |
| [students/26-promotion-result.png](screenshots/students/26-promotion-result.png) | Students & roster | DOC-SCH-STU-009 | 4 Result | School Coordinator | "Done for 2027-28: 13 promoted, 1 held back, 3 not changed, 0 skipped." |
| [students/27-grade-history.png](screenshots/students/27-grade-history.png) | Students & roster | DOC-SCH-STU-009 | 5 Grade history | School Coordinator | Promoted Grade 8 → Grade 9 entry |
| [academic-team/01-dashboard.png](screenshots/academic-team/01-dashboard.png) | Academic Team | DOC-SCH-ACAD-001 | 1 Dashboard | Academic Team | Academic Team dashboard (top) |
| [academic-team/02-portfolio-progress.png](screenshots/academic-team/02-portfolio-progress.png) | Academic Team | DOC-SCH-ACAD-001 | 2 Table | Academic Team | Portfolio progress (element shot) |
| [academic-team/03-upload-result-form.png](screenshots/academic-team/03-upload-result-form.png) | Academic Team | DOC-SCH-ACAD-002 | 2 Fill in | Academic Team | Upload a result filled (element shot) |
| [academic-team/04-result-saved-as-draft.png](screenshots/academic-team/04-result-saved-as-draft.png) | Academic Team | DOC-SCH-ACAD-002 | 3 Saved | Academic Team | "Mathematics result saved as Draft." |
| [academic-team/05-results-uploader-view.png](screenshots/academic-team/05-results-uploader-view.png) | Academic Team | DOC-SCH-ACAD-003 | 1 Uploader | Academic Team | Results with "Ask another Academic Team member…" (element shot) |
| [academic-team/06-results-verify-button.png](screenshots/academic-team/06-results-verify-button.png) | Academic Team | DOC-SCH-ACAD-003 | 1 Colleague | Academic Team | Results with Verify/Publish for a colleague (element shot) |
| [academic-team/07-result-verified.png](screenshots/academic-team/07-result-verified.png) | Academic Team | DOC-SCH-ACAD-003 | 2 Verified | Academic Team | "Result verified." |
| [academic-team/08-result-published.png](screenshots/academic-team/08-result-published.png) | Academic Team | DOC-SCH-ACAD-003 | 3 Published | Academic Team | Results after publishing (element shot) |
| [academic-team/09-bulk-results-panel.png](screenshots/academic-team/09-bulk-results-panel.png) | Academic Team | DOC-SCH-ACAD-004 | 1 Panel | Academic Team | Bulk entry — results opened |
| [academic-team/10-bulk-results-report.png](screenshots/academic-team/10-bulk-results-report.png) | Academic Team | DOC-SCH-ACAD-004 | 3 Result | Academic Team | 1 added, 2 rejected |
| [academic-team/11-test-prep-start.png](screenshots/academic-team/11-test-prep-start.png) | Academic Team | DOC-SCH-ACAD-005 | 1 Start | Academic Team | Start test preparation (IELTS) |
| [academic-team/12-test-prep-score-recorded.png](screenshots/academic-team/12-test-prep-score-recorded.png) | Academic Team | DOC-SCH-ACAD-005 | 2 Score | Academic Team | "Result recorded." |
| [academic-team/13-language-started.png](screenshots/academic-team/13-language-started.png) | Academic Team | DOC-SCH-ACAD-006 | 1 Start | Academic Team | "German classes started." |
| [academic-team/14-language-certified.png](screenshots/academic-team/14-language-certified.png) | Academic Team | DOC-SCH-ACAD-006 | 2 Certified | Academic Team | "Marked certified." |
| [academic-team/15-bulk-test-prep-report.png](screenshots/academic-team/15-bulk-test-prep-report.png) | Academic Team | DOC-SCH-ACAD-007 | 2 Result | Academic Team | Bulk test prep: 1 added, 1 rejected |
| [portfolio/01-portfolio-overview.png](screenshots/portfolio/01-portfolio-overview.png) | Digital Portfolio | DOC-SCH-PORT-001 | 1 Overview | Academic Team | Digital Portfolio card with completion % |
| [portfolio/02-add-entry-form.png](screenshots/portfolio/02-add-entry-form.png) | Digital Portfolio | DOC-SCH-PORT-002 | 1 Add | Academic Team | Add award form |
| [portfolio/03-entry-added.png](screenshots/portfolio/03-entry-added.png) | Digital Portfolio | DOC-SCH-PORT-002 | 2 Saved | Academic Team | "Award added." |
| [portfolio/04-entry-date-error.png](screenshots/portfolio/04-entry-date-error.png) | Digital Portfolio | DOC-SCH-PORT-002 | Error | Academic Team | "End date must not be before start date" |
| [portfolio/05-delete-confirm.png](screenshots/portfolio/05-delete-confirm.png) | Digital Portfolio | DOC-SCH-PORT-002 | 4 Delete | Academic Team | Confirm delete button |
| [portfolio/06-skill-india-errors.png](screenshots/portfolio/06-skill-india-errors.png) | Digital Portfolio | DOC-SCH-PORT-003 | Error | Academic Team | Certified without number/date |
| [portfolio/07-skill-india-form.png](screenshots/portfolio/07-skill-india-form.png) | Digital Portfolio | DOC-SCH-PORT-003 | 2 Details | Academic Team | Skill India details filled |
| [portfolio/08-skill-india-saved.png](screenshots/portfolio/08-skill-india-saved.png) | Digital Portfolio | DOC-SCH-PORT-003 | 3 Saved | Academic Team | "Certification added." |
| [portfolio/09-internship-form.png](screenshots/portfolio/09-internship-form.png) | Digital Portfolio | DOC-SCH-PORT-004 | 1 Add | Academic Team | Internship with tracking fields |
| [portfolio/10-certificate-too-big.png](screenshots/portfolio/10-certificate-too-big.png) | Digital Portfolio | DOC-SCH-PORT-004 | Error | Academic Team | "Certificate must be at most 5 MB" |
| [portfolio/11-certificate-saved.png](screenshots/portfolio/11-certificate-saved.png) | Digital Portfolio | DOC-SCH-PORT-004 | 2 Uploaded | Academic Team | "Certificate saved." with Download/Replace/Remove |
| [portfolio/12-personal-statement-saved.png](screenshots/portfolio/12-personal-statement-saved.png) | Digital Portfolio | DOC-SCH-PORT-005 | 2 Saved | Academic Team | "Personal statement saved." |
| [portfolio/13-portfolio-complete-view.png](screenshots/portfolio/13-portfolio-complete-view.png) | Digital Portfolio | DOC-SCH-PORT-001 | 3 Sections | Academic Team | Portfolio after entries |
| [portfolio/14-portfolio-tier-denied.png](screenshots/portfolio/14-portfolio-tier-denied.png) | Digital Portfolio | DOC-SCH-PORT-002 | Error | School Coordinator (Bronze) | Digital portfolio creation not in Bronze |
| [portfolio/15-internships-platinum-only.png](screenshots/portfolio/15-internships-platinum-only.png) | Digital Portfolio | DOC-SCH-PORT-004 | Error | School Coordinator (Bronze) | Internship tracking Platinum-only notice |
| [portfolio/16-teacher-adds-skill.png](screenshots/portfolio/16-teacher-adds-skill.png) | Digital Portfolio | DOC-SCH-PORT-002 | Tip | Teacher | "Skill added." by the assigned Teacher |
| [career-counselor/01-dashboard.png](screenshots/career-counselor/01-dashboard.png) | Career Counselor | DOC-SCH-DASH-006 | Dashboard | Career Counselor | Career Counselor dashboard (top) |
| [career-counselor/02-add-record-form.png](screenshots/career-counselor/02-add-record-form.png) | Career Counselor | DOC-SCH-CAR-001 | 2 Fill in | Career Counselor | Add a record (Guidance session, Scheduled) (element shot) |
| [career-counselor/03-record-saved.png](screenshots/career-counselor/03-record-saved.png) | Career Counselor | DOC-SCH-CAR-001 | 3 Saved | Career Counselor | "Record saved." |
| [career-counselor/04-records-table.png](screenshots/career-counselor/04-records-table.png) | Career Counselor | DOC-SCH-CAR-001 | 3 List | Career Counselor | Records table with statuses (element shot) |
| [career-counselor/05-edit-record-follow-up.png](screenshots/career-counselor/05-edit-record-follow-up.png) | Career Counselor | DOC-SCH-CAR-002 | 2 Status | Career Counselor | Edit record: Follow-up Required + Next follow-up (element shot) |
| [career-counselor/06-record-changed-elsewhere.png](screenshots/career-counselor/06-record-changed-elsewhere.png) | Career Counselor | DOC-SCH-CAR-002 | Error | Career Counselor | Changed by someone else + Discard my changes and reload |
| [career-counselor/07-career-preferences-saved.png](screenshots/career-counselor/07-career-preferences-saved.png) | Career Counselor | DOC-SCH-CAR-003 | 2 Saved | Career Counselor | Career preferences saved (element shot) |
| [career-counselor/08-career-goal-form.png](screenshots/career-counselor/08-career-goal-form.png) | Career Counselor | DOC-SCH-CAR-004 | 1 Form | Career Counselor | Career goal input in the 360° view |
| [career-counselor/09-career-goal-saved.png](screenshots/career-counselor/09-career-goal-saved.png) | Career Counselor | DOC-SCH-CAR-004 | 2 Saved | Career Counselor | "Career goal saved." (card not yet refreshed) |
| [career-counselor/09b-career-goal-after-reload.png](screenshots/career-counselor/09b-career-goal-after-reload.png) | Career Counselor | DOC-SCH-CAR-004 | 3 Reload | Career Counselor | Goal shown after reload |
| [career-counselor/10-skills-batches.png](screenshots/career-counselor/10-skills-batches.png) | Career Counselor | DOC-SCH-CAR-005 | 1 List | Career Counselor | Skills batches (no batches yet) + filters |
| [career-counselor/11-create-batch-form.png](screenshots/career-counselor/11-create-batch-form.png) | Career Counselor | DOC-SCH-CAR-005 | 2 Create | Career Counselor | Create a batch (element shot) |
| [career-counselor/12-batch-header.png](screenshots/career-counselor/12-batch-header.png) | Career Counselor | DOC-SCH-CAR-005 | 3 Created | Career Counselor | New batch page |
| [career-counselor/13-enrol-students.png](screenshots/career-counselor/13-enrol-students.png) | Career Counselor | DOC-SCH-CAR-007 | 1 Enrol | Career Counselor | Enrol students with filter |
| [career-counselor/14-certify-confirm.png](screenshots/career-counselor/14-certify-confirm.png) | Career Counselor | DOC-SCH-CAR-007 | 3 Certify | Career Counselor | Certify confirmation |
| [career-counselor/15-enrolment-statuses.png](screenshots/career-counselor/15-enrolment-statuses.png) | Career Counselor | DOC-SCH-CAR-007 | 2 Statuses | Career Counselor | Completed / Certified / Withdrawn / Enrolled (element shot) |
| [career-counselor/16-session-attendance.png](screenshots/career-counselor/16-session-attendance.png) | Career Counselor | DOC-SCH-CAR-008 | 2 Attendance | Career Counselor | Sessions and attendance (element shot) |
| [career-counselor/17-assessment-scores.png](screenshots/career-counselor/17-assessment-scores.png) | Career Counselor | DOC-SCH-CAR-009 | 2 Scores | Career Counselor | Assessments and scores (element shot) |
| [career-counselor/18-batch-closed.png](screenshots/career-counselor/18-batch-closed.png) | Career Counselor | DOC-SCH-CAR-006 | 2 Closed | Career Counselor | Closed batch after reload (read-only notice, Reopen batch) |
| [career-counselor/19-add-funding-case.png](screenshots/career-counselor/19-add-funding-case.png) | Career Counselor | DOC-SCH-CAR-010 | 1 Fill in | Career Counselor | Add a case (Scholarship) (element shot) |
| [career-counselor/20-funding-duplicate.png](screenshots/career-counselor/20-funding-duplicate.png) | Career Counselor | DOC-SCH-CAR-010 | Error | Career Counselor | Already has an open scholarship case |
| [career-counselor/21-update-funding-stage.png](screenshots/career-counselor/21-update-funding-stage.png) | Career Counselor | DOC-SCH-CAR-011 | 2 Stage | Career Counselor | Update case: Counselling (element shot) |
| [career-counselor/22-close-funding-case.png](screenshots/career-counselor/22-close-funding-case.png) | Career Counselor | DOC-SCH-CAR-011 | 3 Close | Career Counselor | Closed + Reason for closing (element shot) |
| [career-counselor/23-funding-open-and-finished.png](screenshots/career-counselor/23-funding-open-and-finished.png) | Career Counselor | DOC-SCH-CAR-011 | 4 Finished | Career Counselor | Open cases + Finished cases |
| [career-counselor/24-empty-portfolio-dashboard.png](screenshots/career-counselor/24-empty-portfolio-dashboard.png) | Career Counselor | DOC-SCH-CAR-001 | Empty | Career Counselor (no schools) | Counselor with no school portfolio: dashboard |
| [career-counselor/25-empty-portfolio-skills.png](screenshots/career-counselor/25-empty-portfolio-skills.png) | Career Counselor | DOC-SCH-CAR-005 | Empty | Career Counselor (no schools) | Counselor with no school portfolio: Skills |
| [psychometric-team/01-dashboard.png](screenshots/psychometric-team/01-dashboard.png) | Psychometric Team | DOC-SCH-DASH-007, PSY-001 | 1 Dashboard | Psychometric Team | Psychometric Team dashboard |
| [psychometric-team/02-assign-assessment-form.png](screenshots/psychometric-team/02-assign-assessment-form.png) | Psychometric Team | DOC-SCH-PSY-001 | 2 Assign | Psychometric Team | Assign an assessment |
| [psychometric-team/03-assessment-assigned.png](screenshots/psychometric-team/03-assessment-assigned.png) | Psychometric Team | DOC-SCH-PSY-001 | 2 Saved | Psychometric Team | "Assessment assigned." |
| [psychometric-team/04-attach-report.png](screenshots/psychometric-team/04-attach-report.png) | Psychometric Team | DOC-SCH-PSY-002 | 1 URL | Psychometric Team | Attach report (Report URL) |
| [psychometric-team/05-results-validation.png](screenshots/psychometric-team/05-results-validation.png) | Psychometric Team | DOC-SCH-PSY-003 | Error | Psychometric Team | "Each item must be 80 characters or fewer." |
| [psychometric-team/06-results-form.png](screenshots/psychometric-team/06-results-form.png) | Psychometric Team | DOC-SCH-PSY-003 | 1 Fill in | Psychometric Team | Results form filled (element shot) |
| [psychometric-team/07-results-saved.png](screenshots/psychometric-team/07-results-saved.png) | Psychometric Team | DOC-SCH-PSY-003 | 2 Saved | Psychometric Team | "Results saved." |
| [psychometric-team/08-bulk-assessments-report.png](screenshots/psychometric-team/08-bulk-assessments-report.png) | Psychometric Team | DOC-SCH-PSY-004 | 2 Result | Psychometric Team | Bulk assessments: 1 added, 1 rejected (report_url) |
| [student-360/01-overview-school-role.png](screenshots/student-360/01-overview-school-role.png) | Student 360° | DOC-SCH-S360-001 | 1 Header | School Coordinator | Overview tab, 16 tabs with counts |
| [student-360/02-examination-results.png](screenshots/student-360/02-examination-results.png) | Student 360° | DOC-SCH-S360-001 | 2 Tab | School Coordinator | Examination Results (Arjun, published) |
| [student-360/03-edusphere-programs.png](screenshots/student-360/03-edusphere-programs.png) | Student 360° | DOC-SCH-S360-001 | 2 Tab | School Coordinator | Edusphere Programs statuses |
| [student-360/04-restricted-tab-service-role.png](screenshots/student-360/04-restricted-tab-service-role.png) | Student 360° | DOC-SCH-S360-001 | Restricted | Academic Team | Restricted Attendance tab |
| [student-360/05-psychometric-tab-psychometric-team.png](screenshots/student-360/05-psychometric-tab-psychometric-team.png) | Student 360° | DOC-SCH-PSY-003, S360-001 | Tab | Psychometric Team | Psychometric Assessment tab with results |
| [student-360/06-mobile-tabs.png](screenshots/student-360/06-mobile-tabs.png) | Student 360° | DOC-SCH-S360-001 | Mobile | School Coordinator | 360° view at **390 × 844** (tabs as a row) |
| [admin-schools/31-school-applications-page.png](screenshots/admin-schools/31-school-applications-page.png) | School administration | DOC-SCH-SADM-006 | 1 Page | Overseas Admin | School-Linked Overseas Applications |
| [admin-schools/32-school-application-form.png](screenshots/admin-schools/32-school-application-form.png) | School administration | DOC-SCH-SADM-006 | 3 Form | Overseas Admin | School → Student → University → Intake (element shot) |
| [admin-schools/33-school-application-started.png](screenshots/admin-schools/33-school-application-started.png) | School administration | DOC-SCH-SADM-006 | 4 Started | Overseas Admin | "Application started for Docs Student Ananya." |
| [admin-schools/34-school-application-tier-denied.png](screenshots/admin-schools/34-school-application-tier-denied.png) | School administration | DOC-SCH-SADM-006 | Error | Overseas Admin | Bronze: Application support not included (element shot) |
| [admin-schools/35-linked-applications.png](screenshots/admin-schools/35-linked-applications.png) | School administration | DOC-SCH-SADM-006 | 4 List | Overseas Admin | Linked applications |
| [admin-schools/36-counselor-school-applications.png](screenshots/admin-schools/36-counselor-school-applications.png) | School administration | DOC-SCH-SADM-006 | Role view | Counselor | Counselor's School Applications (own applications only) |
| [reports/10-global-education-funnel.png](screenshots/reports/10-global-education-funnel.png) | Reports & analytics | DOC-SCH-RPT-006 | 1 Pipeline | School Coordinator | Pipeline funnel + Not tracked yet |
| [reports/11-global-education-students.png](screenshots/reports/11-global-education-students.png) | Reports & analytics | DOC-SCH-RPT-006 | 2 Students | School Coordinator | Students on the pathway |
| [reports/12-global-education-principal.png](screenshots/reports/12-global-education-principal.png) | Reports & analytics | DOC-SCH-RPT-006 | Role view | Principal | Principal's Global education page |
