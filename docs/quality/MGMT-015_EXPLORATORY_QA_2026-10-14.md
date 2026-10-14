# mgmt-015 — Partner capital accounts — exploratory QA (2026-10-14)

- **Build:** `feature/mgmt-015`, Docker Compose project `mgmt015` (web `localhost:13015`, API `127.0.0.1:18015`), seeded with `python -m app.seed`.
- **Browser:** Playwright Chromium (headless), scripted exploratory pass; desktop 1366×900, tablet 820×1180, mobile 390×844.
- **Data note:** the stack database is shared with the API tests, which create many `partner` users, so the accounts table showed 160
  partner columns and a share total of 620%. That is test data, not a defect: production has the two partners.

## Scenarios

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Signed out, `/management/capital` | — | Redirect to `/admin/login?next=%2Fmanagement%2Fcapital` ✅ |
| 2 | Command Center → "Partner capital accounts" | partner | Page opens; figures table, Total column, net-profit line ✅ |
| 3 | Shares not totalling 100% (AC1) | partner | "Shares in force total 620.00%, not 100%." shown as a status, nothing blocked ✅ |
| 4 | Balance (AC2) and profit share (AC3) | partner | Arjun ₹5,00,000 invested → balance ₹5,00,000; profit share ₹28,750 = 50% × ₹57,500 FY net profit ✅ |
| 5 | Empty submit / negative amount | partner | "Choose the partner." (field focused); "Enter the amount in rupees with up to 2 decimals." ✅ |
| 6 | Withdrawal over the balance (CP11) | partner | "…more than Meera Partner's capital balance of ₹5,00,000.00. Record it anyway?"; button becomes "Record it anyway" ✅ |
| 7 | Double click on "Record it anyway" | partner | Exactly 1 POST; balance shows −₹9,94,99,999.00 in red with "Withdrawals exceed the capital put in" ✅ (QA then recorded an opposing entry with a note, CP4) |
| 8 | Network dropped / server 500 on save | partner | "The request did not complete… your entry is kept." (amount kept); "The entry could not be saved. Try again." ✅ |
| 9 | Share 120% / month 2099-01 | partner | Client message for 120; API 422 "Choose a month from January 2000 to 12 months ahead" shown in the form ✅ |
| 10 | Period form, refresh, back | partner | `?month=2026-10&period=month` kept after reload; back returns to the previous page (clean-history recheck, same as mgmt-009 P&L) ✅ |
| 11 | Future month in the URL | partner | "Choose this month or an earlier one", period form kept ✅ |
| 12 | `?offset=25` | partner | "Showing 26–28 of 28" + Previous ✅ |
| 13 | Tablet / mobile layout | partner | No horizontal page overflow (0 px); tables scroll in their own region ✅ |
| 14 | Broken images, console, network | partner | No broken images; console errors only from the induced 500 / abort / 422; no other failed calls (Next prefetch aborts ignored) ✅ |
| 15 | Accountant / super admin | accountant, super_admin | "Access unavailable — Only partners can open this"; no Command Center entry ✅ |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Minor (layout) | partner | `/management/capital` | Desktop or tablet → "Record a capital entry" | The open form spans the content width, like the card below it | It was sized to its content inside the button row, with "Set share %" wrapping beside or under it (screenshot `tablet-entry-form.png`) | **Fixed:** both forms take `flexBasis: 100%`; re-checked at 1366 (form 1036 px = card 1036 px) and 820 (760 = 760) |

| RV-01 | Major (API) | partner | `PUT /management/capital/shares` | Two partners make the first save of the same month at once (CP14) | 409 "The shares were changed at the same time…" | The unique violation was raised at the per-row `flush`, outside the `try` around `commit`, so the loser got a 500 | **Fixed (simplification review):** the `try` covers the whole write; test `test_losing_the_first_insert_race_for_a_month_is_a_409_not_a_500` (RED 500 → GREEN 409) |

No other defects found. Playwright `mgmt-015-partner-capital.spec.ts` (4 tests) and the regression specs `mgmt-001`, `mgmt-014` pass (11/11).
