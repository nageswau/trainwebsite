# nehn-038 — Agent KPIs: implementation plan

Spec: `docs/superpowers/specs/2026-10-27-nehn-038-agent-kpis-design.md` (`DEC-SCOPE-306`).

## Tasks (TDD: RED → GREEN → REFACTOR per task)

### T1 — Backend KPIs (no date filter)
Write a test first. `tests/test_nehn_038_agent_kpis.py` asserts the new counts on `dashboard_world`, hand computed. The world gets
additions for:
- `submitted_on`
- a refused case
- a withdrawn case
- a refused + approved application, which counts as approved

The test asserts:
- the sum rule (approved + refused + withdrawn = decided);
- conversion counted per student;
- the staff split;
- staff conversions.

Then implement in `services/agent_dashboard.py`, adding schema fields to `AgentDashboardOut` and `AgentStaffRowOut`.

### T2 — Date filter
Test first. Pass `date_from`/`date_to` and check these against a hand-computed cohort:
- all filtered figures;
- the breakdowns;
- the staff rows;
- that pending documents, pending actions and commission are unchanged.

Also cover:
- 422 for a reversed range;
- 403 before 422 for a refused caller;
- staff scope kept;
- the noise agency excluded.

Implement:
- a `created_range()` helper, which `agent_performance.cohort` reuses;
- a cohort clause on applications (exists over `AgentStudent` by `owner_join`);
- the route reads `report_range` after `_gate`.

### T3 — Regression
Re-run these:
- `test_agn_018_*`
- `test_agn_019_*`
- the bdm-022 performance tests (`funnel_columns` users)
- the portal compat test

### T4 — Frontend
Vitest first, in `tests/components/nehn038AgentKpis.test.tsx`:
- the board renders the new tiles and the staff conversion column;
- the filter form keeps its values;
- a range note appears;
- a 422 shows an inline error;
- the skeleton has the new groups.

Then implement in these files:
- `lib/types.ts`
- `lib/agentDashboard.ts` (`dashboardUrl(range)`)
- `AgentDashboardPanel.tsx`
- `PortalPage.tsx` (pass `query`)
- `app/overseas/agent/dashboard/page.tsx`

### T5 — e2e
`tests/e2e/nehn-038-agent-kpis.spec.ts`:
- the Master sees the new tiles;
- applying a range updates the URL and keeps the form;
- a reversed range shows an error;
- there is no horizontal overflow at 375px.

### T6 — Docs
- DEC-SCOPE-306 (with the KPI appendix);
- API §12HD;
- RBAC §2.217;
- RTM;
- the backlog and tracker rows.

## Phase 3 review notes

**API**
- Purely additive: a GET with two optional query params.
- `report_range` reuse gives the same messages and validation order as AGN-014 and AGN-019: guards first, then 422.
- Read-only, with no transaction concerns: one statement per aggregate, as today.
- `Cache-Control: private, no-store` is kept.

**Security**
- No new data class and no ids in the body.
- Scope comes only from membership. A test proves staff can't widen it via params.
- The noise agency is excluded.
- The log line adds `filtered: bool` only, never the dates' owner data.
- No rate-limit change: same cost class as AGN-019.

**Frontend**
- A GET form with labelled date inputs, so it works with the keyboard and without JS.
- The error message uses `role="alert"`.
- The tiles reuse `.kpi-grid`, which is responsive already.
- Loading: the skeleton is shown through the `Suspense` key.
- Empty: tiles show 0, and the rate shows "—".
- The error card is the existing one.
