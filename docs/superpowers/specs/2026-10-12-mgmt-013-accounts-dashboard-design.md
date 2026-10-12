# mgmt-013 — Accounts dashboard — design

- **Feature:** `mgmt-013` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-013). Depends on mgmt-005 (merged, PR #249) and mgmt-011
  (merged, PR #251). It reads `ledger.lines()` / `ledger.lines_totals()` (mgmt-005, salary lines from mgmt-011), the IT/overseas
  `payments` + `invoices`, rec-031 `recruiter_invoices` / `recruiter_payments` and upc-019 `university_commission.expected_rows` /
  `received_sums`.
- **Evidence:** `EVID-017` §22 (lines 881–929, `DERIVED_BLUEPRINT`) lists 5 income heads, 8 expense heads and 6 financial-position
  figures, and says the dashboard "should be connected to every module". Management M4, M5 and M13 (`EXPLICIT_APPROVAL`,
  `DEC-SCOPE-186`) make the ledger the money source. Receivables come from unpaid payments and invoices. Payables, cash/bank and tax
  liabilities are entered by hand, there is no GST computation, the accountant enters the figures, and only the finance tier sees them.
  Backlog Appendix B defines R4, R8, R9 and R10.
- **Decision:** `DEC-SCOPE-195` (provisional number). AD1–AD14 below are **recommended defaults, `UNVERIFIED`**. I took them on the
  owner's instruction to proceed with recommended answers. AD7 answers Q-15 as an interim default: month-end balances, not transactions.

## 1. Intent

A partner or the accountant opens one page for a month and sees four things:
- what came in, by the five §22 income heads;
- what went out, by the eight §22 expense heads;
- the profit;
- the financial position: what is owed to EduSphere, what EduSphere owes, cash in hand and tax due.

Income, expenses and profit are read live from the ledger and never copied. Receivables and pending invoices are read live from the
modules that bill. The accountant types only the three month-end figures that exist in no module: cash/bank, payables and tax
liabilities.

## 2. Decisions (AD1–AD14)

| # | Point | Answer |
|---|---|---|
| AD1 | Month | `?month=YYYY-MM`. With no month, the current IST month. A month after the current IST month gets 422, as salaries do. Income, expenses, profit and the entered balances belong to the month |
| AD2 | Income heads (5) | The month's **counted** ledger income (approved manual entries plus INR automatic lines; a reversal counts negatively, as in `lines_totals`), grouped by vertical: `abroad` → Abroad education, `it` → IT training, `recruitment` → Recruitment, `school` → School projects, and `other` **plus `shared`** → Other |
| AD3 | Expense heads (8) | The month's counted ledger expenses, grouped by category label (case-insensitive). Salaries ← "Salaries" (the mgmt-011 automatic line and any older manual entries). Rent ← "Office rent". Marketing ← "Marketing", "Events". Travel ← "Travel" (manual and BDM trip lines). Trainers ← "Trainer payments". Commissions ← "Agent commissions" (manual and paid commission lines). Technology ← "Internet", "Software". **Operations ← everything else**, including any category added later, so every rupee lands in exactly one head. Each head also lists its contributing labels and their amounts, so the mapping is visible on the page |
| AD4 | Totals and profit (R4) | Income total, expense total and profit = income − expense, all from `ledger.lines_totals` for the month. The heads add up to these totals exactly. Automatic lines in another currency are not converted: they are listed per currency as "not counted" (MA8) |
| AD5 | Receivables (R8) | **As of today**, because no module keeps a history of what was unpaid. INR only, with three parts: <br>(a) **Student fees**: `payments` with status `pending` or `overdue`, excluding `agent_deposit` (a pass-through, as in MA1). <br>(b) **Recruitment invoices** (rec-031): each invoice that is not cancelled, counted at amount − received where that is > 0. <br>(c) **University commission** (upc-019): per university and currency, the counted Expected amount − the received amount, floored at 0. <br>Total = a + b + c. **Overdue** = fees with status `overdue` or a due date before today, plus recruitment invoices past their due date. University commission has no due date, so it is never overdue. Amounts in another currency are listed per currency and not added |
| AD6 | Pending invoices (R9) | A count and an outstanding amount, INR. It covers student-fee invoices (`invoices` whose payment is still `pending`/`overdue`, agent deposits excluded) plus recruitment invoices with an outstanding amount. University commission is recorded as receipts and has no invoice, so it is not in this figure. The page says so |
| AD7 | Month-end balances (Q-15 interim, R10) | `finance_balances`: one row per month with `cash_bank`, `payables` and `tax_liabilities`, each Numeric(14,2) and **nullable** (null = not entered). Cash/bank may be negative (an overdraft); payables and tax are ≥ 0. Every value has at most 2 decimals and a magnitude below 10¹². INR only |
| AD8 | Write | `PUT /management/accounts/balances?month=YYYY-MM` with `{cash_bank, payables, tax_liabilities}` (each a number or null). It saves the month's row. If all three are null, the row is removed. A future month gets 422. A transaction-scoped advisory lock serialises two saves of the same month, and the last one wins. The response has the same shape as GET |
| AD9 | Not entered | A month with no row, or a null field, shows "Not entered", never 0. There is no carry-forward from an earlier month |
| AD10 | Access | Finance tier only (partner, accountant), using the ledger's `require_finance` for GET and PUT. super_admin gets 403 "Finance access required", and every other role gets 403. Both finance roles may write (M5: the accountant enters the figures; partners can also edit) |
| AD11 | Audit | `mgmt.balance` ("Month-end balances", finance tier). A PUT that changes something writes one row: entity = the month, fields = the names of the changed fields. No amounts are stored. A save that changes nothing writes no row |
| AD12 | University commission exposure | Only one aggregate figure is shown: no university names, no per-university rows. The finance tier already sees university commission receipts as ledger lines (mgmt-005 MA12), so this exposes nothing new |
| AD13 | Page | `/management/accounts?month=YYYY-MM` has: a month form; Income (5 heads + total); Expenses (8 heads + total, each with its category breakdown); Financial position tiles (Receivables with the overdue part and the three parts, Payables, Cash/bank, Profit, Tax liabilities, Pending invoices); the "not counted" note; and a balances form (3 inputs + Save, with 422s shown on their fields). The "Accounts" nav entry goes live |
| AD14 | Read shape | `GET /management/accounts?month` → `{month, current_month, as_of, income: {heads, total}, expenses: {heads, total}, profit, not_counted, receivables: {total, overdue, fees, recruitment, university, not_counted}, pending_invoices: {count, amount}, balances: {cash_bank, payables, tax_liabilities, updated_at, updated_by}}`. A head is `{key, label, amount, parts: [{label, amount}]}` |

## 3. Data

Migration `0155_finance_balances` (provisional), guarded like 0154:

- `finance_balances` has these columns: `id`, `month` (a date, always the 1st), `cash_bank`, `payables` and `tax_liabilities`
  (Numeric(14,2), nullable), `created_by_user_id` / `updated_by_user_id` (FK users RESTRICT) and timestamps.
- It has UNIQUE(month) and these CHECKs: month is day 1, `payables >= 0`, `tax_liabilities >= 0`.
- `downgrade()` refuses while any row exists, because it would drop finance records.

No existing table changes. The ledger (`services/ledger.py`, frozen after mgmt-005) is only read.

## 4. Components

- `services/accounts.py` holds `view(db, month)` and `save_balances(db, user, month, values)`. It is a separate module, like mgmt-011's
  `salaries.py`. The money comes from `ledger`, and `management_metrics` stays the owner of the operational counts.
- `services/salaries.first_day` gains an optional message, so both pages share one month parser. The default keeps the salaries text.
- `services/management_audit.py` gets the `mgmt.balance` kind.
- `api/management.py` gets two routes. `schemas.py` gets `FinanceBalancesIn` and `AccountsOut`. `models.py` gets `FinanceBalance`.
- Web:
  - `lib/accounts.ts`: types, URLs and the balances body.
  - `components/AccountsDashboard.tsx`: the figures (a server-renderable component).
  - `components/BalancesForm.tsx`: the client form.
  - `app/management/accounts/page.tsx`.
  - The "Accounts" href in `lib/management.ts`.

## 5. Error handling

| Status | When |
|---|---|
| 401 | Signed out |
| 403 | No finance tier |
| 422 | A malformed or future month, a non-number, more than 2 decimals, a negative payable or tax figure, a value out of range |

The page shows the access card on 401/403, an error notice when the read fails, 422s inline on their fields, a disabled Save while
saving, and a success message followed by a refresh.

## 6. Testing

- **Backend `test_mgmt_013_accounts.py`:**
  - AC1: receivables reconcile. Adding a pending fee, an overdue fee, a part-paid recruitment invoice and a cancelled one moves the
    total by exactly the unpaid amounts, and the overdue part moves by the overdue amounts only. A paid fee, a cancelled invoice and an
    agent deposit change nothing.
  - AC2: super_admin gets 403 on GET and PUT, and an unrelated role gets 403.
  - Income and expense heads: a month's entries land in the right heads, the heads sum to the totals, and profit = income − expense.
  - Pending invoices: count and amount.
  - Balances: not entered → null; save, read back, partial nulls, all null removes the row; negative payables, 3 decimals or a future
    month get 422; a negative cash figure is allowed; the audit row has field names and no values; a no-op save writes no audit row.
- **`test_mgmt_013_migration.py`:** single head, the model matches the migration, CHECKs, and downgrade refuses with rows.
- **Web vitest:** `accounts.test.ts` and `AccountsDashboard.test.tsx` (the heads, "Not entered", the balances form's 422 placement).
- **Playwright `mgmt-013-accounts.spec.ts`:** the accountant saves balances and sees them; super_admin is refused.
