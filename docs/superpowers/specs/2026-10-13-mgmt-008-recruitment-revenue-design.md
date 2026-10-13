# mgmt-008 — Recruitment & Placement revenue dashboard — design

- **Feature:** `mgmt-008` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-008). Depends on mgmt-005 (PR #249), rec-031 (PR #233) and
  rec-033 (PR #239), all merged on `main`, so the backlog's "not available yet" state never applies.
- **Evidence:** `EVID-017` §6 "Recruitment & Placement Revenue" (lines 245–281, `DERIVED_BLUEPRINT`): six revenue kinds (recruitment
  fees, placement fees, employer payments, internship programs, corporate training, other employer revenue) and nine KPIs (recruiters,
  partner companies, open positions, candidates, interviews, selections, joining, placement percentage, revenue per placement).
  Management M4/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`); mgmt-005 MA1–MA11 (`ledger.lines()`, the `recruiter_payment` source);
  rec-033 PF1–PF9 (`recruiter_metrics.performance`); mgmt-003 MS10/MS15 (S10 Partner Companies, S15 Recruiters); rec-035 M3 (open
  requirements); Appendix B R1, R11.
- **Decision:** one new DEC-SCOPE (number taken at merge). RR1–RR12 answer Q-12 and the open points of the backlog item with
  **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

The finance tier sees what the Recruitment vertical earned, by kind, for a month or the financial year to date, next to the §6 KPIs;
the super admin sees the KPIs only. Read-only; money comes from `services/ledger.lines()`, counts from `recruiter_metrics.performance`
(rec-033) and the Command Center's own S10/S15 rules. Nothing is stored.

## 2. Decisions (RR1–RR12)

| # | Point | Answer |
|---|---|---|
| RR1 | Period | `month` (`YYYY-MM`, IST, default this month; January 2000 to this month) and `period` = `month` or `year` (Indian financial year to the end of `month`) — the mgmt-007 IR1 idiom |
| RR2 | Lines | Counted `ledger.lines()` income rows of the `recruitment` vertical: rec-031 payments (always rupees) + approved manual income (reversals negative) |
| RR3 | Revenue kinds (Q-12) | "Recruiter invoice payments" (rec-031 — the recruitment / placement fees invoiced per requirement) + one row per manual income category booked to Recruitment. Internship programs, corporate training and other employer revenue are recorded as manual ledger income in categories a partner creates (mgmt-004); no category is seeded (no migration) |
| RR4 | Revenue | Σ the kind rows (R1 for `recruitment`). The invoice row is always listed; a manual category netting to zero is not |
| RR5 | Flow KPIs | Candidates = rec-033 P4 (candidates sourced), Interviews = P6, Selections = P7, Joining = P8 — the rec-033 Total for the same range, all recruiters + Unassigned (AC2). The range ends today when the period runs past today (rec-033 refuses a future end) |
| RR6 | Stock KPIs | Recruiters = S15 (active `placement_team` with a recruiter profile); Partner companies = S10 (past "Interested"); Open positions = rec-035 M3 (requirements in an open status). Counted now, as on the snapshot |
| RR7 | Placement % | Joining ÷ Candidates × 100, one decimal; `null` ("—") when there are no candidates |
| RR8 | Revenue per placement (R11, AC1) | Revenue ÷ Joining for the period, in rupees; `null` ("—") when nobody joined |
| RR9 | Access | Management roles only (`require_management`): partner and accountant get revenue + all nine KPIs; super_admin gets the KPIs without money (`revenue_visible: false`, `revenue` and revenue per placement `null`, the ledger never queried); everyone else `403` "Management access required"; signed out `401` |
| RR10 | rec-033 reuse | `recruiter_metrics.performance` takes the allowed roles as a keyword (default PF1's), so the management read calls it unchanged for every other caller |
| RR11 | Navigation | The "Recruitment revenue" Finance entry goes live. The super admin keeps their own sidebar (MG10) and gets a "Recruitment KPIs" link there; the Command Center tier lists are unchanged |
| RR12 | Costs | Recruitment expenses and contribution are not on this page (§6 lists none); they belong to mgmt-009 (vertical P&L) |

## 3. API

`GET /management/revenue/recruitment?month&period` → `200`
`{month, period, start, end, label, kpi_end, revenue_visible, revenue: {total, kinds[{key, label, amount}]} | null,
kpis{recruiters, partner_companies, open_positions, candidates, interviews, selections, joining, placement_pct, revenue_per_placement}}`.
Kind keys: `recruiter_invoices`, or `ledger:<category label>` for a manual category. `422` for a malformed / future / pre-2000 month
or a bad period.

## 4. Web

`/management/revenue/recruitment` (server-rendered, the period in the address via a GET form): the month / period form, the KPI tiles
in §6 order, and for the finance tier the revenue total and the kinds table with a note on how to record the other §6 kinds. Access
card for 401/403 (`accessUnavailable`). The super admin's tiles omit revenue per placement.

## 5. Tests

- Backend `test_mgmt_008_recruitment_revenue.py`: access per role; 422s; RR2/RR3 kinds and reversal; AC1 revenue per placement =
  revenue ÷ joined; AC2 flow KPIs = `GET /recruiter/performance` totals for the same range; RR6 stock KPIs = the snapshot's S10/S15;
  super admin sees no money; FY period sums the months.
- Web: `managementRecruitmentRevenue.test.ts` (query/url), `ManagementRecruitmentRevenue.test.tsx` (tiles, "—", super-admin view,
  empty state); nav tests; e2e `mgmt-008-recruitment-revenue.spec.ts`.

## 6. Risks

`recruiter_metrics.performance` serves rec-033/035 pages: the keyword defaults to today's roles (re-run `test_rec_033_performance.py`).
The stack DB is shared, so company-wide figures are asserted as before/after deltas or against the rec-033 endpoint read in the same test.
