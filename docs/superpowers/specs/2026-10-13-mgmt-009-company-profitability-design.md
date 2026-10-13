# mgmt-009 — Company profitability (vertical P&L) — design

**Status:** design for `feature/mgmt-009` (2026-10-13). Every PL answer below is a **recommended default, `UNVERIFIED`**, taken on the
owner's standing instruction to proceed with recommended answers. Registered as `DEC-SCOPE-205` (provisional numbering).

## Evidence

- `EVID-017` §7 "Company profitability dashboard" (lines 283–296, `DERIVED_BLUEPRINT`): a Business Vertical P&L — Abroad Education, IT
  Training, Recruitment rows, Revenue / Expenses / Contribution columns, a TOTAL row — "which business is actually making money".
- Backlog `MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-009: + School/Other per §22; shared costs per Q-04 ("a separate
  Shared/Unallocated row if not allocated"); month, quarter or year; finance tier; `GET /management/pnl`; no migration.
  AC: total row = sum of the rows; contribution = revenue − expenses; a negative contribution is shown in red.
- `DEC-SCOPE-186` M3/M13 (`EXPLICIT_APPROVAL`): university commission is the partners'; finance tier = partner + accountant.
- `DEC-SCOPE-192` (mgmt-005 `ledger.lines()`), `DEC-SCOPE-195` ME4/ME9 (Indian financial year, month validation),
  `DEC-SCOPE-198` MR6/MR7 (shared costs unallocated on vertical pages; commission partner-only).

## Decisions (PL1–PL12)

| # | Point | Answer |
|---|---|---|
| PL1 | Period | `month` (`YYYY-MM`, IST, default this month; January 2000 to this month, else 422 as ME9) and `period` = `month` (default), `quarter` or `year`. Quarter = the Indian financial-year quarter (Apr–Jun, Jul–Sep, Oct–Dec, Jan–Mar) from its first day to the end of `month`; year = the financial year to the end of `month` |
| PL2 | Lines | Counted `ledger.lines()` rows only: approved manual entries (reversals negative) + rupee automatic lines (payments, agent commissions, trips, recruiter payments, university commission, salaries) |
| PL3 | Rows | One row per ledger vertical, always listed in this order: Abroad Education, IT Training, Recruitment, School projects, Other — then the Shared row (PL4) |
| PL4 | Shared costs (Q-04, second half) | Not allocated. The `shared` vertical (salaries, shared manual entries, shared trips) is its own row "Shared (company-wide, not allocated)". Allocation by % or manual split stays open (Q-04) |
| PL5 | Figures | Per row: revenue = Σ income, expenses = Σ expense, contribution = revenue − expenses, margin = contribution ÷ revenue × 100 (1 dp; `null` when revenue ≤ 0) |
| PL6 | Total (AC) | Σ of all six rows for revenue, expenses and contribution (= net profit); margin as PL5. Net profit and margin are what mgmt-013/015/030/032 read |
| PL7 | University commission (M3, MR7) | Partners only. For the accountant the receipts are never fetched (excluded in SQL), so Abroad revenue and the total leave it out; `commission_visible` says which |
| PL8 | Other currencies | Not counted; per currency and kind in `not_counted` (commission excluded for the accountant here too) |
| PL9 | Negative contribution (AC) | Shown in red (`.pnl-loss`) with the minus sign kept, so colour is never the only cue |
| PL10 | Access | Finance tier (partner, accountant). `super_admin` 403 "Finance access required"; other roles 403 "Management access required"; signed out 401 |
| PL11 | Navigation | Command Center Finance entry "Profit & loss" goes live at `/management/pnl` |
| PL12 | Privacy | Totals only; no names, no line items |

## Design

- **Backend:** new `services/management_pnl.py` — `dashboard(db, user, month_start, period)`: one grouped query
  `select(vertical, kind, sum(signed_amount)) … where counted, start <= entry_date < end [, source != 'university_commission']`, plus the
  not-counted query. `management_it_revenue.period_range` gains the `quarter` branch (backward compatible: its routes accept month/year
  only). `schemas.py`: `PnlFigures`, `PnlRow`, `PnlOut`. `api/management.py`: `GET /management/pnl` (`ledger.require_finance`,
  `_past_month`). No migration.
- **Web:** `lib/managementPnl.ts` (types, query parsing, URL), `components/ManagementPnl.tsx` (period GET form, tiles for revenue /
  expenses / net profit / margin, the P&L table with the total in `<tfoot>`, notes), `app/management/pnl/page.tsx` (server page, access
  card on 401/403, 422 message), `lib/management.ts` (live href), `globals.css` (`.pnl-loss`).
- **States:** API error → `.form-error` alert, form still shown; all-zero period → empty status line above a still-rendered table of
  zeroes (the six rows are the answer); loading is server-rendered.

## Alternatives rejected

- Stitching the three revenue dashboards + the expense dashboard: four reads, different shapes, no School/Other, reconciliation risk.
- Allocating shared costs: Q-04 unanswered.

## Tests

- Backend `tests/test_mgmt_009_pnl.py`: access matrix; validation (bad month, future month, bad period); default month; quarter and
  year ranges; deltas per vertical for income / expense / reversal / unapproved entry; shared row; total = Σ rows; contribution and
  margin; commission partner-only; other currency not counted.
- Web `tests/lib/managementPnl.test.ts`, `tests/components/ManagementPnl.test.tsx`; e2e `tests/e2e/mgmt-009-pnl.spec.ts`.

## Regression risks

- `period_range` is shared by mgmt-007/008 — month/year behaviour unchanged, covered by their tests.
- Nav: one entry gains an `href`; pinned nav tests checked.
