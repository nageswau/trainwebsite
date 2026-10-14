# mgmt-026 — Exploratory browser QA (2026-10-14)

- **Build:** `feature/mgmt-026`, isolated Docker stack (`-p mgmt026`, web `http://localhost:13026`), migration `0159_management_plans`,
  seeded demo accounts. Playwright (Chromium) script with console / page-error / HTTP ≥ 500 capture and full-page screenshots, plus
  `tests/e2e/mgmt-026-plans.spec.ts`.
- **Roles:** partner (`partner.one`), super admin, accountant, trainer (IT portal), signed out.

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: Command Center → Next month plan & targets → plan a month → KPI item (New agents, 30) and free-text item → tick done → Target vs actual row | Pass (e2e) |
| 2 | Invalid inputs: empty item; KPI without target; fractional count target (server `422` placed on Target) | Pass |
| 3 | Empty states: no KPI items, empty verticals, every month planned | Pass (component tests + browser) |
| 4 | Server errors | Pages fall back to "… unavailable right now" (page code paths; component tests for read errors) |
| 5 | Cancel / back / refresh | Pass — inline edit Cancel; done state persists after reload |
| 6 | Duplicate submission (double click "Plan this month", "Add item") | Pass — one plan, one item |
| 7 | Unauthorized / wrong role | Pass — accountant "Operational management access required"; trainer "Access unavailable"; signed out → `/admin/login?next=` |
| 8 | Revenue KPI (PN7) | Pass — partner sees ₹50,00,000 target; super admin sees neither the item nor the KPI option |
| 9 | Closed plan | Pass — read-only (no add/edit, checkboxes disabled) until reopened |
| 10 | Remove item, create task from item | Pass — removed from table; task created and counted ("1 task") |
| 11 | Malformed / unknown month URL | Pass — "That is not a month." / "There is no plan for January 2999 yet." |
| 12 | Desktop 1366 / tablet 820 / mobile 375 | Pass — no horizontal page scroll; the table scrolls inside its own wrapper |
| 13 | Console errors / failed requests / broken images / redirects | None, except the browser's log line for the deliberate `422` in row 2 (expected) |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Medium | Partner, `/management/plans/{month}` | Tick a free-text item done | Box shows ticked at once | Box snapped back unticked until the refresh arrived (Playwright: "Clicking the checkbox did not change its state") | **Fixed** — optimistic tick held until the refreshed item arrives, reverted on failure; test `ManagementPlanEditor.test.tsx` QA-01; re-verified in the browser and e2e |
| QA-02 | Low | Partner, plan editor | Item with a task | "Free-text item · Done · 1 task" | Doubled spacing before "· 1 task" | **Fixed** — one joined line |
| QA-03 | Low | Partner, Target vs actual | Plan with free-text items | Tally spaced from the table | "Other plan items…" touched the table | **Fixed** — top margin |

No open issues.
