# rec-035 — Exploratory QA (2026-10-11)

Stack: isolated Docker Compose project `rec035` (web `http://localhost:13335`, api `127.0.0.1:18335`), seeded demo accounts, the shared
pytest rows present. Tool: Playwright (Chromium) script + the `rec-035-management.spec.ts` / `rec-033-performance.spec.ts` e2e specs.

## Scenarios
| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Menu "Management Dashboard" → `/recruiter/manager/business`, 7 tiles, both lists, link marked current | placement_manager | Pass |
| 2 | Refresh; GET form submit (Sep 2026); Back; double submit | placement_manager | Pass |
| 3 | Empty past period (2013-02-01–02): period tiles 0, "No hires in this period yet." | placement_manager | Pass |
| 4 | Invalid input: garbage dates (ignored → this month); > 366 days; future end; start after end → the API's sentence | placement_manager | Pass |
| 5 | Desktop 1366, tablet 820, mobile 375: no horizontal scroll, tiles wrap, lists stack | placement_manager | Pass |
| 6 | "Recruiter Management Dashboard" menu link; every recruiter's scope; 10 categories ranked count ↓ then name | super_admin, it_admin | Pass |
| 7 | Wrong role: page says "Placement manager or administrator role required"; API 403; no menu link | placement_team, hr_team | Pass |
| 8 | Anonymous: redirected to `/admin/login?next=…`; API 401 | — | Pass |
| 9 | Selected / Joined equal rec-033's Total for the same period (MG2) | placement_manager | Pass (e2e) |
| 10 | Console errors, failed (5xx) calls, broken images | all | None |

## Issues
| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA35-01 | Low (UX) | all | `/recruiter/manager/business` | Open the page | The card heading names its content | The card heading "Recruiter business" repeated the page title (the rec-033 QA33-01 pattern) | Fixed: "At a glance" (vitest asserts it); re-verified in the browser |

Note: the super_admin category list is filled with pytest fixture categories (the shared database), not a defect.
