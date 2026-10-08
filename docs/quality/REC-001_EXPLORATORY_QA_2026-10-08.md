# rec-001 exploratory QA — 2026-10-08

## Setup
- Stack: isolated `rec001` (web `:3121`, API `:8121`, SMTP disabled), seeded.
- Browser: isolated Edge 154 over CDP (port 9333, temporary profile). The user's Chrome has remote debugging off. Playwright ran in the
  `web-test` container.
- Roles exercised:
  - `placement_team` (seed recruiter + new ones)
  - `placement_manager` (seed + new)
  - `hr_team`
  - `super_admin`
  - `it_admin`
  - signed out

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Signed-out `/recruiter/dashboard` | → `/it/login?next=%2Frecruiter%2Fdashboard` ✅ |
| 2 | Recruiter signs in at `/it/login` (AC3) | Lands on `/recruiter/dashboard`; sidebar shows Dashboard, Profile + legacy placement screens; profile card shows Employee ID and manager ✅ |
| 3 | Profile: phone `abc<script>` | 422 "Phone may contain only digits, spaces and + - ( )", focus on message, input kept ✅ |
| 4 | Profile: phone with spaces | Saved trimmed, card refreshed; only console entry is the expected 422 from step 3 ✅ |
| 5 | Recruiter opens `/recruiter/manager/team`, `/recruiter/manager`, `/admin/recruiter-staff`, `/it/admin/recruiter-staff` | Access unavailable with the API's reason + "Go to your dashboard" → `/recruiter/dashboard` ✅ |
| 6 | Recruiter on legacy `/it/placement/candidates` | Works; sidebar has "Recruiter Workspace" back link ✅ |
| 7 | `/recruiter`, `/recruiter/manager` | Redirect to the dashboard and the team page ✅ |
| 8 | `hr_team` (AC6, Q-28) | Lands on `/it/hr/dashboard` (unchanged); `/recruiter/dashboard` → "Recruiter role required" ✅ |
| 9 | Placement manager signs in at `/admin/login` (AC4) | Lands on `/recruiter/manager/team`; sees only their direct report ✅ |
| 10 | Super Admin Recruiter Staff: create with a duplicate Employee ID (different case), double-clicked | One POST; "Employee ID already exists"; input kept; focus on message ✅ |
| 11 | Create valid (AC1) | "Recruiter created." + the no-SMTP guidance; list filtered to the new Employee ID (`?q=`) ✅ |
| 12 | "No manager" row (AC5): Edit → Esc | Edit closes, focus back on Edit ✅ |
| 13 | Edit → set Employee ID + manager (keyboard pick) → Save | "Saved Legacy Recruiter.", badge gone, manager shown ✅ |
| 14 | Deactivate / Reactivate | Status flips with a notice ✅ |
| 15 | Refresh with `?q=` | Search kept ✅ |
| 16 | `?q=zzz-nothing`, `?offset=9999` | Empty and past-the-end states ✅ |
| 17 | List + manager APIs blocked (server error) | Both alerts, Create disabled, Retry recovers ✅ |
| 18 | 390 px and 768 px | No horizontal overflow, no broken images; phone rows are labelled cards ✅ |
| 19 | `it_admin` | `/it/admin/recruiter-staff` works, and the nav has the link. The Users form offers `placement_team` and no manager role ✅ |

## Issues
No defect in rec-001 scope.

Observations (no change):
- **OBS-1:**
  - After Deactivate, focus returns to the row's Edit button, not Reactivate. The row re-mounts when the list reloads, so the
    fallback target is used.
  - This is the same behaviour as the telecaller page.
- **OBS-2:**
  - The shell shows both "Profile" (the recruiter page) and the generic "My profile" account link.
  - The telecaller and BDM shells do the same.
- **OBS-3:**
  - `adm-007` e2e failed once in a parallel run on shared seeded data. It passed alone and on the full re-run.
  - This does not come from rec-001: the landing step it checks passed.
- **Tooling note:** a coordinate click on a `SearchableSelect` option in a background CDP tab did not select it. Keyboard selection
  (↓, Enter) and Playwright clicks work.
