# Screenshot Index

Agent CRM documentation screenshots. Viewport 1440 × 900, Chromium, light scheme, time zone Asia/Kolkata.
Masked (grey boxes) on every capture: password inputs, the dev-only "Demo accounts" card and the dev-only reset link.
Captured 2026-10-05 against docs commit `717d6aa8` (= `main` @ `6a9be770` + docs) unless a row says otherwise. Capture scripts: `apps/web/tests/doc-capture/`.

| Screenshot | Module | Feature | Step | Role | Description |
|---|---|---|---|---|---|
| account-access/01-login-page.png | Account access | DOC-AUTH-002 | Sign-in page | Visitor | Overseas sign-in page (password field and demo-accounts card masked) |
| account-access/02-login-invalid-credentials.png | Account access | DOC-AUTH-002 | Error | Visitor | "Invalid credentials" |
| account-access/03-login-wrong-portal.png | Account access | DOC-AUTH-002 | Error | Visitor | Wrong-portal message for an IT account |
| account-access/04-register-empty.png | Account access | DOC-AUTH-001 | Open form | Visitor | Create Overseas account, empty |
| account-access/05-register-agent-filled.png | Account access | DOC-AUTH-001 | Fill form | Visitor | Education agent selected, Agency name visible |
| account-access/06-register-duplicate-email.png | Account access | DOC-AUTH-001 | Error | Visitor | "Email already exists" |
| account-access/07-access-unavailable-pending.png | Account access | DOC-AUTH-001/003 | Result | Pending Master | "Agent registration is pending approval" |
| account-access/08-access-unavailable-suspended.png | Account access | DOC-AUTH-003 | Blocked | Suspended Master | "Your agency's account is suspended" |
| account-access/09-forgot-password.png | Account access | DOC-AUTH-004 | Request reset | Master | Reset your password form, email filled |
| account-access/10-forgot-password-sent.png | Account access | DOC-AUTH-004 | Confirmation | Master | Neutral confirmation (dev reset link masked) |
| account-access/11-reset-password-form.png | Account access | DOC-AUTH-004 | New password | Master | Choose a new password |
| account-access/12-reset-password-invalid.png | Account access | DOC-AUTH-004 | Error | Master | "Reset token is invalid or expired" |
| account-access/13-signed-in-sidebar.png | Account access | DOC-AUTH-002 | Signed in | Master | Agent Dashboard with Master sidebar (new agency, zero counts) |
| account-access/14-change-password.png | Account access | DOC-AUTH-005 | Open page | Master | Change your password |
| account-access/15-change-password-wrong-current.png | Account access | DOC-AUTH-005 | Error | Master | "Incorrect current password" |
| account-access/16-change-password-success.png | Account access | DOC-AUTH-005 | Success | Master | "Your password was changed." |
| account-access/17-my-profile.png | Account access | DOC-AUTH-006 | Open page | Master | Your profile + Notifications (full page) |
| account-access/18-my-profile-validation.png | Account access | DOC-AUTH-006 | Error | Master | "String should have at least 2 characters" |
| admin-agencies/01-agent-approvals-pending.png | Agency administration | DOC-ADM-001 | Pending tab | Overseas Admin | Agent Approvals, pending agencies |
| admin-agencies/02-agent-approvals-search.png | Agency administration | DOC-ADM-001 | Search | Overseas Admin | Search "Docs Second" |
| admin-agencies/03-agent-approvals-approved.png | Agency administration | DOC-ADM-001 | Approve | Overseas Admin | "Docs Second Agency approved." on Approved tab |
| admin-agencies/04-agent-approvals-suspend-confirm.png | Agency administration | DOC-ADM-001 | Suspend | Overseas Admin | Suspend confirmation |
| admin-agencies/05-agent-approvals-suspended.png | Agency administration | DOC-ADM-001 | Result | Overseas Admin | Suspended tab |
| admin-agencies/06-agent-approvals-rejected.png | Agency administration | DOC-ADM-001 | Rejected tab | Overseas Admin | Rejected agency listed with Approve |
| account-access/19-deactivated-staff-sign-in.png | Account access | DOC-AUTH-003 | Blocked | Deactivated Staff | Deactivated staff member refused at sign-in: "Invalid credentials" |
| team/01-team-page.png | Team | DOC-TEAM-001 | Open page | Master | Team page: Masters table, Actions, Team card, Staff card (no staff) |
| team/02-invite-master-form.png | Team | DOC-TEAM-001 | Invite | Master | Invite a Master form filled |
| team/03-invite-master-sent.png | Team | DOC-TEAM-001 | Result | Master | "Invite sent." and Invite pending badge |
| team/04-deactivate-master-confirm.png | Team | DOC-TEAM-001 | Deactivate | Master | Deactivate Master confirmation |
| team/05-staff-empty.png | Team | DOC-TEAM-002 | Open card | Master | Staff card, "No staff yet" |
| team/07-add-staff-form.png | Team | DOC-TEAM-002 | Add staff | Master | Add staff form filled |
| team/08-add-staff-success.png | Team | DOC-TEAM-002 | Result | Master | "EDU-S001 created. A set-password link was emailed…" |
| team/09-permissions-form.png | Team | DOC-TEAM-004 | Permissions | Master | "What Bala Verifier can do" with Verify documents ticked |
| team/10-permissions-saved.png | Team | DOC-TEAM-004 | Result | Master | "permissions saved", summary "Can verify documents" |
| team/11-edit-staff.png | Team | DOC-TEAM-003 | Edit | Master | Edit staff form |
| team/12-reset-confirm.png | Team | DOC-TEAM-003 | Reset | Master | Reset confirmation |
| team/13-deactivate-staff-confirm.png | Team | DOC-TEAM-003 | Deactivate | Master | Deactivate staff confirmation |
| team/14-staff-deactivated.png | Team | DOC-TEAM-003 | Result | Master | Deactivated badge and Reactivate button |
| team/15-staff-list.png | Team | DOC-TEAM-002 | Staff list | Master | Staff rows with badges and permission summaries |
| team/16-staff-sidebar-default.png | Team | DOC-TEAM-004 | Staff view | Staff (no permissions) | Staff sidebar: My Students, no Reports/Team/Commissions |
| team/17-staff-team-refused.png | Team | DOC-TEAM-001 | Refusal | Staff | "Only an agency Master can open this page" |
| team/18-staff-sidebar-with-reports.png | Team | DOC-TEAM-004 | Staff view | Staff (View reports) | Staff sidebar with Reports |
| team/19-staff-activity.png | Team | DOC-TEAM-005 | Activity | Master | "Created a student record · Kiran Kumar" |
| team/20-staff-activity-empty.png | Team | DOC-TEAM-005 | Empty | Master | "No activity yet." |
| admin-agencies/07-users-resend-link.png | Agency administration | DOC-ADM-008 | Find account | Overseas Admin | Users > Manage users, Re-send link on an awaiting-setup staff row |
| admin-agencies/08-users-resend-result.png | Agency administration | DOC-ADM-008 | Result | Overseas Admin | "New link created for Esha Pending…" |
| students/01-students-list-master.png | Students | DOC-STU-001 | List | Master | All students cards, search, Show archived, Assigned to, Add student |
| students/02-students-list-staff.png | Students | DOC-STU-001 | List | Staff | Staff list: assigned students only, no Archive/Assign |
| students/03-add-student-form.png | Students | DOC-STU-002 | Fill form | Master | Add student form filled (full page) |
| students/04-add-student-validation.png | Students | DOC-STU-002 | Error | Master | Email/phone/graduation year validation |
| students/05-add-student-duplicate.png | Students | DOC-STU-002 | Duplicate | Master | Possible duplicate warning with Save anyway / Go back |
| students/06-add-student-success.png | Students | DOC-STU-002 | Result | Master | "Neha Sharma added." |
| students/07-students-no-match.png | Students | DOC-STU-001 | Search | Master | "No students match." + Clear filters |
| students/08-students-pagination.png | Students | DOC-STU-001 | Paging | Master | Showing 1–20 of 24, Previous/Next |
| students/09-student-detail.png | Students | DOC-STU-003 | View | Master | Student record (no login) with Journey/Counseling/Shortlist |
| students/10-student-edit.png | Students | DOC-STU-003 | Edit | Master | Edit Neha Sharma form |
| students/11-student-with-login.png | Students | DOC-STU-003 | View | Master | Student with a login: no Edit |
| students/12-archive-confirm.png | Students | DOC-STU-004 | Archive | Master | Confirm archive |
| students/13-archived-shown.png | Students | DOC-STU-004 | Result | Master | Show archived: Archived badge + Unarchive |
| students/14-assign-control.png | Students | DOC-STU-005 | Assign | Master | Assign to list |
| students/15-assign-success.png | Students | DOC-STU-005 | Result | Master | "assigned to EDU-S001 · Asha Staff." |
| students/16-counseling-form.png | Students | DOC-STU-006 | Form | Master | Record counseling form filled |
| students/17-counseling-budget-error.png | Students | DOC-STU-006 | Error | Master | Budget decimal format error |
| students/18-counseling-saved.png | Students | DOC-STU-006 | Result | Master | Counseling saved view |
| students/19-shortlist-form.png | Students | DOC-STU-007 | Form | Master | Add a university: catalogue university + course |
| students/20-shortlist-cards.png | Students | DOC-STU-007 | List | Master | Shortlist cards incl. Agency badge |
| students/21-shortlist-remove-confirm.png | Students | DOC-STU-007 | Remove | Master | Confirm remove |
| students/22-journey.png | Students | DOC-STU-008 | Journey | Master | Journey: Create/Counseling/Shortlist Done |
| students/23-history.png | Students | DOC-STU-008 | History | Master | History list with event labels |
| students/24-link-student-picker.png | Students | DOC-STU-009 | Find | Master | Link student suggestion "Farah Ali — d***@example.test" |
| students/25-link-student-result.png | Students | DOC-STU-009 | Result | Master | "Student linked." |
| students/26-link-student-already-linked.png | Students | DOC-STU-009 | Error | Master | Already-linked student not offered: "Choose a student from the list." |
| universities/01-universities-empty.png | Universities | DOC-UNI-001 | Open | Master | No universities yet |
| universities/02-university-validation.png | Universities | DOC-UNI-001 | Error | Master | "Name is required." |
| universities/03-university-form.png | Universities | DOC-UNI-001 | Form | Master | Add university form filled |
| universities/04-universities-list.png | Universities | DOC-UNI-001 | List | Master | Two agency universities |
| universities/05-universities-staff.png | Universities | DOC-UNI-001 | Staff view | Staff | No Add/Edit/Delete |
| universities/06-university-delete-confirm.png | Universities | DOC-UNI-001 | Delete | Master | Confirm delete |
| universities/07-university-in-use.png | Universities | DOC-UNI-001 | Error | Master | "This university is on 1 shortlist entry…" |
