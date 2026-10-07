# tel-024 — Telecaller management reports (5) + CSV export — design

- **Feature:** tel-024 (`docs/delivery/TELECALLER_CRM_BACKLOG.md`), EVID-019 §21 (source lines 652–686), T24, Appendix B R1–R5.
- **Decision:** `DEC-SCOPE-108` (RP1–RP4, owner answers 2026-10-07, all recommended). API §12AB, RBAC §2.34. **No migration.**
- **Dependencies:** tel-018 (handover/conversion, PR #114) and tel-021 (`services/telecaller_metrics.py`, PR #118) — both merged.
- Numbering: tel-020 is in flight with 0098 / DEC-SCOPE-107 / §12AA / RBAC 2.33, so tel-024 takes the next numbers.

## 1. Owner answers (DEC-SCOPE-108)

| # | Question | Answer |
|---|---|---|
| RP1 | R3 telecaller report basis | **Activity in the range** (Appendix B P2–P6): calls / connected / qualified / appointments logged by the telecaller in the range; conversions credited per tel-021 DB2. Same figures as the tel-021 daily activity summed over the range. |
| RP2 | "Enrolled" in the funnels | **Lead still `converted` now** (DB2). The earlier columns use *stage ever reached* (cumulative rule, DEC-SCOPE-036 D3), so a funnel is monotonic. |
| RP3 | R1 source / R2 product columns | **Leads + Connected, Qualified, Counselling, Enrolled** — the same cohort query as R5. |
| RP4 | R4 counselor handover basis | Leads created in the range **currently with a counselor** (`owner_id`), grouped by the lead's telecaller × its current counselor. A returned lead drops out. |

Q-20 (mask mobile/email in exports) does not arise: every report is an aggregate; no lead name, mobile or email is ever in a row or a CSV.

## 2. Reports

The **cohort** reports (R1, R2, R4, R5) count leads **created** in the range (IST days, `bdm_activities.day_range`), within the caller's
scope and the filters. A lead's *reached index* is the highest `lead_stages.ORDER` index among its current `status` and every
`lead_stage_history.to_stage` (closed outcomes have no index). A lead counts in every column whose stage index ≤ its reached index.

| Key | Title | Rows | Columns |
|---|---|---|---|
| `source` | Lead Source Report | one per `enquiries.source` with ≥ 1 lead (label as `SOURCE_LABEL`; website enquiries are `website`) | Leads · Connected (contacted+) · Qualified (qualified+) · Counselling (counselling_scheduled+) · Enrolled (status `converted`) |
| `product` | Course Report | one per product; leads without a product → "No product" | same |
| `campaign` | Campaign Report | one per campaign; leads without a campaign → "No campaign" | same |
| `handover` | Counselor Handover Report | one per (telecaller, counselor) for leads with `owner_id` set; no telecaller → "Unassigned" | Handed over · Counselling done (counselling_completed+) · Enrolled |
| `telecaller` | Telecaller Report | one per telecaller in scope (inactive ones included, marked) | Calls · Connected · Qualified · Appointments (counselling + BDM requests) · Conversions |

Every report returns a **Total** row. Rows are ordered by the first count descending, then label.

## 3. API (§12AB)

`GET /api/v1/telecaller/reports/{kind}` and `GET /api/v1/telecaller/reports/{kind}.csv` (`.csv` registered first).

Query (all optional, plain strings validated after authorization — the AGN-020 order): `date_from`, `date_to` (ISO dates; default
the 1st of the current IST month → today), `team` (`it`/`overseas`), `product_id`, `campaign_id`, `source`. `telecaller` accepts
only `team` (other filters are ignored for it: activity is per actor, not per lead).

Order of checks: authenticated → role allowed (else **403** "Telecaller reports are for managers and administrators") → kind known
(else **404** "Report not found") → inputs (**422**, FastAPI list shape naming the param: bad date, `date_from > date_to`, a span over
366 days, unknown team/source, malformed UUID).

Response:
```json
{ "kind": "source", "title": "Lead Source Report", "date_from": "2026-10-01", "date_to": "2026-10-07",
  "columns": [{"key": "label", "label": "Source"}, {"key": "leads", "label": "Leads"}, ...],
  "items": [{"label": "Instagram", "leads": 250, ...}], "totals": {"label": "Total", "leads": 250, ...},
  "options": {"teams": ["it","overseas"], "sources": [...], "products": [{"id","name"}], "campaigns": [{"id","name"}]} }
```
`Cache-Control: private, no-store`. Reads are not audited. The CSV (UTF-8 BOM, on-screen labels as header, Total row last, cells
through `_safe_cell` against CSV injection — `agent_reports.to_csv` reused) writes one `AuditLog` `telecaller_report.export`
(entity `telecaller_report` / kind; metadata: which filters were set and the row count) committed before the file is returned.
Filename `telecaller-{kind}-{from}-to-{to}.csv`.

## 4. Scope (T24, RBAC §2.34)

| Role | Leads counted (cohort) | Telecallers listed (R3) |
|---|---|---|
| `telecaller_manager` | `lead_pipeline.scope` — direct reports' leads + unassigned leads of their teams (exactly the manager Leads list) | direct reports |
| `it_admin` / `overseas_admin` | `enquiries.division = own division` (exactly the admin Leads list) | telecallers of that team |
| `super_admin` | all (optional `team`) | all |
| `telecaller` and every other role | **403** (§22 "telecaller should not view confidential management reports") | — |

The `team` filter is ANDed with the scope (it can only narrow). Options list products and campaigns (active and inactive — old leads
keep them) of the teams in scope.

## 5. Backend design

- `services/telecaller_metrics.py`: add `flow_counts_by_user(db, user_ids, start, end) -> dict[UUID, dict]` — the same counts as
  `flow_counts`, each one grouped by actor in one query; `flow_counts` becomes a one-user call of it (single source of truth kept;
  tel-021 tests guard it). `conversions` becomes grouped by `owner_at(first conversion)` the same way.
- `services/telecaller_reports.py` (new): `REPORTS` spec dict, `parse_filters`, `lead_scope(user)`, the cohort query (one grouped
  SELECT with a correlated `max(rank(to_stage))`), `telecaller_rows`, `options`, `report(...)`.
- `api/telecaller_reports.py` (new router, registered in `main.py`).
- Read-only; no transaction concerns beyond the export's audit commit.

## 6. Frontend

- `components/TelecallerReportsPage.tsx` (server component): tabs as links (`?report=source&...`, `aria-current="page"`), a GET
  filter form (From, To, Team when the caller can pick, Product, Campaign, Source — the last three hidden on the Telecaller tab),
  the table (`<table>` in `.table-wrap`, Total row in `<tfoot>`), empty state "No leads in this range.", an error state for a refused
  or failed read, and `ReportDownloadButton` (CSV) for the same query.
- Routes: `/telecaller/manager/reports` (manager, super_admin), `/it/admin/telecaller-reports`, `/overseas/admin/telecaller-reports`,
  `/admin/telecaller-reports` (super_admin). Nav: "Reports" in `TELECALLER_MANAGER_NAV`; "Telecaller Reports" in the IT / Overseas
  admin and super admin navs.
- `lib/telecallerReports.ts`: types, tab list, URL builders.

## 7. Acceptance criteria

1. Each cohort report's Total leads equals the matching lead list's total for the same scope and filters (manager: `/telecaller/leads`; admin: `/admin/leads`).
2. Funnel columns are monotonic per row (Leads ≥ Connected ≥ Qualified ≥ Counselling ≥ Enrolled); a lead that jumped stages counts in each one it passed; an unlinked (no longer converted) lead is not Enrolled.
3. Telecaller → 403 on every kind and on the CSV; unknown kind → 404 (for an allowed role).
4. R3 per telecaller equals the sum of tel-021 daily activity counts over the range.
5. Leads without a campaign/product appear as "No campaign"/"No product"; website enquiries under `website`.
6. A manager sees only their scope; a division admin only their division; a `team` filter can only narrow.
7. CSV export: BOM + header + rows + Total, formula cells neutralised, one audit row, `text/csv`.
8. 422 on bad dates, reversed range, span > 366 days, bad team/source/UUID.

## 8. Risks

- `telecaller_metrics` refactor touches the dashboard/activity — guarded by the tel-021 tests (run them).
- Correlated stage subquery on large ranges: bounded at 366 days; `ix_lead_stage_history_lead` covers the lookup. A rollup only if measured slow.
