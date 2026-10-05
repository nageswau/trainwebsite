# School CRM — Screenshot Index

Captured with Playwright (Chromium), viewport **1440 × 900** unless noted, light theme, locale en-IN, timezone Asia/Kolkata.
Files live under `docs/school-crm/screenshots/<module>/`. Element shots capture one card only (the viewport is grown
so the whole card fits); they are marked "(element shot)".

| Capture run | Stack | Date |
|---|---|---|
| S2 — `apps/web/tests/doc-capture/school/sch-s2-admin.capture.ts` | `schooldocs` from `main` @ `ce1f07c2` (+ docs commits), web :3020 | 2026-10-05 |
| S3 — `sch-s3-access-team.capture.ts` (after S2 on the same DB) | same | 2026-10-06 |

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
