# bdm-024 — BDM performance by type + drill-down + master dashboard (design)

Decision: `DEC-SCOPE-111` (P1–P12 below). Backlog: `BDM_CRM_BACKLOG.md` §bdm-024; definitions Appendix B.6 (P-01…P-08,
V-A/V-S/V-C). Evidence: `EVID-016` §5 Management view (lines 1336–1357) and §6 Master dashboard (lines 1359–1420)
(`DERIVED_BLUEPRINT`); scope approved under `DEC-SCOPE-055` D1.

**Status of the P-answers:** agent-recommended defaults, **not** `EXPLICIT_APPROVAL`. The owner told this session to "proceed with
recommended answers" and ask only on genuine blockers. Every answer is `NEEDS_CONFIRMATION` at sign-off, and the owner may override any of them.

## 1. Dependencies (hard-stop check, 2026-10-07, `main` @ `8b6d4dbe`)

| Item | State | Used for |
|---|---|---|
| bdm-020 School activity | merged, VERIFIED (full regression deferred) | V-S Career/University = the panel's Career Guidance figure |
| bdm-021 College business | merged, VERIFIED (full regression deferred) | V-C, P-07/P-08 College rules |
| bdm-022 Agent performance | merged, COMPLETE WITH DEFERRED FULL REGRESSION | V-A (`funnel_columns`), P-07 Agent |
| bdm-023 Management dashboard | merged, COMPLETE WITH DEFERRED FULL REGRESSION | team scope + super_admin manager filter |

## 2. Scope

