# bdm-023 — Management dashboard: browser QA (2026-10-07)

**Stack:** isolated Docker Compose project `bdm023` (web `http://localhost:13023`, API `127.0.0.1:18023`), built from
`worktree-bdm-023`. **Browser:** Browser Use is not installed in this environment; an isolated Playwright Chromium (headless) drove
the app. **Data:** demo seed + a QA team (manager, three BDMs of each type, an empty manager) created through the API, with rows
back-dated in SQL for alerts that need time to pass (overdue follow-ups, past meetings without a report, an MoU waiting 8 days, a
missing daily report). Screenshots were kept out of the repository.

## Pass 1 — independent exploratory QA (no code changes)

| # | Check | Result |
|---|---|---|
| 1 | Happy path (manager) | 8 tiles in source order with definitions; alerts AL-1 (3), AL-2 (1), AL-3 (12), AL-4 (1), AL-6 (2), AL-7 (3) match the seeded data exactly |
| 2 | Invalid input | `?manager=abc`, `?manager=<script>` ignored (all teams); a manager's `?manager=` ignored by the page, API `422` |
| 3 | Empty state | Manager with no BDMs: "No BDMs report to you yet.", all tiles 0, "No alerts right now." |
| 4 | Server error | Unknown manager id (API `404`): inline "Unable to load the dashboard." with "Try again" — see QA23-02 |
| 5 | Loading | `loading.tsx` skeleton shows while the server renders |
| 6–7 | Back / refresh | Alert link → record → Back returns to the dashboard; reload renders it again |
| 8 | Duplicate submission | Not applicable (read-only page; the super_admin filter is an idempotent GET form) |
| 9–10 | Unauthorized / wrong role | Signed out → `/admin/login?next=/bdm/manager/dashboard`; BDM → "Access unavailable — BDM manager role required" |
| 11–13 | Desktop / tablet / mobile | 1280 / 768 / 375 px: no horizontal overflow; tiles reflow to one column on a phone |
| 14 | Navigation | Every alert item and "View all" link (17 distinct) opened a real page (HTTP 200, no not-found text); super_admin's "BDM Dashboard" sidebar entry works |
| 15–16 | Messages | Status words "Attention" / "Urgent" / "Done" beside the colour; "Showing 10 of 12." |
| 17 | Broken images | None |
| 18–19 | Console / network | No console errors, no page errors, no failed API calls. Only aborted `_rsc` prefetches on navigation (Next.js behaviour) |
| 20 | Unexpected redirects | None |
| — | Keyboard | Tab order: sidebar → "View team" → each alert link in order → "View all" |

### Issues found

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA23-01 | Low | bdm_manager | `/bdm/manager/dashboard` | 12 follow-ups due the same day → open the dashboard | A stable, sensible order | Listed in random order (`Call back 6, 11, 2, …`) — the tie-break was the UUID | **Fixed** test-first: ties by creation time (`test_alerts_due_the_same_day_keep_the_order_they_were_created`); appointments tie by code. Browser: `Call back 0 … 9` |
| QA23-02 | Low | super_admin | `/bdm/manager/dashboard?manager=<unknown id>` | Open an old / wrong manager link | A way back | Only "Try again", which repeats the same failure | **Fixed** test-first: a "Show all teams" link (`BdmManagerDashboardPage.test.tsx`); browser: the link opens "All BDM teams" |

Not defects: the first pass captured the loading skeleton for the BDM-refusal and reload checks (script timing); re-checked with
waits — both render correctly. The skeleton uses the manager sidebar for every role, as the other manager pages' `loading.tsx` do.

## Pass 2 — after fixes

Rebuilt `api` + `web`; QA23-01 and QA23-02 re-checked in the browser (above). Playwright `bdm-023-manager-dashboard`, `bdm-014-my-day`,
`bdm-016-targets`: 3 passed.
