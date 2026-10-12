# mgmt-010 — Expense dashboard — design

- **Feature:** `mgmt-010` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-010). Depends on mgmt-004 (PR #246) and mgmt-005 (PR #249),
  both merged on `main@11fe5979`.
- **Evidence:** `EVID-017` §8 "Expense Dashboard" (Expense | Monthly | Annual; rows Rent, Salaries, Marketing, Travel, Trainers,
  Commissions, Technology, Other, Total — `DERIVED_BLUEPRINT`); Management M4/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`); mgmt-004
  `DEC-SCOPE-189` ML1 ("the §22 expense heads … are dashboard groupings for mgmt-010/013, not extra categories"), ML10; mgmt-005
  `DEC-SCOPE-192` MA1–MA11.
- **Decision:** one new DEC-SCOPE (number taken at merge). ME1–ME10 below answer the open "financial-year start per Q-04?" point of the
  backlog item and the row grouping with **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended
  answers.

## 1. Intent

The finance tier sees what the company spent: the §8 table of expense heads with this month's and this year's totals, the categories
behind each head, and the month-by-month totals that add up to the year. Read-only; every figure comes from `services/ledger.lines()`
(approved manual expenses + rupee automatic expense lines). Nothing is stored.

## 2. Decisions (ME1–ME10)

| # | Point | Answer |
|---|---|---|
| ME1 | Rows (§8) | The 8 §8 heads, always all listed in source order: **Rent** ← Office rent; **Salaries** ← Salaries (the manual category, inactive since mgmt-011 SM9, and the automatic salary lines of mgmt-011 SM8); **Marketing** ← Marketing; **Travel** ← Travel (manual category and the automatic BDM trip lines); **Trainers** ← Trainer payments; **Commissions** ← Agent commissions (manual category and the automatic paid-commission lines); **Technology** ← Internet, Software; **Other** ← every other expense category (Utilities, Maintenance, Insurance, Other fixed costs, Events, University expenses, Recruitment expenses, School activities, Student activities) and any category added or renamed later |
| ME2 | Mapping key | The category's current name (manual) or the automatic line's label, matched ignoring case. A renamed seeded category falls into Other (no schema change; the categories table stays unchanged) |
| ME3 | Monthly | The selected month (`YYYY-MM`, IST days), default the current IST month |
| ME4 | Annual (Q-04 FY part) | **Indian financial year to date**: 1 April of the financial year containing the selected month through the end of that month. The month-by-month list covers the same months, so annual = the sum of the months (AC) |
| ME5 | Figures | Approved manual expense entries (a reversal counts negative, ML10) + automatic expense lines in rupees (MA8). Drafts, submitted and rejected entries never count. Income is not read |
| ME6 | Other currencies | Automatic expense lines in another currency in the financial year to date are not counted and are summed per currency in `not_counted` (as MA8); the page shows them as a note |
| ME7 | Categories | A second table lists each category (or automatic label) with money in the financial year to date (one netted to zero by a reversal is left out, browser QA-01), its head, monthly and annual figures, largest annual first |
| ME8 | Bars | Each head gets a horizontal bar of its share of the annual total (non-negative; the percentage is also written out). No chart library |
| ME9 | Validation | `month` must match `YYYY-MM`, be 2000-01 or later and not after the current IST month → else `422` with a message |
| ME10 | Access (M13) | Finance tier only (`ledger.require_finance`): partner and accountant. `super_admin` `403` "Finance access required"; any other role `403`; signed out `401` |

## 3. API

`GET /management/expenses?month=YYYY-MM` → `200`
`{month, year_start, year_label ("2026-27"), groups[{key, label, month, year, share}], categories[{label, group, month, year}],
months[{month, total}], totals{month, year}, not_counted[{currency, amount, count}]}`. Amounts are decimal strings (2 places).
`share` is the head's percentage of the annual total (0 when the total is not positive), rounded to one place.

## 4. Components

- `services/management_expenses.py` (new): `HEADS`, `head_of(label)`, `financial_year_start(month_start)`, `dashboard(db, month_start)`.
  One grouped query over `ledger.lines()` (kind expense, counted, FY start ≤ day < month end) by label and month; one for `not_counted`.
  `services/ledger.py` is unchanged (frozen after mgmt-005).
- `api/management.py`: the route; `schemas.py`: `ExpenseDashboardOut` and its rows.
- Web: `lib/managementExpenses.ts` (types, `expenseMonth` param check, URLs); `components/ManagementExpenses.tsx` (month form, heads
  table with bars, total row, categories table, month-by-month table, not-counted note, empty note, ledger link);
  page `app/management/expenses/page.tsx`; the Command Center's "Expenses & rent" entry gets its `href`.

## 5. Error handling

`401` signed out → login redirect; `403` → the access card; `422` (future month typed into the address) → the message above the form,
no figures; anything else → "The expense dashboard is unavailable right now. Please try again." A malformed `month` in the address is
dropped by the page (the API then defaults to the current month).

## 6. Testing

- Backend `tests/test_mgmt_010_expenses.py`: approved manual expense counted under its head (month + annual); draft / submitted /
  rejected excluded; reversal nets to zero; automatic commission → Commissions, trip expense → Travel; income never counted; a custom
  category → Other; FY boundary (March vs April); total = sum of heads; annual = sum of months; non-INR in `not_counted`; month
  validation 422s; super_admin / other roles 403; signed out 401. Tests read deltas (the stack DB is shared and never emptied).
- Web vitest: `managementExpenses.test.ts` (month param, URLs); `ManagementExpenses.test.tsx` (rows, total, bars, empty, not-counted).
- Playwright `mgmt-010-expenses.spec.ts`: accountant opens the dashboard from the Command Center, sees the 8 heads and the total;
  super_admin is refused.
