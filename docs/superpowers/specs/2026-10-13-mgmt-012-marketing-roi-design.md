# mgmt-012 — Marketing budget, spend, ROI + marketing dashboard — design

- **Feature:** `mgmt-012` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-012). It depends on mgmt-004 (ledger, merged in PR #246) and
  mgmt-003 (the `management_metrics` foundation, merged in PR #244). It also reads mgmt-005's `ledger.lines()` (merged).
- **Evidence:** `EVID-017` (`DERIVED_BLUEPRINT`) §10, lines 388–407: Budget → Spend → Leads → Conversions → Revenue → ROI per channel.
  Its example table has the columns Channel / Budget / Spent / Leads / Customers / Revenue. It also has §15, lines 561–593, with 15
  figures. Management M7 and M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`) settle the rest:
  - Channels are the lead sources plus campaigns.
  - The partner or the accountant enters a monthly budget per channel.
  - Spend is ledger expenses tagged with a channel.
  - Leads, qualified leads and customers come from `enquiries`.
  - Revenue is the paid fees of converted leads' students.
  - ROI = (revenue − spend) ÷ spend.
  - super_admin sees lead counts only.

  Appendix B defines K1–K7.
- **Decision:** `DEC-SCOPE-206` (provisional number). MK1–MK14 below are **recommended defaults, `UNVERIFIED`**. I took them on the
  owner's instruction to proceed with recommended answers. They answer Q-14 (the channel list and the attribution window) as an interim
  default.

## 1. Intent

Management sees, per marketing channel and month, what was budgeted and what was spent. It also sees the leads, qualified leads and
customers each channel brought, the fee revenue those customers paid, and the ROI. That answers the source's question: "What is
working? What should we stop? Where should we invest more?"

The partner or the accountant types each month's budget per channel. Spend is never typed twice: it is the ledger's approved expenses
tagged with the channel (mgmt-004 ML6). super_admin sees the same page with lead counts only.

## 2. Decisions (MK1–MK14)

| # | Point | Answer |
|---|---|---|
| MK1 | Channels (Q-14 interim) | The 13 lead sources of `tel_sources.TEL_SOURCES`, labelled by `telecaller_reports.SOURCE_LABELS`. They are exactly the ledger's channel tags (ML6), so budget, spend and leads share one key. No channel is added. "Schools" and "Events" in the source example are the `school` and `exhibition_event` sources |
| MK2 | §15 source groups | Website leads = `website`. School leads = `school`. College leads = `college`. Agent leads = `agent`. Events = `exhibition_event`. Social media performance = `instagram` + `facebook` + `whatsapp` leads (no platform API). **Influencer leads: not tracked** (no source), shown as "Not tracked" |
| MK3 | Budget | `marketing_budgets`: one row per (month, channel) holding `amount` in rupees (Numeric(14,2), ≥ 0, at most 2 decimals; the salary money rule). A channel with no row has **no budget** ("Not set"), which differs from a budget of ₹0 |
| MK4 | Budget write | `PUT /management/marketing/budgets?month=YYYY-MM` with `{budgets: [{channel, amount}]}` **replaces the month**: rows sent are inserted or updated, and rows left out are removed. `[]` clears the month. An unknown channel → 422 (the backlog's negative case). A duplicate channel → 422. A month after the current IST month → 422, the same as every finance page (`salaries.first_day`). The answer is the dashboard, as GET shows it |
| MK5 | Spend (K2) | Σ of **approved manual expense entries tagged with the channel**, dated in the month, with a reversal counting negative (ML10/ML11; a reversal copies the channel). Automatic ledger lines carry no channel, and an entry has at most one channel, so a rupee is counted once, in one row (**AC2**). Total spend = Σ of the rows |
| MK6 | Leads, qualified (K3, K4) | Leads = enquiries **created in the month** (IST), all divisions, by `source`. Qualified = those leads that reached Qualified or later, by current stage or stage history. This is the tel-024 source-report rule, so the figures reconcile with the Lead Source Report for the same dates |
| MK7 | Customers (K5) | Leads of the channel that are **still converted** and whose **first conversion** (`telecaller_metrics.first_conversions`, tel T5/DB2) is in the month, the same as mgmt-019. Conversion = customers ÷ leads × 100, one decimal; null ("—") when there are no leads |
| MK8 | Revenue (K6, Q-14 interim) | The month's **counted ledger payment lines** (`ledger.lines()` source `payment`: paid, INR, no agent deposits, dated by receipt or payment day in IST). It counts only payments by a student linked to a **still-converted** lead of the channel, paid **on or after the IST day the lead was linked** (`converted_at`). There is no upper window. A student is linked to at most one lead (`uq_enquiries_converted_user`), so a payment counts in at most one channel. This is cash basis, the same as the ledger (MA2) |
| MK9 | ROI (K7) | (revenue − spend) ÷ spend × 100, rounded half-up to one decimal. Null ("—") when spend is 0, per row and for the total. **AC1:** the source's Instagram row (spent ₹85,000, revenue ₹5,00,000) gives 488.2% |
| MK10 | Campaigns | The `tel_campaigns` that **ran in the month** (start ≤ month end, and no end or end ≥ month start) or had leads created in it. Each shows its name, channel, leads, qualified and customers (MK6/MK7 by `campaign_id`), and its active flag. Spend is tagged per channel, not per campaign, so campaigns have no ROI (said on the page) |
| MK11 | Access (M13) | `GET /management/marketing`: any management role. **Finance tier** (partner, accountant): every figure. **super_admin**: lead counts, groups, conversion and campaigns. Budget, spend, revenue and ROI are `null` with `money_visible: false`, and they are **never queried**. Every other role → 403. `PUT …/budgets`: finance tier only (`ledger.require_finance`), so super_admin gets 403 "Finance access required" |
| MK12 | Audit | A new kind `mgmt.marketing_budget` ("Marketing budget", **finance** tier, so super_admin's activity list and `/admin/audit` leave it out). One row per PUT that changes something: entity = the month, fields = the changed channel keys. **No amounts** (the salary/balance precedent). A PUT that changes nothing writes no row |
| MK13 | Concurrency | A PUT takes a transaction-scoped advisory lock on `marketing_budget:<month>`, so two saves of one month serialise and the last one wins. UNIQUE(month, channel) is the backstop |
| MK14 | Page | `/management/marketing?month=YYYY-MM` (default: the current IST month). It has a month form, the §15 figure tiles, the §10 ROI table per channel with a totals row, a budget form (finance tier only; a blank field means no budget), and the campaigns table. The Sales pillar gets two live entries: "Marketing budget & ROI" (finance, the page) and "Marketing leads" (operational, `#marketing-leads`), so super_admin reaches it too |

## 3. Data

Migration `0156_marketing_budgets` (provisional), guarded like 0155:

- `marketing_budgets` has these columns: id, `month` (a date, the 1st), `channel` String(30), `amount` Numeric(14,2),
  created/updated by (FK users RESTRICT), and timestamps.
- Constraints: UNIQUE(month, channel), plus CHECKs on the day (1), `amount ≥ 0`, and `channel IN (the 13 sources)`. The migration keeps
  a frozen copy of the list.
- `downgrade()` refuses while rows exist.

No existing table changes.

## 4. Components

- `services/management_marketing.py`: `dashboard(db, user, month)` and `save_budgets(db, user, month, rows)`.
- `services/management_audit.py`: the `mgmt.marketing_budget` kind.
- `models.py`: `MarketingBudget` + `MARKETING_BUDGET_CHECKS`.
- `schemas.py`: `MarketingBudgetIn`, `MarketingBudgetsIn`, `MarketingRow`, `MarketingGroups`, `MarketingCampaign`, `MarketingOut`.
- `api/management.py`: `GET /management/marketing`, `PUT /management/marketing/budgets`.
- Web:
  - `lib/marketing.ts` (types, URLs, ROI/percent text, the budget body, field errors).
  - `components/MarketingDashboard.tsx` (tiles, ROI table, campaigns).
  - `components/MarketingBudgetForm.tsx` (client).
  - `app/management/marketing/page.tsx`.
  - The `lib/management.ts` hrefs.

## 5. Error handling

| Status | When |
|---|---|
| 401 | Signed out |
| 403 | Not a management role (GET). Not the finance tier (PUT) |
| 422 | A bad or future month, an unknown or duplicate channel, a negative amount, more than 2 decimals or too large (each placed on its field) |

The page shows its access card on 401/403. On 422 it shows the future-month notice and keeps the month form. A failed read shows an
error notice. A save shows its inline message, disables Save while it runs, and guards against a double click. A month with no leads
shows a row of zeros, not an error.

## 6. Testing

- **Backend `test_mgmt_012_marketing.py`:**
  - AC1: Instagram ROI from the source figures.
  - AC2: spend never double-counts. A tagged expense counts once. An unapproved or untagged one and an automatic line do not count. A
    reversal nets to zero.
  - Leads, qualified and customers per channel. Revenue attribution (before conversion excluded, another channel excluded, non-INR
    excluded).
  - Zero spend gives ROI null.
  - super_admin gets counts with no money, and 403 on PUT. Others get 403.
  - PUT replaces the month. Unknown and duplicate channel → 422. Future month → 422.
  - The audit row (fields, no amounts) and the activity tiering.
- **`test_mgmt_012_migration.py`:** a single head, and model = migration (CHECKs).
- **Web vitest:** `marketing.test.ts` and `MarketingDashboard.test.tsx`.
- **Playwright `mgmt-012-marketing.spec.ts`:** the accountant saves a budget and sees spend and ROI. super_admin sees leads without
  money.
