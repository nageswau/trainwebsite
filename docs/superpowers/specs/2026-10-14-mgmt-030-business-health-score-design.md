# mgmt-030 — Business health score (design)

**Feature:** `mgmt-030` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-030 and Appendix B "Business health"; EVID-017
`Management Functionalities.md` §30, L1157–L1203).
**Depends on (merged):** mgmt-009, mgmt-012, mgmt-013, mgmt-016, mgmt-021, mgmt-022, mgmt-023 and mgmt-026 (all on `main`).
**Status of the answers below:** recommended defaults (BH1–BH14), applied under the owner's standing instruction for the build session
("proceed with recommended answers"). They answer Q-29 for this item. `UNVERIFIED`: `NEEDS_CONFIRMATION` at sign-off.

## Intent

§30: "This gives partners an instant understanding of the company." The source asks for one overall score out of 100, calculated
automatically from twelve factors, with a green / amber / red line per factor. The page computes each factor live from the figures
the merged dashboards already own. It stores nothing, so there is no migration. Weights and thresholds are code constants
(Q-29 interim).

## Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| BH1 | Readers | **Partners** see all twelve factors. **super_admin** sees only the six operational factors (H4–H9), and their overall score is computed over those six and labelled "Operational health" (M13: no finance figure, not even folded into a score). The six finance factors are **never queried** for super_admin. `accountant` gets `403` "Operational access required" (the backlog names partner and super_admin only). Everyone else gets `403` and a signed-out caller gets `401` |
| BH2 | Period | `month` = `YYYY-MM`, from January 2000 to the current IST month (`422` otherwise, the mgmt-006 rule). The default is **the last complete month**. Choosing the current month scores it so far (`partial: true`), and the page says so |
| BH3 | Comparison | Every growth factor compares the month with the month before it (MoM). Profit and Marketing ROI are scored on the month's own figure |
| BH4 | Factors (H1–H12) | H1 Revenue: P&L total revenue (mgmt-009, MoM). H2 Profit: P&L margin (mgmt-009). H3 Cash flow: entered cash/bank balance (mgmt-013, MoM). H4 Sales pipeline: new leads (enquiries created) + applications created (MoM). H5 Student growth: new IT students + new school students (mgmt-026 KPIs, MoM). H6 Enrollment: applications reaching Enrolled (mgmt-026, MoM). H7 Agent growth: agencies activated (mgmt-026, MoM). H8 School growth: school MoUs signed (mgmt-026, MoM). H9 University partnerships: universities that became partners (mgmt-026 = the UPC G1 change, MoM). H10 Employee productivity: revenue ÷ the month's salary headcount (mgmt-011, MoM). H11 Marketing ROI: K7 total (mgmt-012). H12 Expenses: expense growth against revenue growth (mgmt-009) |
| BH5 | Scales (0–100, clamped) | Growth g% (H1, H3–H10): `50 + 5·g`, so −10% → 0, flat → 50 and +10% → 100. Margin m% (H2): `2·(m + 20)`, so −20% → 0, 0% → 40, 15% → 70 and 30% → 100. ROI r% (H11): `50 + r/2`, so −100% → 0, 0% → 50 and +100% → 100. Expenses (H12): d = expense growth − revenue growth (points); `50 − 5·d` |
| BH6 | Not available | A factor with no basis is **excluded and its weight is shared out** (backlog edge case). Cases: both months 0, or the earlier month is 0 for H12; an earlier month of 0 with activity now scores 100 ("new this month"); no revenue (H2); a missing cash/bank balance in either month (H3); a missing or zero headcount in either month (H10); no tagged spend (H11). Each case carries a reason |
| BH7 | Weights | Revenue 15, Profit 15, Cash flow 10, Sales pipeline 10, Student growth 8, Enrollment 8, Agent growth 5, School growth 5, University partnerships 5, Employee productivity 7, Marketing ROI 6, Expenses 6 (Σ 100) |
| BH8 | Overall | The weighted average over the available factors, rounded half-up. Each factor gets whole points by largest remainder, so **Σ points = the overall score** (acceptance: "the breakdown recomputes the overall score"). This reuses upc-028's `health_score`. With no available factor the score is null: "Not enough data" |
| BH9 | RAG | Green ≥ 70, Amber 40–69, Red < 40 (Appendix B, proposed), for each factor and for the overall score. The pill always carries its word, so colour is never the only cue |
| BH10 | Tier per factor | P (finance) for H1, H2, H3, H10, H11 and H12. O (operational) for H4–H9 (Appendix B) |
| BH11 | Values shown | Each factor returns `current`, `previous` (decimal strings) and `change` (growth %, or points for H12), plus `unit` (`inr` / `count` / `percent`), so the page writes the measure and the API does no text formatting |
| BH12 | Writes / audit | None. The route is read-only, not audited, and runs a fixed number of statements |
| BH13 | Page / nav | `/management/health`. The Business Intelligence entry "Business health score" goes live as **operational** (partner + super_admin). It was a partner-only placeholder; super_admin now sees the operational part. super_admin nav gets "Management business health" |
| BH14 | Settings | Weights, scales and RAG bands are constants in `services/management_health.py` (backlog: "weights and thresholds as settings: design"). Changing them is a code change, recorded against Q-29 |

## API

`GET /api/v1/management/health?month=YYYY-MM` → `ManagementHealthOut`:
`{month, previous_month, partial, scope: "business" | "operational", score: int | null, rag: "green" | "amber" | "red" | null,
factors: [{key, label, tier, weight, unit, current, previous, change, score, rag, points, note}]}`.
Partners get 12 factors and super_admin gets 6. `points` is null when the factor is not available. Errors: `422` for a month out of
range, `403` for the accountant and other roles, `401` when signed out.

## Backend

`services/management_health.py`:
- `FACTORS` (`partnership_metrics.Factor`) holds the weights.
- `growth_score`, `margin_score`, `roi_score` and `expense_score` are the pure scales.
- `rag(score)` maps a score to its band.
- `health(db, user, month)` composes the inputs:
  - `management_pnl.dashboard` for both months;
  - one `FinanceBalance` read and one `SalaryMonthTotal` headcount read, each covering both months;
  - `management_marketing._spend` / `_revenue` / `roi`;
  - `management_metrics.plan_actuals` for both months;
  - one enquiry count.

`partnership_metrics.health_score(values, factors=HEALTH_FACTORS)` gains the optional `factors` argument, so its behaviour is
unchanged. The route is appended to `api/management.py` behind `_operational`.

## Frontend

- Files: `app/management/health/page.tsx` (server), `components/ManagementHealth.tsx` and `lib/managementHealth.ts`.
- A GET month form.
- The overall score is a tile: "84/100", plus a RAG pill.
- One RAG line per factor (the §30 list), then a breakdown table: Factor · Status · Measure · Score · Weight · Points, with a total row
  where Σ points = the score.
- Not-available factors show their reason.
- Empty state: "Not enough data to score {month}". Error: the API's 422 text, or an "unavailable" notice.

## Tests

- **Backend:** pure scale and RAG tests, plus:
  - access: 401; accountant and other roles 403; partner gets 12 factors; super_admin gets 6 operational factors and no finance key;
  - 422 months;
  - the default month is the previous month;
  - Σ points = the score;
  - a far-past month with no data scores null;
  - controlled ledger revenue in two far-past months gives the expected H1 score;
  - a not-available factor is excluded.
- **Web:** lib unit tests, component tests (tiles, RAG text, super_admin variant, empty and error states), and an e2e spec for the
  partner, super_admin and accountant.
