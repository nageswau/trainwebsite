# mgmt-007 — IT Training revenue dashboard — exploratory browser QA (2026-10-13)

- **Build:** branch `worktree-mgmt-007` (pushed as `feature/mgmt-007`), Docker stack `mgmt007` (web `http://localhost:13707`, api
  `127.0.0.1:18707`), isolated Playwright Chromium (desktop 1366×900, tablet 820×1180, mobile 390×844).
- **Data:** `python -m app.seed` plus a QA fixture of the §5 example in August 2026: five courses (Python Full Stack, Data Analytics,
  Java Full Stack, Cloud & DevOps, Digital Marketing), two batches each, 16 August enrolments, one EMI instalment, 27 July enrolments
  paying ₹1,000 in August (paging), an unlinked IT service fee (₹2,500), a USD service fee and a ₹45,000 trainer cost tagged to a batch.
- **Roles:** accountant, partner, super_admin, it_admin, signed out.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path (accountant, partner): Command Center → IT Training revenue → August 2026 | PASS — Revenue ₹4,79,500 = 1,35,000 + 1,27,000 + 1,05,000 + 80,000 + 30,000 + 2,500 (by hand); costs ₹45,000; 16 new enrolments; every course = Σ its batches |
| 2 | Invalid inputs: future month, `month=abc&period=week&program=nope`, unknown course id | PASS — API 422 shown ("Choose this month or an earlier one"); malformed values dropped to defaults; "Choose a course from the list" under "Payments: the chosen course" |
| 3 | Empty state (January 2000) | PASS — "No IT Training revenue, costs or enrolments in January 2000." |
| 4 | Server error / loading | Unit-tested (page renders the "unavailable" alert; the payments list fails on its own). Server-rendered page: no client loading state |
| 5 | Financial year to date | PASS — "Financial year 2026-27 to date: 01 Apr 2026 to 30 Sept 2026" |
| 6 | Payments drill-down + paging | PASS — 29 payments; "Showing 1–25 of 29", Next → "26–29 of 29"; no student names |
| 7 | Back / refresh | PASS — Back returns to page 1; reload keeps the period and the list |
| 8 | Double submit of the period form | PASS — one navigation, one page |
| 9 | Unauthorised / wrong role | PASS — signed out → `/admin/login?next=…`; super_admin "Finance access required"; it_admin "Management access required" |
| 10 | Layout desktop / tablet / mobile | PASS after fixes — no page-level horizontal overflow (0 px); tables scroll inside their regions |
| 11 | Other currency | PASS — "IT payments in another currency are not counted: $300.00 (1 payment)." |
| 12 | Console errors, failed requests, broken images, redirects | PASS — none at any viewport |

## Issues found and fixed

| ID | Severity | Role / page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|
| QA-01 | Low | accountant, mobile 390 px, `/management/revenue/it?month=2026-08` | Open the page on a phone | Course and batch names readable | The name column was squeezed; "Python Aug Morning" wrapped to three lines | `.it-revenue-courses th[scope=row] { min-width: 170px }` (the table scrolls sideways). Re-run: column 170 px |
| QA-02 | Medium | accountant, all viewports | Click any "Payments" link | The list's heading "Payments: …" visible | The `#payments` jump put the heading under the sticky 68 px top bar | `.it-revenue-payments { scroll-margin-top: 84px }`. Re-run: heading top 84 px on desktop, tablet and mobile |
| QA-03 | Low | accountant, mobile | Open a payment list on a phone | Dates and enrolment codes on one line | "QA7-P14-9cb2" and "24 Aug 2026" broke across two lines | `.it-revenue-nowrap td { white-space: nowrap }`. Re-run: one line |

Open issues: none.
