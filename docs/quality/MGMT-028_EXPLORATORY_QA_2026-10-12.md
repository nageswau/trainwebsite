# mgmt-028 — Exploratory browser QA (2026-10-12)

- **Build:** `feature/mgmt-028`, isolated Docker stack (`-p mgmt028`, web `http://localhost:13028`), migration `0153_management_tasks`,
  seeded demo accounts. Playwright (Chromium) with console / page-error / HTTP ≥ 400 capture and full-page screenshots.
- **Roles:** partner (`partner.one`), trainer (IT portal, task owner), accountant, IT student, signed out; e2e also creates two
  partnership heads through the admin API.

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: partner adds a task due today for a staff owner; owner opens **Management tasks** from their sidebar, completes it; it moves to Completed | Pass (`mgmt-028-tasks.spec.ts`) |
| 2 | Invalid inputs: empty form; past deadline | Pass — "Give the title (2-200 characters)", "Choose the owner", "The deadline can't be in the past"; nothing sent |
| 3 | Empty states | Pass — "No tasks here." / "No management tasks are assigned to you." |
| 4 | Server errors | Pages fall back to "Tasks are unavailable right now" / "Temporarily unavailable" (component tests) |
| 5 | Cancel / back / refresh | Pass — Cancel returns to the Everyone view; back and reload keep `?view=` |
| 6 | Duplicate submission (double click Save) | Pass — one row created |
| 7 | Unauthorized / wrong role | Pass — trainer and accountant on `/management/tasks` see "Access unavailable" (API `403`); signed out → `/admin/login?next=` and "Sign in required" on the staff page |
| 8 | Another staff member | Pass — their list is empty; PATCH on the task → `404` (backend AC3) |
| 9 | Sidebar entries | Pass — trainer has "Management tasks"; accountant has it and no To-do; IT student has none |
| 10 | Unknown / malformed task id on edit | Pass — "Task not found" |
| 11 | Cancel a task | Pass — leaves the bands, listed under Cancelled |
| 12 | Desktop 1366 / tablet 820 / mobile 375 | Pass — no horizontal scroll on the to-do, the form and the staff page |
| 13 | Console errors / failed requests / broken images / unexpected redirects | None recorded |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Low (accessibility) | Partner, `/management/tasks` | Open the to-do | Priority badge identifies itself | Priority and status badges read as bare words side by side ("High Open") | **Fixed** — badge reads "High priority"; test `ManagementTasks.test.tsx`; re-verified in the browser |

No open issues. Note (by design, MT14/mgmt-027): the staff page is the shared `/account/management-tasks` route in the public frame with
"← Back to dashboard", like `/account/management-decisions` and `/account/password`.
