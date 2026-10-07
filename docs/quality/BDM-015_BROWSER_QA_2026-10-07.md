# bdm-015 — Browser QA (2026-10-07)

- **Build:** `feature/bdm-015`, Docker Compose project `bdm015` (api 127.0.0.1:8115, web 127.0.0.1:3115), seeded with `python -m app.seed`.
- **Tool:** isolated Playwright Chromium (1.62.1). Browser Use is not installed on this machine (as in the earlier BDM sessions); the
  scripted exploratory pass stands in for it until the owner accepts or runs it.
- **Accounts:** one manager with a College, an Agent and a School BDM, each created and activated through the admin API.

## Pass 1 — exploratory (no code changed)

| # | Area | Result |
|---|---|---|
| 1 | Happy path: preview → note → confirm → submit | Pass — notice "Report submitted. This day's activities are now locked.", note shown, Submit gone |
| 2 | Invalid inputs: `?date=2026-02-30`, `?date=2099-01-01` | Pass — today shown with the activities-page note (BDM page and manager grid) |
| 3 | Empty state: new BDMs / no activity | Pass — zeros; days before a profile existed show "—" in the grid |
| 4 | Not tracked | Pass — Agent: 3 tiles "Not tracked" with the reason, never 0; School: the 11 §G labels |
| 5 | Old day (beyond 7 days) | Pass — read-only preview, "Reports can be submitted up to 7 days back" |
| 6 | Cancel / Escape on the confirm | Pass — back to Submit |
| 7 | Refresh / Back | Pass — the submitted snapshot persists; Back returns to the report |
| 8 | Duplicate submission (double click) | Pass — one POST (the button disables while busy) |
| 9 | Unauthorized / wrong role | Pass — BDM on the manager grid and manager on the BDM page: "Access unavailable" with the API reason; unknown BDM id: "BDM not found"; signed out → `/bdm/sign-in?next=…` |
| 10 | XSS in the note | Pass — `<script>` rendered as text |
| 11 | Keyboard | Pass — Enter on Submit focuses "Yes, submit"; Escape cancels |
| 12 | Layout 320 / 375 / 820 / 1366 px | Pass — no horizontal page overflow; the grid scrolls inside `.table-scroll` with the BDM column sticky |
| 13 | Console / failed network | One 422 (QA15-01); no page errors, no 5xx |
| 14 | Activity lock | Pass (e2e) — PATCH of a submitted day's activity `409`; no Edit buttons on `/bdm/activities` |

### Findings

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA15-01 | Low | bdm_manager | `/bdm/manager/daily-reports/{id}` | Type only spaces in "Your comment", Save | Refused in the browser | The form's `required` let spaces through; the API answered 422 "Comment is required" | console: `Failed to load resource … 422` |
| QA15-02 | Low | bdm_manager | `/bdm/manager/daily-reports` at 375 px | Open the grid on a phone | The chosen day in view | Days ran oldest → newest; today was off-screen to the right | screenshot `grid-mobile.png` (scratchpad) |

## Fixes (test-first) and pass 2

- **QA15-01:** a blank comment shows "Write a comment first." with no request — `BdmDailyReport.test.tsx` "a blank comment is refused
  without a request" (failed first, then passed).
- **QA15-02:** grid columns are newest first (API order unchanged) — `BdmDailyReportPages.test.tsx` column-order assertion (failed
  first, then passed); the e2e spec reads today from the first column.
- **Pass 2** on the rebuilt web image: the exploratory script and Playwright `bdm-015-daily-report` + `bdm-009-activities` — 2 passed;
  no console errors, page errors, 5xx or overflow.
