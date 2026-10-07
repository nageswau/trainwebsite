# bdm-022 Agent performance drill-down — implementation plan

Spec: `docs/superpowers/specs/2026-10-07-bdm-022-agent-performance-design.md` (DEC-SCOPE-109). TDD per task; focused tests only.

## Phase 3 review notes (folded in)

- **API:** read-only `GET`, additive route; 403 (role) before 404 (scope / missing / non-Agent) — `load_scoped` already orders these;
  the unlinked case is a normal 200 with `linked: false` (not an error). No pagination: the payload is fixed-size. `extra` fields
  impossible (response model). No ETag/idempotency contract needed.
- **Frontend:** reuse `pipeline-funnel` markup (bdm-021) and `action-card wide`; counts are text, bars `aria-hidden`; the stage
  disclosure is a real `<button aria-expanded aria-controls>`; the table has a caption; status flag is text, not colour alone; error
  state `role="alert"` with Try again; responsive via existing `.table-scroll`.
- **Security:** IDOR — `load_scoped` (scope = 404); no student/member/application rows; no money; logs carry ids only; no new input
  beyond a UUID path parameter (FastAPI validates → 422).

## Tasks

1. **Shared definitions (refactor, RED = AGN-018 tests stay green + new parity test).** `agent_dashboard.funnel_columns(student_where,
   application_where)`; `headline_counts` uses it. Rerun `test_agn_018_*`, `test_agn_019_*`.
2. **Service + schema + route (RED first):** `tests/test_bdm_022_agent_performance.py` — parity, offers, visa, stage breakdown,
   revenue not tracked, unlinked, suspended, 404 non-agent / other module / outside team, 403 other role, no PII. Then
   `bdm_metrics.agent_performance`, `BdmAgentPerformanceOut`, the route.
3. **Web lib + component (RED first):** `BdmOrganizationAgentPerformance.test.tsx`; then `lib/bdmAgentPerformance.ts`,
   `lib/bdmAgentPerformanceServer.ts`, the component.
4. **Wire pages:** both organization pages + `BdmOrganizationDetail` prop `agentPerformance`.
5. **E2E:** `tests/e2e/bdm-022-agent-performance.spec.ts`.
6. **Docs:** DEC-SCOPE-109, API 12AC, RBAC 2.35, backlog status, RTM row.
