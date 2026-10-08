# rec-005 — exploratory browser QA (2026-10-08)

**Stack:** isolated docker compose project `rec005` (web :3105, api :8105), seeded demo data. **Browser:** headless Microsoft Edge driven by
Python Playwright (isolated context per role). **Users:** `placement@` (recruiter), `placement.manager@`, `superadmin@`, `student.it@`,
`hr@`, signed out.

## Pass 1 (before fixes) — 23 checks, 23 pass; one issue found by screenshot review

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | recruiter | `/recruiter/pipeline` (no stage chosen) | Open the board when no open company is in scope | Empty text about the whole pipeline | "No companies at this stage." although no stage was chosen | **Fixed** (vitest first, RED → GREEN) |
| QA-02 | — | recruiter | company detail, two tabs | Tab A moves to Interested; tab B (stale) moves to Meeting Scheduled | Conflict message, stage refreshed | Correct: "This company moved to Interested meanwhile. Check the stage and try again." and the stepper shows Interested. The first QA locator matched Next.js's empty route-announcer `alert` | Not a defect (harness locator fixed) |

## Pass 2 (after fixes) — 25 / 25 pass

Happy path (create → Contacted → Meeting Scheduled), only manual stages offered, Move disabled until chosen, moving back requires a reason
(browser and server), refresh keeps stage and history, Cancel on Mark lost returns focus, double-click on "Yes, mark lost" writes one row,
recruiter gets no Reopen, list Stage column + Lost badge, board via nav + Lost tile, invalid filter message, offset past the end, tablet
(820×1180) and mobile (390×844) without horizontal scroll on detail and board, stale second tab conflict, manager reopen (empty reason
blocked) and no move/lost, manager board shows the team's company, super admin nav entry, signed-out redirect to sign-in, `it_student` and
`hr_team` get "Access unavailable" / no pipeline.

Console / network: no page errors, no 5xx. The only console error is the expected `409` of the deliberate stale-tab conflict.
Broken images: none seen on the screenshots (desktop, tablet, mobile detail and board).
