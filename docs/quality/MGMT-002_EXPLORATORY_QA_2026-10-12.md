# mgmt-002 — Management activity — exploratory browser QA (2026-10-12)

- **Build:** `feature/mgmt-002`, Docker Compose project `mgmt002` (web `localhost:13102`, api `127.0.0.1:18102`), seeded (`app.seed`, MA12).
- **Tools:** Playwright (Chromium) scripted exploratory pass + `tests/e2e/mgmt-002-activity.spec.ts`.
- **Roles:** partner (`partner.one`, `partner.two`), accountant, super_admin, it_admin, signed out.
- **Viewports:** desktop 1366×900, tablet 820×1180, mobile 390×844.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: partner lists all kinds; filter by "Done by" + "Kind"; Apply | Pass: URL carries the filters; only matching rows |
| 2 | Invalid inputs: `actor=nope`, `date_from=2026-13-01`, `offset=abc`, `limit=9999` in the address | Pass: dropped by the page (no error, first page shown) |
| 3 | Unknown kind `kind=mgmt.bogus` | Pass: "Unknown activity kind" above the form; Clear filters recovers |
| 4 | `date_to` before `date_from` | Pass: "The end date must be on or after the start date" |
| 5 | Empty state (`date_from=2030-01-01`) | Pass: "No management activity matches these filters." |
| 6 | Paging Next → Back | Pass: "Showing 26–50 of N"; Back returns to page 1 |
| 7 | Refresh | Pass: filters persist (GET form) |
| 8 | Duplicate submission | N/A: read-only GET; repeated Apply is idempotent |
| 9 | Signed out (page and API) | Pass: `/admin/login?next=…` (filters kept in `next`); API `401` |
| 10 | Incorrect role (it_admin) | Pass: "Access unavailable" |
| 11 | Tier: accountant | Pass: kinds = Ledger entry only; investment filter via API → empty |
| 12 | Tier: super_admin | Pass: Task / Plan & target / Decision only; capital filter → none |
| 13 | Desktop / tablet / mobile, all three roles | Pass: no horizontal overflow; filters wrap on mobile |
| 14 | Console errors, 5xx, broken images | None. `net::ERR_ABORTED` on `_rsc` requests are Next.js prefetches cancelled by navigation (app-wide, benign) |
| 15 | Keyboard | Tab order: Done by → Kind → From (date segments) → To → Apply → Clear filters |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | partner | `/management/activity` | Open the list; find "Investment created" | "amount: 500000.00" | "amount: — → 500000.00" | **Fixed** (`describeActivity`, unit + e2e assertion) |
| QA-02 | Info | all | `/management/activity` | Desktop filter row | Labels aligned | Selects and date inputs differ by ~2px (shared `analytics-form` idiom, as telecaller reports) | Not mgmt-002 scope; unchanged |
| QA-03 | Info | all | `/management/activity?kind=mgmt.bogus` | Open | — | Choices empty until Clear filters (data unavailable on a 422; telecaller-reports idiom) | By design |

Note: the shared dev database also holds rows written by the backend test run (actors named "partner xxxx"), so totals exceed the eight
demo entries.
