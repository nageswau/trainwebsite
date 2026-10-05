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
| applications/01-applications-page.png | Applications | DOC-APP-001 | Open | Master | Applications page: Create application form + list |
| applications/02-create-form.png | Applications | DOC-APP-002 | Fill form | Master | Create application form filled |
| applications/03-create-future-date.png | Applications | DOC-APP-002 | Error | Master | Browser blocks future Submitted on date |
| applications/04-create-success.png | Applications | DOC-APP-002 | Result | Master | "Application created." |
| applications/05-create-duplicate.png | Applications | DOC-APP-002 | Error | Master | "An application for this university/course already exists" |
| applications/06-list-all.png | Applications | DOC-APP-001 | List | Master | All applications cards with stage badges and deadlines |
| applications/07-filter-draft.png | Applications | DOC-APP-001 | Filter | Master | Draft view |
| applications/07-filter-submitted.png | Applications | DOC-APP-001 | Filter | Master | Submitted view |
| applications/07-filter-offer.png | Applications | DOC-APP-001 | Filter | Master | Offer received view |
| applications/07-filter-visa.png | Applications | DOC-APP-001 | Filter | Master | Visa view |
| applications/07-filter-withdrawn.png | Applications | DOC-APP-001 | Filter | Master | Withdrawn view |
| applications/08-filter-empty.png | Applications | DOC-APP-001 | Empty | Master | Enrolled view empty: Show all applications |
| applications/09-edit-form.png | Applications | DOC-APP-003 | Edit | Master | Edit form with university note |
| applications/10-application-detail.png | Applications | DOC-APP-004 | Detail | Master | Detail after Saved. |
| applications/11-change-status.png | Applications | DOC-APP-005 | Change status | Master | Move to Offer with note |
| applications/12-withdraw-confirm.png | Applications | DOC-APP-005 | Withdraw | Master | Withdraw confirmation |
| applications/13-withdrawn-read-only.png | Applications | DOC-APP-004/005 | Result | Master | Withdrawn, read-only note |
| applications/14-staff-applications.png | Applications | DOC-APP-001 | Staff view | Staff | Assigned students' applications only |
| tasks/01-tasks-open.png | Tasks | DOC-TASK-001 | Open view | Master | Open tasks |
| tasks/02-new-task-form.png | Tasks | DOC-TASK-002 | Form | Master | New task form filled |
| tasks/03-task-validation.png | Tasks | DOC-TASK-002 | Error | Master | Student/Title/Due validation |
| tasks/04-new-task-past-due.png | Tasks | DOC-TASK-002 | Hint | Master | "This time has passed…" hint |
| tasks/05-tasks-overdue.png | Tasks | DOC-TASK-001 | Overdue view | Master | Overdue badge |
| tasks/06-cancel-task-confirm.png | Tasks | DOC-TASK-002 | Cancel | Master | Confirm cancel |
| tasks/07-tasks-done.png | Tasks | DOC-TASK-001 | Done view | Master | Done task with Completed by |
| tasks/08-tasks-cancelled.png | Tasks | DOC-TASK-001 | Cancelled view | Master | Cancelled task |
| tasks/09-tasks-all.png | Tasks | DOC-TASK-001 | All view | Master | All tasks with every badge |
| tasks/10-staff-tasks.png | Tasks | DOC-TASK-001 | Staff view | Staff | Staff sees assigned students' tasks |
| applications/20-offer-conditions-required.png | Applications | DOC-APP-006 | Error | Master | Conditional offer without conditions: browser "Please fill out this field." |
| applications/21-offer-form.png | Applications | DOC-APP-006 | Form | Master | Offer form: conditional, dates, conditions, offer letter |
| applications/22-offer-saved.png | Applications | DOC-APP-006 | Result | Master | "Offer saved." |
| applications/23-deposit-amount-error.png | Applications | DOC-APP-007 | Error | Master | "The amount must be more than ₹0" |
| applications/24-deposit-form.png | Applications | DOC-APP-007 | Form | Master | Deposit required Yes, amount, due date |
| applications/25-deposit-awaiting-payment.png | Applications | DOC-APP-007 | Result | Master | Awaiting payment + Pay deposit |
| applications/26-razorpay-checkout.png | Applications | DOC-APP-007 | Pay | Master | Razorpay test checkout window (Test Mode ribbon) |
| applications/28-deposit-paid.png | Applications | DOC-APP-007 | Paid | Master | Paid, Paid on, Paid by, Download receipt (paid via signed test webhook) |
| applications/29-visa-start-form.png | Applications | DOC-APP-008 | Start | Master | Start visa case form with checklist |
| applications/30-visa-checklist.png | Applications | DOC-APP-008 | Checklist | Master | Visa case started, checklist statuses |
| applications/31-visa-checklist-gate.png | Applications | DOC-APP-008 | Error | Master | "Cannot advance past the checklist stage -- not yet verified: English test." |
| applications/32-visa-skip-confirm.png | Applications | DOC-APP-008 | Move | Master | Skip-stages confirmation |
| applications/33-visa-decision-confirm.png | Applications | DOC-APP-008 | Decision | Master | Record decision confirmation |
| applications/34-visa-decision-recorded.png | Applications | DOC-APP-008 | Result | Master | Decision Approved + disclaimer |
| applications/35-enrollment-form.png | Applications | DOC-APP-009 | Form | Master | Enrollment form |
| applications/36-enrollment-confirm.png | Applications | DOC-APP-009 | Confirm | Master | Confirm enrollment prompt |
| applications/37-enrolled.png | Applications | DOC-APP-009 | Result | Master | Enrollment details + status history |
| applications/38-filter-enrolled.png | Applications | DOC-APP-001/009 | Filter | Master | Enrolled view with Birmingham application |
| applications/39-enrollment-staff-note.png | Applications | DOC-APP-009 | Staff view | Staff | "An agency Master confirms enrollment." |
| documents/01-documents-pending.png | Documents | DOC-DOC-001 | Pending | Master | Pending review list |
| documents/02-documents-uploaded.png | Documents | DOC-DOC-001 | Uploaded | Master | Uploaded documents view |
| documents/03-upload-form.png | Documents | DOC-DOC-002 | Form | Master | Upload form: Other + description + application |
| documents/04-upload-other-description.png | Documents | DOC-DOC-002 | Error | Master | Other without Description: browser message |
| documents/05-upload-success.png | Documents | DOC-DOC-002 | Result | Master | "Document uploaded. It is waiting for review." |
| documents/06-upload-wrong-type.png | Documents | DOC-DOC-002 | Error | Master | "Upload a PDF, JPEG or PNG file" |
| documents/07-review-form-master.png | Documents | DOC-DOC-004 | Review | Master | Decision Rejected + reason |
| documents/08-review-reason-required.png | Documents | DOC-DOC-004 | Error | Master | Reason required (browser message) |
| documents/09-replace-file.png | Documents | DOC-DOC-003 | Replace | Master | New file chooser |
| documents/10-replace-success.png | Documents | DOC-DOC-003 | Result | Master | "new file uploaded, waiting for review." |
| documents/11-document-history.png | Documents | DOC-DOC-005 | History | Master | Uploaded / Rejected / Downloaded / File replaced |
| documents/12-request-form.png | Documents | DOC-DOC-006 | Form | Master | Request a document form |
| documents/13-additional-requests.png | Documents | DOC-DOC-006 | List | Master | Additional documents (open requests) |
| documents/14-request-cancelled.png | Documents | DOC-DOC-006 | Cancel | Master | "Request for LOR from Neha Sharma cancelled." |
| documents/15-review-staff-verify.png | Documents | DOC-DOC-004 | Staff verify | Staff (Verify documents) | Mark verified button |
| documents/16-staff-no-verify.png | Documents | DOC-DOC-004 | Staff view | Staff (no permission) | No Review button |