In scope: `GET /bdm/manager/performance` (the KPI × type table; with `type`, the BDMs of that type), `GET /bdm/manager/performance/bdms/{id}`
(one BDM's organizations and trips), `GET /bdm/manager/hierarchy` (the master view), four pages, and the nav entries.
Out of scope: writes, caching, export, new tables, migrations, and changes to existing list pages.

## 3. Decisions (recommended defaults)

| # | Question | Default |
|---|---|---|
| P1 | Who reads | `bdm_manager` (own team) and `super_admin` (all teams, or one manager with `manager_user_id`). Same scope, errors and validation as bdm-023 R1–R3 (the scope helper is shared) |
| P2 | Period | `from` / `to` are IST dates and both ends are inclusive. Each defaults to the current IST month's first or last day. `from > to` returns `422` "The period must start on or before its end". A span over 366 days returns `422` "The period can be at most 366 days" (bounds the heaviest aggregation) |
| P3 | Type and team attribution | There is **no history** of a BDM's type or manager, so the BDM's **current** profile type and manager apply to every record. A record counts for the BDM who owns it: appointment `bdm_user_id`, trip `bdm_user_id`, MoU event `actor_user_id`, enquiry `bdm_user_id`, organization `created_by_user_id`. The backlog's "as of each record's date" is not possible without history (`NEEDS_CONFIRMATION`) |
| P4 | Deactivated BDMs | Their records still count (backlog: "included historically"). P-01 counts **active** BDMs only (Appendix B). The BDM list shows inactive BDMs with an "Inactive" label |
| P5 | Students (P-07), period-bound ("bdm-024 owns periods", `DEC-SCOPE-086` B4) | Counted through the organizations **currently assigned** to the BDM, using each organization's module rule. **Agent:** active agent students created in the period in the linked agency (A-01's population). **School:** M-22, students created in the period in the linked School. **College:** attributed users whose lead was converted in the period (F-3's population, by `converted_at`) |
| P6 | Revenue (P-08) | **College:** R-1's rule (paid, INR, not an agent deposit) over the payments of the organization's attributed users, **recorded in the period** (`payments.created_at`; there is no paid-at column). **Agent / School:** "Not tracked" (D17) |
| P7 | Other P-rows | P-02 = M-06, P-03 = trips with `travel_date` in the period that are not cancelled or rejected (T-M05's rule), P-04 = M-14 for any organization type, P-05 = M-11, P-06 = M-12 |
| P8 | Drill-down | L1 type table → L2 the BDMs of a type (`/bdm/manager/performance/{type}`) → L3 one BDM's organizations and trips (`/bdm/manager/performance/bdms/{id}`) → L4 the organization page (`/bdm/manager/organizations/{id}`: its appointments with outcomes, leads, and the bdm-020/021/022 panels) and the trip page. All figures are computed once at (BDM, organization) grain and then summed, so L1 = ΣL2 = ΣL3 by construction (AC2) |
| P9 | L4 period | The organization page and its panels are all-time (bdm-020/021/022 B4). L3 says that its row counts only the period |
| P10 | Master view | `/bdm/manager/hierarchy`: live and all-time (the same figures as the organization panels). Type → BDMs → **linked** organizations (Agent `agent_org_id`, School `school_id`, College: every College-module organization), each with its value-chain counts. BDM and type totals are sums. Unlinked organizations are counted ("2 not onboarded yet"), not listed. Only non-archived organizations whose module equals the BDM's type are included |
| P11 | Value chains | **V-A:** Students (A-01) → Applications (A-02) → Enrollment (A-05) → Revenue (not tracked). **V-S:** Students (S-01) → Profile Building (not tracked) → Career/University (S-02, the bdm-020 Career Guidance figure) → Future Student (distinct students with an `overseas_applications` row, `DEC-SCOPE-018`). **V-C:** Students (F-3) → Training (F-4) → Internship (not tracked) → Placement (F-7) → Revenue (R-1, INR) |
| P12 | Navigation | Manager sidebar: "Performance" and "Master view". super_admin sidebar: "BDM Performance" and "BDM Master View" |

## 4. API

`GET /api/v1/bdm/manager/performance?from=&to=[&type=agent|school|college][&manager_user_id=]` → `200`

```json
{"from": "2026-10-01", "to": "2026-10-31", "manager": null,
 "rows": [{"key": "P-01", "label": "BDMs", "cells": [{"type": "agent", "tracked": true, "value": 3, "definition": "…"}]}],
 "type": "agent" | null,
 "bdms": [{"id": "…", "full_name": "…", "active": true, "figures": {"meetings": 4, "trips": 1, "new_organizations": 2, "mous": 0,
            "leads": 9, "students": 3, "revenue": null}}]}
```

`rows` follows P-01…P-08 in order, with columns Agent, School, College. A `value` is an integer, or for P-08 a decimal string in INR.
An untracked cell has `tracked: false` and `value: null`. `bdms` is empty unless `type` is given. It is sorted by name and its sums equal
the type's cells.

`GET /api/v1/bdm/manager/performance/bdms/{bdm_user_id}?from=&to=` → `200` `{from, to, bdm: {id, full_name, active, bdm_type},
totals: figures, organizations: [{id, code, name, figures}], trips: [{id, code, from_place, to_place, travel_date, approval_status,
travel_status}]}`. A BDM outside the caller's team (or an id that isn't a BDM) returns `404` "BDM not found". An organization row's
`trips` is `null`, because trips belong to the BDM. Organizations are listed only when one of their figures is non-zero, ordered by name.

`GET /api/v1/bdm/manager/hierarchy[?manager_user_id=]` → `200` `{manager, as_of, types: [{type, label, chain: [{key, label, definition,
tracked}], bdm_count, organization_count, not_linked, totals: [int|str|null], bdms: [{id, full_name, active, organization_count,
not_linked, totals, organizations: [{id, code, name, counts}]}]}]}`.

Read-only: no write, no audit, no log line. Query count is constant per request: one profile list, about 10 grouped statements for
performance, and fewer than 15 for the hierarchy. Only aggregates and organization or trip identities leave the server. No student
or payment rows are returned.

## 5. Module layout

- `app/services/bdm_performance.py` (new): the period window, grouped (BDM, org) figures, and the hierarchy builders.
- `app/api/bdm_performance.py` (new): the three routes, sharing bdm-023's scope helper (renamed `team_scope`).
- `app/services/bdm_metrics.py`: `college_business` gets its scalar subqueries from a `college_columns(org_id)` builder. The hierarchy
  calls it with the correlated `BdmOrganization.id`, so the panel and the master view use the same SQL. Behavior is unchanged.

## 6. Web

- `lib/bdmPerformance.ts`: types, guards, URL and query builders that keep `from`, `to` and `manager`, value formatting
  ("Not tracked", INR), and type labels.
- `components/BdmPerformanceTable.tsx` (L1), `components/BdmPerformanceFigures.tsx` (L2/L3 shared rows × figures table),
  `components/BdmHierarchy.tsx` (native `<details>`, keyboard-accessible).
- Pages: `app/bdm/manager/performance/page.tsx`, `[type]/page.tsx`, `bdms/[id]/page.tsx`, `app/bdm/manager/hierarchy/page.tsx`, each
  with `loading.tsx`. Each page has a GET period form, plus a manager `<select>` for super_admin. An error from the API is shown inline
  with "Try again" and "Show this month". Tables sit in `.table-scroll`, so phones get no horizontal page scroll (AC5).

## 7. Security

Scope always comes from the session. `manager_user_id` is super_admin only. A BDM id outside the team returns 404, so there is no IDOR.
Revenue is shown only to managers and super_admin, the only callers allowed. No contact, student, or payment details are returned.
No new dependency.

## 8. Tests

Backend `tests/test_bdm_024_performance.py`: roles (BDM 403; manager 200; super_admin all and filtered; 422/404 as in bdm-023); the
period validation; each P-row against seeded rows plus near misses (outside the period, another team, a cancelled trip, a refunded
payment, an agent deposit); L1 = ΣL2 = ΣL3; type filter; the BDM detail 404 for another team; the inactive BDM counted but not in P-01;
hierarchy chains equal to the bdm-021/022 panel figures and the bdm-020 Career Guidance figure; unlinked organizations counted, not listed;
`college_business` unchanged (the existing bdm-021 tests). Web: lib unit tests, component tests, and page tests. Playwright
`tests/e2e/bdm-024-performance.spec.ts`: a seeded manager sees the table, drills type → BDM → organization page, the period filter
changes the figures, the master view lists the organization, and phone width has no overflow.
