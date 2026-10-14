# mgmt-034 — Confidentiality + permission sweep: exploratory QA (2026-10-14)

- **Build:** `feature/mgmt-034`. Isolated stack `mgmt034` (web `localhost:13134`, api `127.0.0.1:18134`), seeded demo accounts. One QA
  university commission receipt (₹64,321, reference `QA34-COMMISSION`, dated today) was planted so the partner/accountant difference is
  visible. The shared test DB also holds pytest rows (hundreds of ledger categories, so the Operations head lists many parts).
- **Method:** Playwright (Chromium) scripts. Accountant at 1366×900, 820×1100 and 375×800; partner, super_admin and signed out at 1366×900.
  Console errors, page errors and HTTP ≥ 500 were captured; horizontal overflow measured; full-page screenshots reviewed by eye. First pass
  with no code changes. The item is mostly backend (tests + CS1); the browser surface is the accounts dashboard, the ledger list and the
  tier refusals.

## First pass — results

| Check | Accountant | Partner | super_admin | Signed out |
|---|---|---|---|---|
| `/management/accounts` receivables by source | Student fees, Recruitment invoices (no university line) + "University commission is not included: only partners see it." | + "University commission: ₹1,39,000.00", no note | Access unavailable | → `/admin/login?next=%2Fmanagement%2Faccounts` |
| Receivables explanation | "unpaid student fees and open recruitment invoices" (no commission clause) | commission clause kept | — | — |
| `/management/ledger?include=auto` | no "University commission" line, no `QA34-COMMISSION` | `QA34-COMMISSION` listed | Access unavailable | — |
| `/management/investments`, `/capital`, `/reviews` | Access unavailable ×3 | — | investments: Access unavailable | — |
| `/management/snapshot` | Access unavailable | — | — | — |
| `/management/salaries` | renders | — | Access unavailable | — |
| Horizontal overflow (3 widths) | 0 | 0 | 0 | — |
| Console errors / HTTP ≥ 500 | see QA34-02 | none | none | — |
| Refresh, Back, Forward (accounts → ledger) | Back → accounts with the note; Forward → ledger | same | — | — |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA34-01 | Low | accountant | `/management/ledger?include=auto` | Sign in as the accountant, choose "Manual + automatic" | The explanation lists only the automatic lines the accountant can see | "Automatic lines (… recruiter and university receipts) …" although CS1 leaves university receipts out of the accountant's list | **Fixed** (TDD: `ManagementLedger.test.tsx` "names university receipts among the automatic lines for a partner only"; the page passes `me.tiers.partner_only`; the accountant reads "… approved BDM trip expenses and recruiter receipts) … University commission is not included: only partners see it."). Re-verified in the browser and by `mgmt-034-confidentiality.spec.ts`. |
| QA34-02 | Info | accountant | one page of the tablet run (URL not captured) | First exploratory run at 820×1100 | No page error | One `Minified React error #418` (hydration mismatch) | **Not reproducible:** 128 further loads of every touched page at 820 and 1366 px gave no page error. The changed components render no clock-dependent text (the accounts date is formatted in UTC on both sides). Not attributable to mgmt-034; no change. |

## After the fix

- `tests/e2e/mgmt-034-confidentiality.spec.ts` 5/5 and `mgmt-013-accounts.spec.ts` 4/4 against the rebuilt stack.
- Exploratory script re-run: the accountant's ledger explanation reads "… approved BDM trip expenses and recruiter receipts) …" at all three
  widths; no console or page errors; no overflow.
