# mgmt-020 — BDM dashboards (agent / school / college) — design

- **Feature:** `mgmt-020` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-020). Depends on mgmt-003 (PR #244, merged on `main`).
- **Evidence:** `EVID-017` §16 "BDM DASHBOARD" (lines 595–647, `DERIVED_BLUEPRINT`): "Separate:" Agent BDM (9 figures), School BDM
  (7), College BDM (6). Management M1/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`: operational tier = partner + super_admin);
  bdm-024 (`DEC-SCOPE-113`: P-01…P-08 and the master view V-A / V-S / V-C); bdm-015/016 (`DAILY_METRICS`, `TARGET_METRICS`);
  bdm-019 (agent onboarding links).
- **Decision:** one new DEC-SCOPE (number taken at merge). BD1–BD12 answer Q-21 and the open points of the backlog item with
  **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

Management sees, company-wide, one tab per BDM type with that type's §16 figures for a period. Read-only and nothing is stored: every
figure is a bdm-024 total (the super admin's all-teams view for the same period) or an existing bdm-015/016 rule applied to every
BDM of the type.

## 2. Decisions (BD1–BD12)

| # | Point | Answer |
|---|---|---|
| BD1 | Scope | Company-wide: every BDM (active or not), as the super admin's bdm-024 "All BDM teams" view. A figure belongs to the type of the BDM who owns the record (bdm-024 P-columns) |
| BD2 | Period | `from` / `to` (inclusive IST dates), each defaulting to the current IST month; start after end or more than 366 days → `422` (bdm-024 P2, the same function) |
| BD3 | Type | `type` = `agent` (default) / `school` / `college`; anything else `422` |
| BD4 | Period figures equal to bdm-024 (AC) | Prospects / School leads = P-04 New Organizations; Meetings = P-02; Agreements / MoUs = P-05; Agent students / Students / Student registrations = P-07 — the bdm-024 cell of that type for the same period |
| BD5 | Live figures equal to bdm-024 (AC) | Agent Applications and Enrollments = the master view's (V-A) all-time type totals, as of now |
| BD6 | Visits | Visits the type's BDMs logged in the period (activity channel "visit", the bdm-015 School visits rule) |
| BD7 | Proposals | MoUs the School BDMs moved to Proposal Sent in the period (bdm-015/016 rule) |
| BD8 | New agents | Agent organizations whose onboarding request was completed (linked to an agency, bdm-019) in the period |
| BD9 | Active agents | Now: non-archived Agent organizations linked to an agency whose status is active |
| BD10 | Active schools | Linked schools with a tier still valid at the period's end — today while the period runs (bdm-016 M-17 over every School BDM) |
| BD11 | Q-21 | Course promotions are tracked: course promotion appointments the College BDMs completed in the period (the bdm-016 KPI). Internships are **not tracked** (nothing records them) and show "Not tracked", never 0 |
| BD12 | Access + nav | Operational tier: partner and super_admin `200`; accountant `403` "Operational access required"; any other role `403` "Management access required"; signed out `401`. The Command Center "BDM" entry goes live; the super admin's own sidebar (MG10) gets "Management BDM figures" |

## 3. API

`GET /management/bdm?type&from&to` → `200`
`{type, label, from, to, as_of, bdm_count, figures[{key, label, definition, basis: "period"|"now", tracked, value}]}`, figures in §16
order. `bdm_count` = P-01 (active BDMs of the type). `value` is `null` when `tracked` is false.

## 4. Web

`/management/bdm` (server-rendered): three link tabs (Agent BDM / School BDM / College BDM, `aria-current="page"`, the tel-024 strip);
the bdm-024 period form (GET, keeps `type`); two tile groups, "In the period" and "Right now", each tile showing its definition; a
not-tracked tile reads "Not tracked". 401/403 → access card; 422 → its message with "Show this month".

## 5. Tests

- Backend `test_mgmt_020_bdm_dashboards.py`: access per role; 422s; the §16 keys per type; AC — every BD4/BD5 figure equals the
  super admin's `GET /bdm/manager/performance` / `hierarchy` read in the same test; BD6–BD11 as before/after deltas on a past period;
  internships not tracked.
- Regression: `test_bdm_015_*`, `test_bdm_016_*`, `test_bdm_023_dashboard.py`, `test_bdm_024_*` (shared builders and totals).
- Web: `managementBdm.test.ts`, `ManagementBdm.test.tsx`, nav tests; e2e `mgmt-020-bdm-dashboards.spec.ts`.

## 6. Risks

`bdm_metrics._activities` / `_linked_schools` learn to take a team sub-select (as `_owned` already does); a single BDM id compiles to
the same SQL. bdm-024's per-type summing moves into `bdm_performance.type_totals`, called by both routes, so the totals cannot drift.
