# mgmt-017 — Training dashboard: exploratory QA (2026-10-13)

**Build:** `feature/mgmt-017` on the isolated stack (`docker compose -p mgmt017`, web `http://localhost:13017`, api `127.0.0.1:18017`),
seeded demo accounts. Headless Chromium (Playwright) driving the real app; console errors, page errors, failed requests, HTTP 5xx and
broken images collected on every page.

## Scenarios

| # | Scenario | Role | Result |
|---|---|---|---|
| QA1 | Command Center → Training: heading, 11 KPI tiles in §12 order, trainer table (Meera Iyer: 1 batch, 1 student, 85.7%, 0.0%, —, —, 42.0%, 0) | partner | Pass |
| QA2 | Period 2026-08-01..31 → URL keeps it; refresh keeps it; Back returns to the default month | partner | Pass |
| QA3 | Reversed period → "The period must start on or before its end"; > 366 days → "The period can be at most 366 days"; garbage params → this month, no error | partner | Pass |
| QA4 | Empty period (June 1900): Attendance "Nothing marked", Completion "No seats taken" (no fabricated 0%) | partner | Pass |
| QA5 | People → Trainers opens `/management/training#trainers` with the table | partner | Pass |
| QA6 | Double-click Show (duplicate submission): one GET, no error | partner | Pass |
| QA7 | Super admin sidebar "Management training figures" → page with KPIs | super_admin | Pass |
| QA8 | `/management/training` → "Access unavailable", no figures | accountant | Pass |
| QA9 | Same, signed in at `/it/login` | trainer, it_admin | Pass |
| QA10 | Signed out → `/admin/login?next=%2Fmanagement%2Ftraining` | — | Pass |
| QA11 | Desktop 1280, tablet 768, phone 375: no sideways page scroll; the table scrolls in its own box | partner | Pass |
| — | Console / page errors, failed requests, 5xx, broken images on every page above | all | None |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA17-01 | Low | partner, super_admin · `/management/training` | Open the page this month | The note's trainer count agrees with the Trainers tile | Note said "13 trainers" while the tile said 10: the note counted inactive accounts too | **Fixed** — the note reads "13 trainer accounts, 3 inactive." (component test + e2e) |

Not an issue: the grey table header behind every column but the first is the shared `.table-scroll` style (identical computed
background on `/management/counseling`).

## Re-check after the fix

`vitest` ManagementTraining + managementTraining 12/12; Playwright `mgmt-017-training.spec.ts` 5/5 (with mgmt-018's 4/4); the scripted
pass above re-run with no failures.
