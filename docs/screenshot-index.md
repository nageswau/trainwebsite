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
