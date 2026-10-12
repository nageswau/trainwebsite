# mgmt-010 — Expense dashboard — exploratory browser QA (2026-10-12)

- **Build:** `feature/mgmt-010`, Docker Compose project `mgmt010` (web `http://localhost:13310`, api `127.0.0.1:18310`), seeded demo data
  plus the rows the backend tests add to the shared stack DB.
- **Tools:** a scripted Playwright (Chromium) exploratory pass, 20 checks (desktop 1366×900, tablet 820×1180, phone 390×844; console
  errors, page errors, failed requests and HTTP 5xx recorded on every page), full-page screenshots reviewed by eye; then the
  Playwright specs `mgmt-010-expenses.spec.ts`, `mgmt-001-command-center.spec.ts`, `mgmt-004-ledger.spec.ts`, `mgmt-005-auto-lines.spec.ts`.
- **Roles:** accountant, partner (`partner.one`), super_admin, trainer, signed out.

## Issues

### QA-01 — Netted-out categories add ₹0.00 / ₹0.00 rows · Low
- **Role / page:** accountant, `/management/expenses`.
- **Steps:** approve an expense in a category, then reverse it and approve the reversal (same month); open the dashboard.
- **Expected:** the category table lists categories that carry money. **Actual:** the category stayed listed with ₹0.00 monthly and
  annual ("CAT AA808228", "Software"). No console/network error.
- **Fix:** `management_expenses.dashboard` drops a category whose monthly and annual sums are both zero. Test
  `test_a_category_that_nets_to_zero_is_not_listed` (RED, then GREEN). Re-verified in the browser.

### QA-02 — On a phone the table captions are clipped and the month table scrolls sideways · Medium (responsive)
- **Role / page:** partner, `/management/expenses` at 390 px.
- **Steps:** open the dashboard on a phone-width window.
- **Expected:** each table's title readable; the two-column month table fits. **Actual:** the visible `<caption>`s were centred across
  the scrolled table width ("By categ…", "Month…" cut at the edge), and the month table kept the global 650 px table minimum, hiding
  its Expenses column off-screen.
- **Fix:** the titles are `<h3>` headings outside the scroll regions (regions `aria-labelledby` them; captions stay for screen
  readers, visually hidden); the month table has `minWidth: 0`. Test "titles the category and month tables … (browser QA-02)" (RED,
  then GREEN). Re-verified in the browser screenshot.

No other issue was found. Two harness corrections (not product issues): `getByLabel("Month")` also matched the "Month by month" region
(the specs use `exact: true`), and trainers sign in at `/it/login`.

## Checked and passing (after the fixes)

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: Command Center → "Expenses & rent" → the dashboard; sidebar entry present | pass |
| 2 | The 8 §8 heads in source order + Total; total = sum of heads; annual = sum of months (e2e) | pass |
| 3 | Month picker (GET form): choose April 2025 → "financial year 2025-26", one month row; survives refresh; back returns to the default month | pass |
| 4 | Invalid inputs: `?month=2099-01` → "Choose this month or an earlier one", no tables; `?month=1999-05` → the 2000 message; `?month=garbage` dropped (default month shown) | pass |
| 5 | Empty state: April 2000 → "No expenses are recorded in the financial year 2000-01 up to April 2000 yet." | pass |
| 6 | Ledger link opens `/management/ledger?month=…&kind=expense&include=auto` | pass |
| 7 | Loading/server error: server-rendered page (no client fetch); an API failure shows "The expense dashboard is unavailable right now" (unit test) | pass |
| 8 | Duplicate submission: read-only page, the form is a GET (idempotent) | n/a |
| 9 | Wrong roles: super_admin → "Access unavailable — Finance access required", no Command Center entry; trainer → access card | pass |
| 10 | Signed out → `/admin/login?next=%2Fmanagement%2Fexpenses` | pass |
| 11 | Desktop, tablet, phone: no page-level horizontal overflow (0 px); wide tables scroll inside focusable regions | pass |
| 12 | Console errors, page errors, failed requests, 5xx: none on any page or role | pass |
| 13 | Broken images: none (no images on the page) | pass |
| 14 | Playwright specs: mgmt-010 (2), mgmt-001 (3), mgmt-004 (3), mgmt-005 (2) — 10 passed | pass |
