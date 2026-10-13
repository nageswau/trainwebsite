# mgmt-018 — Counseling dashboard: exploratory QA (2026-10-13)

Stack: isolated Docker Compose project `mgmt018` (web `http://localhost:13018`, api `127.0.0.1:18018`), demo seed. Driver: Playwright
(Chromium) with console / network capture; screenshots at 1440 × 900, 820 × 1180 and 375 × 812. Independent pass first, no code changed.

## Checked

| Area | Result |
|---|---|
| Happy path (partner): 7 KPI tiles in §13 order, counselor table, IT / Overseas / All totals, revenue in rupees | Pass |
| Super admin: own sidebar link "Management counseling figures"; Revenue tile "Partners only"; no Revenue column | Pass |
| Accountant: "Access unavailable"; signed out → `/admin/login?next=/management/counseling` | Pass |
| Invalid inputs: impossible date / garbage in the address → this month; start after end → "The period must start on or before its end"; > 366 days → "The period can be at most 366 days" | Pass |
| Refresh / back keep the period (GET form, address carries it); Show twice is idempotent (read-only) | Pass |
| Command Center: Students "Counseling" and People "Counselors" (`#counselors`) entries live | Pass |
| Desktop / tablet / phone: page never scrolls sideways (`scrollWidth - innerWidth = 0`); table scrolls in its focusable region (tabindex 0) with a sticky name column | Pass |
| Console errors / failed API calls for partner, super admin, accountant | None |
| Load time (server render) | 0.7–1.2 s |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | partner, super admin | `/management/counseling` | Open the page; read the Calls tile | The note explains why calls are not tracked | The tile says "Not tracked" and its note starts "Not tracked:" again | `partner-desktop.png` |
| QA-02 | Low | partner, super admin | `/management/counseling` | Read the table footer at any width | "21 counselors" on one line | The count wraps onto two lines ("21 / counselors"), making the footer rows taller | `partner-desktop.png`, `superadmin-phone.png` |

Not mgmt-018 defects (recorded, not fixed): the demo counselor cannot sign in through `/admin/login` (403, a staff portal rule); the
counselor's refusal of this route is covered by the API test (403 "Management access required"). Counselors in a "Global" division come
from shared-database test rows.

## Fixes (Phase 6)

- QA-01: the Calls definition now reads "Calls are logged by telecallers; counselors have no call log." (API test + component test).
- QA-02: the footer count cell is `no-wrap` (component test). Both re-verified in the browser — see the re-check below.
