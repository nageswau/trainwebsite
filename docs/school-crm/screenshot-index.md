# School CRM — Screenshot Index

Captured with Playwright (Chromium), viewport **1440 × 900** unless noted, light theme, locale en-IN, timezone Asia/Kolkata.
Files live under `docs/school-crm/screenshots/<module>/`. Element shots capture one card only (the viewport is grown
so the whole card fits); they are marked "(element shot)".

| Capture run | Stack | Date |
|---|---|---|
| S2 — `apps/web/tests/doc-capture/school/sch-s2-admin.capture.ts` | `schooldocs` from `main` @ `ce1f07c2` (+ docs commits), web :3020 | 2026-10-05 |

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
