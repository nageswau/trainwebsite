# mgmt-012 — Marketing budget, spend & ROI — exploratory QA, 2026-10-13

- **Build:** `feature/mgmt-012`, isolated stack `mgmt012` (web `localhost:13012`, api `127.0.0.1:18012`), seeded demo accounts.
- **Method:** this was the first pass, run with no code changes. A scripted headless Chromium (Playwright) session ran against the real
  stack.
  - Real data: the accountant created a ₹85,000 Marketing expense tagged Instagram through the ledger API and submitted it, and
    `partner.one` approved it.
  - Console errors, failed requests (prefetch `_rsc` noise filtered), 5xx responses and broken images were captured. Screenshots were
    taken at 1440, 768 and 375 px.
- **Roles:** partner, accountant, super_admin, it_admin, and signed out.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: the tagged approved expense shows as Instagram spend | ✅ ₹85,000.00 spent; budget "Not set"; revenue ₹0.00; ROI −100% |
| 2 | Budget saved via the form; success message; refresh keeps it | ✅ "Budgets for October 2026 saved."; ₹1,00,000.00 after reload; input keeps `100000.00` |
| 3 | Duplicate submission (double-click Save) | ✅ one `PUT` |
| 4 | Invalid input (`abc`, `1.005`) | ✅ 422 on the Google field: "Enter rupees as a number with up to 2 decimals"; alert "Check the highlighted budgets and save again." (the browser logs the 422 resource — expected) |
| 5 | Future month `?month=2099-01` | ✅ alert "Marketing can be shown up to the current month. Pick another month."; month form stays |
| 6 | Malformed month `?month=abc` | ✅ falls back to the current month |
| 7 | Back / refresh after changing month | ✅ Back returns to the previous month (URL, heading and input agree); refresh keeps it. A first-pass reading of URL "2024-04" with heading "March 2024" was the script reading `page.url()` before history settled — a targeted re-check (full loads and the month form) agrees everywhere |
| 8 | Accountant | ✅ same figures as the partner |
| 9 | Super admin (incorrect role for money) | ✅ "Marketing leads" nav entry lands on `#marketing-leads` with the heading in view; no ₹ anywhere; no budget form; API `money_visible: false` with null budget/spend/revenue/ROI; `PUT` 403. **See QA12-01** |
| 10 | Unauthorized role (it_admin) | ✅ "Access unavailable" |
| 11 | Signed out | ✅ redirected to `/admin/login?next=%2Fmanagement%2Fmarketing` |
| 12 | Desktop / tablet / mobile | ✅ `scrollWidth` = viewport at 1440 / 768 / 375 (no page-level sideways scroll); the ROI table scrolls inside its card on a phone; figures stay on one line (e2e) |
| 13 | Empty states | ✅ zero spend → ROI "—"; no leads → conversion "—"; no budget → "Not set"; no campaigns → "No campaign ran or brought leads in …" (vitest) |
| 14 | Console errors / failed network calls / 5xx / broken images | ✅ none besides the intentional 422s |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA12-01 | Low | super_admin | `/management/marketing` | Sign in as `superadmin@`, open Command Center → "Marketing leads" | A title and lead-in that match what the role sees (lead figures only) | Title "Marketing budget & ROI" and a lead-in promising budget, spend, revenue and ROI, none of which is shown | **Fixed.** Without the finance tier the page is titled "Marketing leads" and the lead-in names leads, qualified leads, conversions and campaigns. e2e asserts it. RED → GREEN |

## Observations (not defects)

- The partner's nav lists both "Marketing budget & ROI" and "Marketing leads". This is intended: the operational entry is how
  super_admin reaches the page, and it follows the Salaries / Employee cost precedent.
- On a 375 px phone the 15 figure tiles stack in one column, so rupee amounts stay on one line. This is the same `accounts-tiles` rule
  as mgmt-013 QA-02.
- Campaign rows named "MK running …" come from backend test data in the shared stack DB.

## Evidence

- Screenshots (scratchpad, not committed): `partner-desktop.png`, `partner-tablet.png`, `partner-mobile.png`, `partner-past-month.png`,
  `superadmin-desktop.png`.
- e2e `apps/web/tests/e2e/mgmt-012-marketing.spec.ts`: 5/5 after the fix.
