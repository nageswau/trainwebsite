# upc-031 — Partnership Reports + CSV export (design)

**Item:** `UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §upc-031 (EVID-020 §32 "📑 Reports"; Q-25). **Depends on:** upc-018, upc-021, upc-023
(all merged). **Gate:** Q-25 and RP1–RP14 below are recommended answers applied under the owner's standing build instruction ("proceed
with the recommended answers; ask only if genuinely blocking") — `NEEDS_CONFIRMATION` at sign-off. No migration.

## 1. Intent

The §32 menu names "Reports" and nothing else. The backlog asks for on-screen tables plus CSV for "pipeline by country, expected
partnerships, university performance, agreements expiring, targets vs actual", with commission columns only for U2 roles, a CSV-injection
guard and a row cap. **Acceptance:** each report reconciles with the figure it repeats; a counselor gets a 403; an empty period shows an
empty report, not an error.

## 2. Decisions (Q-25 → RP1–RP14, recommended)

| # | Question | Answer |
|---|---|---|
| RP1 | Which reports | Five: `pipeline` (pipeline by country), `expected` (expected partnerships), `performance` (university performance), `agreements` (agreements expiring), `targets` (targets vs actual) |
| RP2 | Readers | `partnership_manager` (with a profile), `partnership_head`, `super_admin` — the dashboard's readers (DB15). Every other role, including `overseas_admin` and counselors, → 403 |
| RP3 | Scope | upc-018 PF6 (`scope_filter`): manager = primary/backup; head = direct reports' universities + unowned; super_admin = all. Targets: upc-021's own scope (manager = self, head = direct reports, super_admin = every manager) |
| RP4 | Check order | role (403) → kind (404) → inputs (422), so a refused caller never learns the kinds (tel-024 / AGN-020) |
| RP5 | `pipeline` | One row per country of the active universities in scope: Total, Partners (G1), In progress (G2), Targets (G3), Lost, At risk. Total row = dashboard D1–D5 + lost |
| RP6 | `expected` | upc-023's rows (`expected_rows`), `window` = all / this_month / next_month / this_quarter / undated, ordered as the Expected page (EX12). Columns: University, Code, Country, Stage, Expected date, Owner, Probability (%), Weighted. Total row: Weighted = E4 Σ. `this_month` reconciles with D13 |
| RP7 | `performance` | upc-018's ranking for `from`/`to` (PF1 period rules, default this IST month to date): every ranked row, F3 + F5–F9 (Leads, Counselling, Eligible are not tracked and left out). Total row = the page's `totals`. Commission expected / received (per currency, text) only for U2 roles (RP12). Health score left out (HS10 computes it per page) |
| RP8 | `agreements` | Agreements whose AG4 effective status is **Expiring** today (signed/active, expiry ≤ 90 days), on universities in scope, soonest expiry first: MoU number, University, Code, Country, Type, Status, Expiry date, Days left, Owner. For super_admin it matches `/partnership/agreements?status=expiring`. No commission terms |
| RP9 | `targets` | upc-021 `team()` for `month` (YYYY-MM, default this IST month): one row per manager (Manager, Status, then Target / Achieved per KPI), Total row = the team row. Not-tracked and future actuals are blank |
| RP10 | Filters | Plain strings, validated after the role and kind checks; a bad value → 422 naming the field. Unknown filters are ignored |
| RP11 | Row cap | The screen shows the first 500 rows (`total` says how many there are); a CSV of more than 5,000 rows is refused with a 422 ("narrow the filters"), never cut short |
| RP12 | Commission | Only `can_see_commission` roles get the commission columns (server-side, on screen and in CSV). Today every reader is a U2 role; the check stays so a future non-U2 reader gets none |
| RP13 | CSV | tel-024's `to_csv`: UTF-8 BOM, on-screen labels as the header, the Total row last, every text cell through `_safe_cell` (formula guard). Filename `partnership-<kind>-<as-of>.csv` |
| RP14 | Audit / logs | Reads are not audited; an export writes `partnership_report.export` (kind, which filters, row count) and commits before the file is sent (fail closed). Logs carry ids, kind, filter names and counts — no values, no names |

## 3. API (`api/partnership_reports.py`, §12 addendum)

- `GET /api/v1/partnership/reports/{kind}` → 200 `{kind, title, as_of, filters, columns: [{key, label, numeric}], items, totals | null,
  total, truncated, notes}`; `Cache-Control: private, no-store`.
- `GET /api/v1/partnership/reports/{kind}.csv` → 200 `text/csv; charset=utf-8`, attachment (registered first).
- Errors: 401 no session; 403 role / manager without a profile; 404 unknown kind; 422 bad input or a CSV over the cap.

## 4. Backend structure

`services/partnership_reports.py` holds the five builders and the shared payload shape. Each reuses the existing computation:
`partnership_metrics.scope_filter` + `GROUPS` (pipeline), `api.partnership_expected.expected_rows` / `window_figures` (expected),
a `ranked()` helper extracted from `api.partnership_performance.performance` with no behaviour change (performance),
`university_agreements.effective_status_sql` (agreements), `partnership_targets.team` (targets). No new tables, no schema.

## 5. Frontend

`/partnership/reports` (server page, `TelecallerReportsPage` pattern): a report tab strip (links, `?report=`), a plain GET filter form per
kind (window select / from-to dates / month), the table (`.table compact stack`, labelled region, caption, Total row in `<tfoot>`), a
`role="status"` empty message, the truncation note, and `ReportDownloadButton` for the CSV. The API decides everything shown. Nav:
`PARTNERSHIP_MENU` Reports goes live (managers), head nav and super-admin nav gain "Reports" / "Partnership Reports".

## 6. Errors, edge cases

Empty period / no rows → an empty table message and no CSV button (the CSV route still returns the header row). A 422 is shown above the
form, which keeps the inputs. A 403 is the access card. Unknown `?report=` falls back to `pipeline`.

## 7. Tests

API (`tests/test_upc_031_reports.py`): role matrix (counselor, overseas_admin → 403; unknown kind → 404 for a reader, 403 for a
counselor); 422s; each report reconciles with its source (pipeline totals = `dashboard_figures` overview; expected `this_month` = D13
count/weighted; performance totals = `/partnership/performance` totals; agreements = the menu list's expiring rows for super_admin;
targets total row = `/partnership/targets` team); manager scope; empty period; CSV BOM/header/formula guard/audit row/attachment;
commission columns stripped for a non-U2 role (service level); the CSV cap. Web (vitest): lib URL helpers, the view (columns, empty,
error, totals, filters per kind), nav lists. E2E (Playwright): a head opens each report and downloads a CSV; a counselor is refused.
