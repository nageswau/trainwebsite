# mgmt-023 — University partnership dashboard (design)

**Feature:** `mgmt-023` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-023; EVID-017 `Management Functionalities.md` §19, L717–L785).
**Depends on (merged):** mgmt-003 (#244), upc-018 (#203), upc-022 (#225), upc-023 (#218), upc-029 (#229).
**Status of the answers below:** recommended defaults (UD1–UD14) applied under the owner's standing instruction for the build session
("proceed with recommended answers"). They answer Q-24 for this item. `UNVERIFIED` — `NEEDS_CONFIRMATION` at sign-off.

## Intent

Management (partners, and super_admin without money) gets one global view of university partnerships: the twelve §19 KPIs, the 8-step
§19 pipeline, and "which universities are expected to be signed next month?". It is a read-through of the UPC figures, so its totals
equal upc-029's global dashboard for the same period. Nothing is stored; no migration.

## Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| UD1 | Readers | Operational tier (M13): `partner`, `super_admin`. `accountant` and every other role `403`; signed out `401` |
| UD2 | Scope | Every active university (upc-018 PF6: both readers are global, so the figures equal upc-029's super_admin view) |
| UD3 | Period | `from` / `to` (IST days, default this IST month to date), upc-018 PF1 rules: start ≤ end, at most 366 days, else `422`. The period drives Applications, Enrollments and Revenue only; everything else is "now" |
| UD4 | Universities identified | upc-029 `pipeline.total` (= upc-022 D1): every active university in the master, lost/closed included |
| UD5 | Contacted · Meetings · Negotiations · MoUs · Signed | Not lost, and currently **at or past** the §19 step: Contacted = steps Contacted…Active Partner; Meetings = Meeting…; Negotiations = Negotiation…; MoUs = Agreement…; Signed = Signed + Active Partner. Each is a sum of upc-029 pipeline steps, so the KPIs never contradict the pipeline |
| UD6 | Active | upc-029 `active.count` (Appendix B G1 = upc-022 D2) |
| UD7 | Exclusive | Active, not-lost universities with an in-force exclusive agreement now (upc-025 MP8 `exclusive` rule: signed/active, not past expiry) |
| UD8 | Countries | Countries with at least one active partner (`len(upc-029 active.countries)`) |
| UD9 | Applications · Enrollments | upc-018 F5 / F9 totals for the period (= upc-029 `funnel.totals.applications` / `enrolled`) |
| UD10 | Revenue | upc-019 F11 university commission **received** in the period, per currency (no FX), with F10 expected beside it. **Partner only** (M3 via `can_view_university_commission`, mgmt-006 MG11). super_admin and everyone else get no `revenue` key at all (M13: no finance figures) |
| UD11 | Pipeline | upc-029 `pipeline` (Management §19 mapping, Appendix B / GD13): 8 steps, `lost` aside, total |
| UD12 | Expected Partnership Date | upc-023 E1–E4 windows (this month, next month, this quarter: count + weighted) and the **next month** list (upc-023 EX12 order: expected date, then name), first 25 rows with the total |
| UD13 | Links | None into `/partnership/*` (partners cannot open the UPC module); the page is self-contained |
| UD14 | Page / nav | `/management/universities`; Command Center Partnerships → "Universities" goes live (operational); super_admin nav "Management university figures" |

`partnership_access.COMMISSION_ROLES` is unchanged (MG2): partners gain no partnership-module commission route. To give partners the
F10/F11 sums without the U2 gate, `partnership_performance.commission_by_university` is split into an un-gated `commission_sums` it
calls after its own check (behaviour unchanged).

## API

`GET /api/v1/management/universities?from=&to=` → `ManagementUniversitiesOut`
`{today, from, to, kpis: [{key, label, value}] ×11 (source order, Revenue excluded), revenue?: {expected, received},
pipeline: GlobalPipeline, expected: {windows: ExpectedWindow[], next_month: {total, items: ExpectedUniversity[]}, undated}}`.
`response_model_exclude_unset=True` drops `revenue` for super_admin. Read-only; not audited; a fixed number of statements.

## Backend

`services/management_universities.py: dashboard(db, user, first, last, today)` composes `global_figures`, `ranking`,
`commission_sums` (partners), one exclusive count and `expected_rows` / `window_figures` / `chosen_rows`. Route appended in
`api/management.py` with `require_operational`.

## Frontend

`app/management/universities/page.tsx` (server, as mgmt-021), `components/ManagementUniversities.tsx`, `lib/managementUniversities.ts`.
GET period form keyed on the href; KPI tiles (Revenue tile only when present); pipeline as an ordered list; expected windows tiles and a
next-month table (empty state "No universities are expected to sign next month."). Error: API 422 text, or an "unavailable" notice.

## Tests

Backend: access (401, accountant/other 403, partner/super_admin 200), 422 periods, super_admin has no `revenue` key and partner has it,
totals equal `/partnership/global-dashboard` (super_admin) for the same period, each UD5/UD7 definition by delta on fresh universities,
next-month list contents. Web: lib unit tests, component tests (tiles, no Revenue for super_admin, empty states), e2e spec for partner,
super_admin and accountant.
