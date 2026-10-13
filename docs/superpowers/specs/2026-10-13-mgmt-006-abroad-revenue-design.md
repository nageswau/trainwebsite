# mgmt-006 — Abroad Education revenue dashboard — design

- **Feature:** `mgmt-006` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-006). Depends on mgmt-005 (PR #249, merged on `main`).
- **Evidence:** `EVID-017` §4 "Revenue must be separated" / "A. Abroad Education Revenue" (student service fees, application-related
  revenue, university commission, agent-generated revenue; country / university / intake / agent-wise revenue; Abroad Education Revenue,
  Expenses, Gross Contribution — `DERIVED_BLUEPRINT`); Management M3/M4/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`, MG11); mgmt-005
  `DEC-SCOPE-192` MA1–MA12; mgmt-010 ME3/ME4/ME9 (period and validation idiom).
- **Decision:** one new DEC-SCOPE (number taken at merge). MR1–MR12 below answer Q-09 and Q-10 for this page, and the Q-04 shared-cost
  question for this page only, with **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

The finance tier sees what the Abroad Education vertical earned, what it spent, and what is left (gross contribution), for a month and
its Indian financial year to date. It also sees where the revenue came from by country, university, intake and agency, as far as the
data allows. Read-only; every rupee comes from `services/ledger.lines()`, so the page reconciles with the ledger. Nothing is stored.

## 2. Decisions (MR1–MR12)

| # | Point | Answer |
|---|---|---|
| MR1 | Period | The selected month (`YYYY-MM`, IST days, default this IST month) and the Indian financial year to date (1 April → end of the selected month), as mgmt-010 ME3/ME4 |
| MR2 | Revenue | The counted `ledger.lines()` income lines with vertical `abroad`: approved manual Abroad income (a reversal negative), INR overseas `Payment`s (agent deposits never, MA1), and INR university commission receipts (partner only, MR7) |
| MR3 | Income kinds (Q-09) | Four rows that partition revenue: **Student service fees** ← overseas payments with `reference_type = service_fee`; **Application-related & other student payments** ← every other overseas payment type (no module records which of those are application fees, so they are not split further); **University commission** ← upc-019 receipts; **Recorded in the ledger** ← approved manual Abroad income entries. Total = the sum of the four |
| MR4 | Agent-generated revenue (Q-09) | Not a separate stream of money in any module: it is shown as a figure, the revenue attributed to an agency in MR5's agency breakdown (a subset of revenue, never added to it) |
| MR5 | Breakdowns (Q-10) | Country, University, Intake, Agency, each with an **Unattributed** row, so every breakdown sums to revenue. A payment is attributed when its `reference_id` is an overseas application's id: that application's university, the university's country, the intake text (trimmed) and the agency (the application's `agent_id`, else its agent student's `agent_id`, → that member's `AgentOrg`). A linked application with no agency is the row **Direct (no agency)**. A university commission receipt is attributed to its university and country; its intake and agency are unattributed (one receipt can cover many applications). Manual entries are unattributed everywhere |
| MR6 | Expenses | The counted expense lines with vertical `abroad` (paid agent commissions, approved agent-BDM trip expenses, approved manual Abroad expenses), by category label. **Shared costs are not allocated** here (Q-04 allocation belongs to mgmt-009); the shared expense total for the same period is shown as a note |
| MR7 | Commission (M3, U2 amended, MG11) | `management_access.can_view_university_commission`: partner only. For the accountant the receipts are left out of every figure (revenue, kinds, breakdowns, contribution, not-counted) and the response says `commission_visible: false`; the page says the figures exclude university commission. `partnership_access.COMMISSION_ROLES` is **not** changed (it would open the partnership commission routes to partners, against MG2) |
| MR8 | Contribution | Gross contribution = revenue − expenses, for the month and the year. A negative value is shown as negative |
| MR9 | Other currencies | Automatic Abroad lines in another currency are not counted and are summed per currency and kind in `not_counted` (MA8) |
| MR10 | Validation | `month` as mgmt-010 ME9: `YYYY-MM`, 2000-01 or later, not after this IST month → else `422` |
| MR11 | Access (M13) | Finance tier only (`ledger.require_finance`): partner and accountant. `super_admin` `403` "Finance access required"; any other role `403`; signed out `401` |
| MR12 | Privacy (Q-32 interim) | No student names or ids. Only country, university, intake and agency names |

## 3. API

`GET /management/revenue/abroad?month=YYYY-MM` → `200`
`{month, year_start, year_label, commission_visible, kinds[{key, label, month, year}], revenue{month, year}, agent_generated{month, year},
breakdowns[{key, label, rows[{label, month, year}], unattributed{month, year}}], expenses[{label, month, year}], expense_total{month, year},
shared_expenses{month, year}, contribution{month, year}, not_counted[{currency, kind, amount, count}]}`. Amounts are decimal strings.
Breakdown rows are sorted by the year figure, largest first, then by label; rows netting to zero for both periods are left out.

## 4. Components

- `services/management_abroad_revenue.py` (new): one grouped query over `ledger.lines()` joined (outer) to `payments`, the linked
  `overseas_applications`, `universities`, `countries`, the agency path, and `university_commission_receipts`; one grouped expense query;
  one for `not_counted`. Python folds the grouped rows into the month and year columns. `ledger.py` is unchanged; the period helpers
  come from `management_expenses`.
- `services/management_access.py`: `can_view_university_commission(user)`.
- `api/management.py`: the route; `schemas.py`: `AbroadRevenueOut` and its rows.
- Web: `lib/managementAbroadRevenue.ts` (types, URLs, ledger link); `components/ManagementAbroadRevenue.tsx` (month form, summary
  figures, kinds table, four breakdown tables with share bars, expenses table, notes, empty state, ledger link); page
  `app/management/revenue/abroad/page.tsx`; the Command Center's "Abroad Education revenue" entry gets its `href`.

## 5. Error handling

As mgmt-010: `401` → login; `403` → the access card; `422` → the message above the form, no figures; anything else → "The Abroad
revenue dashboard is unavailable right now. Please try again." A malformed `month` in the address is dropped by the page.

## 6. Testing

- Backend `tests/test_mgmt_006_abroad_revenue.py` (deltas in a random far-past month): service fee → its kind and Unattributed; a
  payment linked to an agency application → country/university/intake/agency rows and agent-generated; a linked direct application →
  "Direct (no agency)"; an agent deposit and an IT payment never count; a university receipt counts for the partner and is absent for the
  accountant; approved manual Abroad income/expense counted, draft not; commission expense and agent-BDM trip in expenses; shared expense
  only in the note; every breakdown + unattributed = revenue; kinds sum = revenue; contribution = revenue − expenses; month ⊂ year;
  non-INR in `not_counted`; 422s; 403s; 401.
- Web vitest: lib URLs/params; component (kinds, breakdowns, contribution, commission note, empty state).
- Playwright `mgmt-006-abroad-revenue.spec.ts`: partner opens it from the Command Center and sees the university commission row;
  the accountant sees the exclusion note and no commission row; super_admin is refused.

## 7. Known follow-up (not this item)

mgmt-005's ledger list and mgmt-013's accounts dashboard still show university commission lines to the accountant (mgmt-005 MA12,
mgmt-013 AD12). MG11 assigns the remaining sweep to mgmt-034; this item only applies M3 to its own page.
