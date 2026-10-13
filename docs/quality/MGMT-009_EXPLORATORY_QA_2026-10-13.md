# mgmt-009 — Company profitability (vertical P&L) — exploratory browser QA (2026-10-13)

- **Build:** `feature/mgmt-009`, Docker Compose project `mgmt009` (web `http://localhost:13009`, api `127.0.0.1:18009`), seeded demo data
  plus the rows the backend tests add to the shared stack DB.
- **Tools:** a scripted Playwright (Chromium) exploratory pass (desktop 1366×900, tablet 820×1180, phone 390×844; console errors,
  page errors, failed requests and HTTP 5xx recorded on every page), full-page screenshots reviewed by eye; a second script for the
  fixes on a real loss period (financial year 2021-22); then the Playwright specs `mgmt-009-pnl.spec.ts`, `mgmt-010-expenses.spec.ts`,
  `mgmt-001-command-center.spec.ts`.
- **Roles:** partner (`partner.one`), accountant, super_admin, signed out.

## Issues

### QA-01 — The Net profit tile shows its figure as a small grey caption · Medium
- **Role / page:** partner, `/management/pnl` (every viewport).
- **Steps:** open the P&L; look at the four tiles.
- **Expected:** Net profit reads like Revenue, Expenses and Margin (the large tile figure), red on a loss. **Actual:** the figure was
  13 px grey: it sat in a `<span>` inside the tile's `<strong>`, and the existing `.metric span` rule (the tile caption style) applied.
  No console/network error.
- **Fix:** the loss class goes on the tile's `<strong>` itself (`lossClass()`), no nested span. Test "QA-01: shows the net profit as the
  tile's own figure, red when it is a loss" (RED: `SPAN` ≠ `STRONG`, then GREEN). Re-verified: 22 px like the other tiles,
  `rgb(185, 28, 28)` on −₹21,850.00.

### QA-02 — On a phone the Contribution column is off-screen, and scrolling to it loses the row names · Low (responsive)
- **Role / page:** partner, `/management/pnl?period=year` at 390 px.
- **Steps:** open the P&L on a phone-width window; scroll the table sideways.
- **Expected:** each vertical's contribution can be read beside its name. **Actual:** the table (560 px minimum) scrolled 244 px; the
  first try at a fix (sticky first column) left a ~205 px column that covered Contribution.
- **Fix:** under 640 px the table drops its minimum width, the first column is sticky and 112 px wide (names wrap), cells are tighter.
  Re-verified by measurement after scrolling right: row headers stay at offset 0, the Contribution header spans 165–281 px, right of
  the sticky column (149 px) and inside the 390 px viewport; no page overflow. Screenshot reviewed. (Layout only — not testable in jsdom.)

No other issue was found.

## Checked and passing (after the fixes)

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: Command Center → "Profit & loss" → `/management/pnl`; sidebar entry present for partner and accountant | pass |
| 2 | Six rows in order (Abroad, IT, Recruitment, School projects, Other, Shared (company-wide, not allocated)) + Total; total = Σ rows for revenue, expenses and contribution; contribution = revenue − expenses on every row (e2e) | pass |
| 3 | Period form: August 2026 quarter → "Q2 (July–September) of 2026-27 to date: 01 Jul 2026 to 31 Aug 2026"; year → "Financial year 2026-27 to date"; survives refresh; back returns to the previous period | pass |
| 4 | Invalid inputs: `?month=2999-01` → "Choose this month or an earlier one", form kept, no table; `?month=1999-12` → "Choose January 2000 or a later month"; `?month=abc&period=week`, a repeated `period`, `?month=2026-13` dropped (the default month shown) | pass |
| 5 | Loss edge case (FY 2021-22): Abroad −₹15,000.00, IT −₹2,600.00, Shared −₹4,250.00 and Total −₹21,850.00 red with the minus sign; ₹0.00 rows not red; margin "—" without revenue | pass |
| 6 | Margin over 100% when a reversal makes expenses negative (IT −₹800.00 in October 2026: 102.5%) — correct arithmetic on the ledger's netted figures, as the expense dashboard shows them | pass (by design) |
| 7 | Accountant: same rows, note "University commission is not included: only partners see it."; partner: no note | pass |
| 8 | super_admin: "Access unavailable" + "Finance access required", no "Profit & loss" sidebar entry | pass |
| 9 | Signed out: redirected to `/admin/login?next=%2Fmanagement%2Fpnl` | pass |
| 10 | Duplicate submission (double-click Show): one GET navigation, same URL; read-only page, nothing written | pass |
| 11 | Keyboard: Month → Period → Show in order; the table region is focusable for scrolling | pass |
| 12 | Tablet 820 px: no page overflow, table fits (0 px scroll), tiles whole | pass |
| 13 | Phone 390 px: no page overflow, tiles whole, table scrolls inside its region with the names pinned (QA-02) | pass |
| 14 | Other-currency note: "Automatic lines in another currency are not counted: $300.00 income (1 line)." | pass |
| 15 | Console errors, page errors, failed requests (excluding aborted `_rsc` prefetches), HTTP 5xx: none on any page | pass |
| 16 | Loading: server-rendered page, no client spinner; empty period: status line "No revenue or expenses recorded in …" (vitest) | pass |
| 17 | Playwright: `mgmt-009-pnl.spec.ts` (4), `mgmt-010-expenses.spec.ts` (2), `mgmt-001-command-center.spec.ts` (3) — 9 passed | pass |

Not applicable: success messages (read-only page), broken images (none on the page), cancel (no form state beyond a GET).
