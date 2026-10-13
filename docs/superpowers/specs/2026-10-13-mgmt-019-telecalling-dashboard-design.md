# mgmt-019 — Telecalling dashboard, company-wide (design)

Date: 2026-10-13 · Backlog: `docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` mgmt-019 · Source: `EVID-017` §14 lines 537–559
(`DERIVED_BLUEPRINT`), scope authority M13 (`EXPLICIT_APPROVAL`, 2026-10-08, registered as `DEC-SCOPE-186`).
Dependency mgmt-003: merged to `main` (PR #244). No migration.

## 1. What the item asks for

§14 "Track": Leads assigned, Calls attempted, Connected, Interested, Follow-up, Appointment, Converted, Lost; "Telecaller conversion";
"Calls → Interested → Counseling → Registration".

Backlog: company-wide figures + per-team, reusing `telecaller_metrics.flow_counts_by_user` over all telecallers; a thin wrapper;
`GET /management/telecalling`; operational tier (partner, super_admin); no database change. **Acceptance criterion (AC1): totals equal the
sum of the tel-023 rows.**

## 2. Discovery (Graphify + code, `main@ed0c9d1c`)

| Class | Items |
|---|---|
| MUST CHANGE | new `services/management_telecalling.py`; `api/management.py` (`GET /management/telecalling`); `schemas.py` (`TelecallingOut`); web new `lib/managementTelecalling.ts`, `components/ManagementTelecalling.tsx`, `app/management/telecalling/page.tsx`; `lib/management.ts` (the two mgmt-019 entries get their `href`) |
| MAY CHANGE | `API_CONTRACT.md`, `RBAC_MATRIX.md`, `PRODUCT_DECISION_REGISTER.md`, backlog status line |
| SHOULD NOT CHANGE | `telecaller_metrics.py` (`flow_counts_by_user`, `leads_received` reused read-only), `telecaller_performance.py` (`date_range` reused; `performance()` is the AC1 oracle), `telecaller_reports.py`, `lead_stages.py` |
| HIGH REGRESSION RISK | `MANAGEMENT_PILLARS` (mgmt-001 nav tests read it dynamically); `/telecaller/manager/performance` must stay byte-identical |

Data: `lead_calls`, `lead_follow_ups`, `appointments`, `bdm_meeting_requests`, `lead_stage_histories` (`to_stage`, `actor_user_id`),
`audit_logs` (`lead.assign` / `lead.create`), `telecaller_profiles.team` (`it` / `overseas`).

**Finding:** `flow_counts_by_user` has no "Interested" or "Lost" count. They are added in the new service (one grouped query over
`lead_stage_histories`, the same shape as tel-021's Qualified D11), so `telecaller_metrics` is not widened.

## 3. Decisions (recommended answers, owner's standing instruction to proceed with recommended answers; `UNVERIFIED`)

| # | Point | Decision |
|---|---|---|
| TC1 | Population | Every `telecaller` user with a telecaller profile, both teams, active and inactive (inactive rows labelled) — tel-023's super_admin scope |
| TC2 | Period | `date_from` / `date_to` as IST days; default the 1st of this month → today; ≤ 366 days, never in the future; tel-023's `date_range` and its 422 wording |
| TC3 | Leads assigned | tel-023 P1 `leads_received`: distinct leads that became the telecaller's in the period |
| TC4 | Calls attempted / Connected | tel-021 D2 / D3 (`calls`, `connected_calls`) |
| TC5 | Interested | Stage moves to `interested` recorded by the telecaller in the period (events, like D11 Qualified) |
| TC6 | Follow-up | Follow-ups completed by the telecaller in the period (tel-021 D5) |
| TC7 | Appointment | tel-021 D7 `new_appointments` (counselling bookings + BDM meeting requests) |
| TC8 | Converted | tel-021 D13 / T5 `converted_leads` (credited to the owner at conversion, still converted now) |
| TC9 | Lost | Stage moves into any closed outcome (Not Interested, Not Eligible, Wrong Number, No Response, Lost) recorded by the telecaller in the period |
| TC10 | Telecaller conversion | Converted ÷ Leads assigned × 100, one decimal; `null` ("—") when no leads were assigned. Per telecaller, per team, company |
| TC11 | Chain | Calls → Interested → Counseling (D8 counselling appointments booked) → Registration (Converted). Activity in the period, so each step shows its count and its share of the previous step (`null` when the previous is 0); not a cohort funnel |
| TC12 | Breakdown | Company totals; per team (IT, Overseas; both always listed); per telecaller table ordered by name. Every total is the sum of its rows (AC1) |
| TC13 | Access | Operational tier: partner, super_admin. Accountant 403 "Operational access required"; any other role 403 "Management access required"; signed out 401 |
| TC14 | Privacy | Counts and staff names only; no lead names, phones or emails |
| TC15 | Page | `/management/telecalling`: GET date form (URL-held), eight KPI tiles + conversion, the chain, a team table and a telecaller table (`#telecallers`). Sales "Leads & calls" → the page; People "Telecallers" → `#telecallers`. super_admin keeps `SUPER_ADMIN_NAV` |
| TC16 | Query shape | `flow_counts_by_user` (fixed grouped queries for all telecallers), one grouped stage-history query (Interested + Lost), `leads_received` per telecaller (as tel-023) |

## 4. Design

Backend
- `services/management_telecalling.py`: `KPIS` (ordered key/label), `dashboard(db, first, last) -> dict`. Reads people, calls
  `flow_counts_by_user`, `_outcomes()` (grouped Interested/Lost), `leads_received`; builds rows, team totals, company totals, chain.
- Route `GET /management/telecalling?date_from&date_to`: `require_management` → operational check → `telecaller_performance.date_range`.

Frontend
- `lib/managementTelecalling.ts`: types, `telecallingFilters(search)` (drops malformed dates), `telecallingUrl`, `telecallingHref`,
  `percentText`.
- `components/ManagementTelecalling.tsx`: form, KPI tiles (`snapshot` tile styles), chain list, two tables (`table-wrap`).
- Page: 401/403 → access card; 422 → its message; other errors → "unavailable".

Error/empty states: no telecallers → tables show an empty note; zero activity → zeros, conversion "—".

## 5. Tests

- pytest `test_mgmt_019_telecalling.py`: each KPI per its definition for test-made telecallers; inactive labelled; team and company totals
  = sums of rows; AC1 totals = tel-023 `performance()` totals for the same range; access (partner 200, super_admin 200, accountant 403,
  telecaller_manager 403, signed out 401); range 422s; default period.
- vitest: lib helpers; component renders tiles, chain, tables, empty and error states; nav entry live.
- Playwright e2e `mgmt-019-telecalling.spec.ts`: partner opens the page from the Command Center, applies a range, refresh keeps it.
