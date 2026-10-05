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
