# bdm-024 Performance + Master View Implementation Plan

> **For agentic workers:** executed inline (Native) under the owner's standing direction. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the period-selectable KPI × BDM-type table with its drill-down (type → BDM → organization) and the master view
(type → BDM → linked organization → value chain) for managers and super_admin.

**Architecture:** A new service `app/services/bdm_performance.py` computes every period figure once at (BDM, organization) grain
using grouped statements; the routes in `app/api/bdm_performance.py` sum those figures into each level, so the levels always agree.
The master view reuses the panel SQL: `bdm_metrics.college_columns(org_id)` and `agent_dashboard.funnel_columns` are correlated
on `BdmOrganization`, and the School figures come from `school_analytics.student_indicators`.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest (Docker api container); Next.js App Router server components, Vitest,
Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-bdm-024-performance-master-design.md`

## Global Constraints

- Read-only. No migration, no new dependency, no cache.
- "Not tracked" is a label (`tracked: false`, `value: null`), never 0.
- Periods use IST dates, inclusive at both ends. The default is the current IST month. `from > to` → 422; a span over 366 days → 422.
- Scope: `bdm_manager` sees their own team. `super_admin` sees all teams, or one manager's via `manager_user_id`. Any other role → 403.
- No student, contact or payment rows in any response.
- Phone width: no horizontal page scroll (tables live in `.table-scroll`).

## Review Focus

- A BDM whose type has no BDMs: the column shows 0 / "Not tracked", never crashes → test the empty team and one-type-only team.
- A revenue sum with no payments must be "0.00", not null, for College → assert in the service test.
- `to` given before the default `from` (e.g. `to=2026-09-01` only) → 422 with the period message → API test.
- A manager opening another team's BDM detail by URL → 404 → API test.
- An organization reassigned to another BDM: students follow the current assignee, meetings stay with their owner → service test.

---

### Task 1: Shared scope + college column builder (refactor, no behavior change)

**Files:** Modify `apps/api/app/api/bdm_manager_dashboard.py` (`_scope` → `team_scope`), `apps/api/app/services/bdm_metrics.py`
(`college_columns(org_id)` extracted from `college_business`). Test: the existing `tests/test_bdm_023_dashboard.py` and
`tests/test_bdm_021_*` must stay green.

- [ ] Extract `college_columns(org_id) -> dict[str, ScalarSelect]` with the keys `leads, registrations, training, certification,
  placement, fees`. `college_business` selects `college_columns(org.id)`.
- [ ] Rename `_scope` → `team_scope` and update its one caller.
- [ ] Run bdm-021 + bdm-023 tests → PASS. Commit.

### Task 2: Performance service + `GET /bdm/manager/performance`

**Files:** Create `apps/api/app/services/bdm_performance.py`, `apps/api/app/api/bdm_performance.py`; modify `apps/api/app/schemas.py`,
`apps/api/app/main.py`. Test: `apps/api/tests/test_bdm_024_performance.py`.

**Produces:** `period(from_, to) -> (date, date, datetime, datetime)`; `async figures(db, team: Select, start, end) ->
dict[(bdm_id, org_id|None), dict[str, int|Decimal]]`; `FIGURES = ("meetings","trips","new_organizations","mous","leads","students","revenue")`;
`async team_members(db, team) -> list[Row(id, full_name, active, bdm_type)]`.

- [ ] RED: tests for roles, period defaults and validation, P-01…P-08 per type with near misses, `type=` returning BDM rows whose
  sums equal the cells, inactive BDM counted in figures but not in P-01, revenue not tracked for Agent/School.
- [ ] GREEN: grouped statements: meetings (`_completed`), trips (T-M05 rule over `travel_date`), new orgs (`created_by_user_id`), MoUs
  (MoU events → signed, grouped by event actor and the MoU's organization), leads (enquiries `bdm_user_id`, `bdm_organization_id`), students
  (three rules grouped by `assigned_bdm_user_id`, org), revenue (College only).
- [ ] Run → PASS. Commit.

### Task 3: `GET /bdm/manager/performance/bdms/{id}`

- [ ] RED: an own team BDM → organizations whose figures sum to totals and to that BDM's L2 row; trips listed; another team's BDM → 404;
  a non-BDM id → 404; super_admin → any BDM.
- [ ] GREEN, run, commit.

### Task 4: `GET /bdm/manager/hierarchy`

- [ ] RED: chains per type; an org's counts equal `college_business` / `agent_performance` / the bdm-020 Career Guidance figure for that org;
  unlinked orgs counted in `not_linked` but not listed; archived orgs excluded; BDM and type totals are sums; team isolation.
- [ ] GREEN (correlated `college_columns(BdmOrganization.id)`, `funnel_columns` with `members_of(BdmOrganization.agent_org_id)`,
  `student_indicators` + one student→school map + a future-student grouped count), run, commit.

### Task 5: Web lib + components (Vitest)

**Files:** `apps/web/lib/bdmPerformance.ts`, `components/BdmPerformanceTable.tsx`, `components/BdmPerformanceFigures.tsx`,
`components/BdmHierarchy.tsx` + `*.test.ts(x)`.

- [ ] RED: URL/query builders keep `from`/`to`/`manager`; `valueText` ("Not tracked", INR, en-IN numbers); guards; table cells link
  to the next level; untracked cells are not links; L3 org rows link to the org page and trips to the trip page; hierarchy renders
  chains, "Not onboarded yet" counts and the empty state.
- [ ] GREEN, run, commit.

### Task 6: Pages + nav

**Files:** `apps/web/app/bdm/manager/performance/{page,loading}.tsx`, `[type]/{page,loading}.tsx`, `bdms/[id]/{page,loading}.tsx`,
`apps/web/app/bdm/manager/hierarchy/{page,loading}.tsx`, `lib/navigation.ts`.

- [ ] RED: page tests (super_admin nav + manager select, manager nav, error state with "Try again", invalid type → notFound).
- [ ] GREEN, run, `tsc`, eslint, commit.

### Task 7: Playwright + docs

- [ ] `tests/e2e/bdm-024-performance.spec.ts` (seed through the API as bdm-023's spec; drill type → BDM → org page; period change; master
  view; 390 px with no overflow).
- [ ] Docs: decision register `DEC-SCOPE-111`, API §12AE, RBAC §2.37, RTM row, backlog status, QA report.
