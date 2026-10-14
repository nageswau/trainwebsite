# mgmt-030 — Business health score: exploratory QA (2026-10-14)

**Build:** `feature/mgmt-030`, Docker Compose stack `mgmt030` (web `http://localhost:13037`, api `127.0.0.1:18030`), seeded demo
accounts, shared test DB. Browser: Playwright Chromium (headless). Widths: 1366, 820 and 375 for the whole page, and 360 and 320 to
measure the breakdown. Roles: `partner.one@`, `superadmin@`, `accountant@`, `itadmin@`, signed out. Script: 36 scripted checks plus a
visual review of each screenshot.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | The partner opens Command Center → Business Intelligence → Business health score | The default month is the last complete month ("September 2026 compared with August 2026"). The overall tile reads "Overall business health 56/100 Amber". There are 12 RAG lines in §30 order and a 12-row breakdown |
| 2 | The breakdown recomputes the overall score (AC) | Σ points over the available factors = the footer score (56 = 56), on the page and in pytest `assert_recomputes` |
| 3 | super_admin opens it from "Management business health" | "Operational health". Six factors (Sales pipeline … University partnerships). No ₹, margin, ROI or revenue wording. The API returns 6 factors, all `tier: operational` |
| 4 | The accountant and it_admin open the URL | "Access unavailable" card; the API returns `403` |
| 5 | Signed out | Redirects to `/admin/login?next=%2Fmanagement%2Fhealth` |
| 6 | `?month=2026-13` (malformed) | Dropped; the default month is shown with no error |
| 7 | `?month=2999-01` / `?month=1999-12` | The API's words in `.form-error`: "Choose this month or an earlier one" / "Choose January 2000 or a later month" |
| 8 | The current month | The note "… is still running: it is scored so far, against the whole of …" |
| 9 | `?month=2000-01` (no data) | `role=status` "Not enough data to score January 2000.". Every factor says why it is not available |
| 10 | Double-click Show; Back; Forward; Reload | One navigation (read-only GET). The month input follows the address through Back, Forward and Reload |
| 11 | Keyboard | Month input (native month and year stops) → Show → the focusable breakdown region |
| 12 | Desktop / tablet / phone | No horizontal page scroll at 1366, 820 or 375. The breakdown fits its region at 375, 360 and 320 (stacked rows below 640px) |
| 13 | Console, 5xx responses, failed requests, broken images | None |

## Issues found and fixed

| ID | Severity | Role | Page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|---|
| QA30-01 | Low | super_admin | `/management/health` | Read the scoring note under the breakdown | Only the scales of the factors shown (BH1: no finance information for super_admin) | The note explained the Profit margin, Marketing ROI and Expenses-vs-revenue scales | The finance sentence renders for the business scope only; component test + e2e assert no margin/ROI/revenue wording |
| QA30-02 | Medium | all | same | Open the page at 375px | Score, Weight and Points (the AC arithmetic) visible | A six-column table clipped by 94px inside its scroll region. Pixel trimming still clipped at 360 / 320 | The Status column is merged into Score (the band beside the score), and the shared `.table.stack` pattern stacks each factor as labelled lines below 640px. Measured 0px clipped at 375 / 360 / 320 |
| QA30-03 | Low | all | same, phone | A long measure on a stacked row | The "Measure" label on one line | "Measu re" broke beside a long measure | `td::before { flex-shrink: 0 }` for this table |
| QA30-04 | Low | all | same, phone | Read a scored factor | The score and its band together | Flex pushed the score and the pill apart | The score + pill are one `<span>` |
| QA30-05 | Low | all | same, phone | Read the total | "Overall score 56" | "Overall score … Points 56" | No `data-label` on the footer cell |

Each fix followed the same loop:
1. Updated the component test first and confirmed it failed (RED). QA30-04 and QA30-05 are the exception: their regression assertions
   were added with the change.
2. Made the change (GREEN).
3. Rebuilt the web container.
4. Re-ran the browser script (36/36) and the e2e spec (3/3).

## False positives (not defects)

- Keyboard check: `<input type="month">` has two internal stops (month, year) before Show. That is native Chromium behaviour.
- The first QA script's `networkidle` wait timed out after Forward; a DOM-condition wait shows Forward works.

## Not changed (observed, out of scope)

- In the shared DB most factors are "not available" for September 2026: no ledger, balances, headcount or tagged spend were entered
  for August and September. The pytest suite covers the scored paths with controlled ledger data in far-past months.
