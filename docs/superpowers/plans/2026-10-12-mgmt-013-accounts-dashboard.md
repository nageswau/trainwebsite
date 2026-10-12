# mgmt-013 Accounts dashboard — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-013-accounts-dashboard-design.md` (AD1–AD14). Branch `feature/mgmt-013`. Each task goes
RED → GREEN → REFACTOR, with focused tests only.

## Tasks

1. **Model + migration.**
   - Write the test first: `test_mgmt_013_migration.py` (chain after `0154_salaries`, single head, model = migration CHECKs, downgrade
     refuses with rows).
   - Then add `FinanceBalance` and `FINANCE_BALANCE_CHECKS` to `models.py`, and `0155_finance_balances.py`, guarded like 0154.
2. **Schemas.** `BalanceMoney` (signed, for cash) beside `SalaryMoney`; `FinanceBalancesIn` (3 nullable fields, `extra="forbid"`;
   payables/tax ≥ 0); `AccountsOut` and its parts.
3. **Service `services/accounts.py`:**
   - `HEADS`: the income vertical map and the expense label map, Operations as the fallback.
   - `income_expense(db, month)`: one grouped query over `ledger.lines()` plus `ledger.lines_totals`.
   - `receivables(db, today)`: fees, recruitment, university; the INR totals and overdue; the other currencies.
   - `pending_invoices(db)`.
   - `balances(db, month)`.
   - `view(db, month)`.
   - `save_balances(db, user, month, body)`: advisory lock, upsert or remove, audit `mgmt.balance` with field names only.
4. **Audit kind** `mgmt.balance` (finance tier) in `management_audit.KINDS`.
5. **Routes** in `api/management.py`: `GET /management/accounts`, `PUT /management/accounts/balances`. Both call
   `ledger.require_finance` first. The month parsing reuses `salaries.first_day` with an accounts message.
6. **Backend tests** `test_mgmt_013_accounts.py` (spec §6), written before each piece.
7. **Web lib** `lib/accounts.ts` + vitest: URLs, month parsing (reuse `salaryMonth`/`monthLabel`), `balancesBody`, `fieldErrors`,
   `amountText` ("Not entered").
8. **Web components:**
   - `AccountsDashboard.tsx`: income/expense head tables, position tiles, the not-counted note.
   - `BalancesForm.tsx`: client, a double-submit guard, 422s on their fields.
   - Vitest for both.
9. **Page** `app/management/accounts/page.tsx`, plus the "Accounts" href in `lib/management.ts` (with the existing nav test updated if
   it lists live entries).
10. **Playwright** `e2e/mgmt-013-accounts.spec.ts`.
11. **Docs:** `DEC-SCOPE-195`, API §12DI, RBAC §2.120, `DATA_MODEL`, backlog status. Renumber at merge if main moved.

## Phase 3 review notes (folded into the tasks above)

### API

- The contract is the backlog's: `GET /management/accounts?month`, `PUT /management/accounts/balances?month`.
- PUT is idempotent: it replaces the row. It returns 200 with the view, not 204, so the page can refresh from one response, as salaries
  does.
- The month uses the same `MONTH` regex and the future-month 422, with the error placed on `query.month`.
- Money crosses the wire as decimal strings (`Decimal`), as in salaries and the ledger. The client never parses money as a float for
  sending.
- No pagination: this is not a list endpoint.

### Security

- Authorization is checked before any query, in both routes (IDOR is not applicable: the month is the only key).
- No new role. No partner-only data is involved, so the finance tier is correct per M13.
- The university commission is shown as one aggregate (AD12). It contains no student or university names, so there is no PII.
- Every query uses SQLAlchemy expressions (no SQL injection).
- `extra="forbid"` on the body; Decimal validation rejects NaN/Infinity.
- The audit stores field names only, and the logs store the actor id and month only (no amounts).
- The advisory lock prevents lost updates between two concurrent saves of one month.
- CSRF follows the existing cookie and same-origin setup of `sendJson`; nothing new.

### Frontend

- The page reuses the PortalShell, `portal-title`, `metric-grid snapshot-tiles money-tiles`, `table-wrap`, `action-card`, the
  `rupees()` formatter and the `accessUnavailable` card.
- Labelled inputs with `inputMode="decimal"` and `aria-invalid`/`aria-describedby` on error. Feedback uses `role="status"` /
  `role="alert"`.
- Tables scroll inside `table-wrap` on a phone, so the page itself never scrolls sideways.
- An empty month shows ₹0 figures with "Not entered" for the balances. There is no spinner, because the page is server-rendered; the
  Save button shows "Saving…".
