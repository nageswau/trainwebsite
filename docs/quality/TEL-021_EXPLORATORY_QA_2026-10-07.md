# tel-021 — Exploratory browser QA (2026-10-07)

Stack `tel021` (web :3121, api :8121), isolated Edge (CDP :9321) driven by Browser Use, plus Playwright
`tests/e2e/tel-021-dashboard.spec.ts`. Roles: IT telecaller, telecaller manager, another manager's telecaller.

Checked: happy path (10 tiles, follow-ups, appointments, achieved / target, daily activity today and a past day), zero-activity day
(zeros), future day (API sentence), malformed / impossible dates, refresh (server-rendered, GET form), wrong role and other user
(403 / 404), manager Team → Activity, desktop 1366 / tablet 820 / phone 390 (no sideways scroll; tiles 5 → 2 columns), console errors
(none outside deliberate 403/404/422), API timing (dashboard ≈ 50 ms, activity ≈ 30 ms on QA data).

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Low | Telecaller / dashboard, phone | Open the Daily activity day picker at 390 px | 44 px touch targets (tel-022 QA-06 rule) | Date input 29 px, button 38 px | Fixed (`.tel-day-form` min-height 44 px ≤ 640 px) |
| QA-02 | Medium | Telecaller / `?date=2026-13-45` | Open a well-formed but impossible date | Falls back to today | Panel showed `[object Object]` (FastAPI 422 list detail) | Fixed (`dayParam` checks a real calendar day; vitest + e2e) |
| QA-03 | Medium | Telecaller / `/telecaller/manager/team/<own id>/activity` | Open the manager's page as a telecaller | Refused | Own figures inside the manager shell and nav (no data leak) | Fixed (page refuses non-manager roles; e2e) |
| QA-04 | Low | Manager / `/telecaller/manager/team/not-a-uuid/activity` | Open a malformed id | "Not one of your reports" | `[object Object]` | Fixed (`isUuid` guard; e2e RED → GREEN) |

Not reproduced / not in scope: keyboard key events did not reach the Edge window from the Browser Use harness (a harness focus issue);
keyboard paths were checked through Playwright and DOM focus/submit.
