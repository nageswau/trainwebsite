# mgmt-007 — IT Training revenue dashboard — implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-007-it-revenue-dashboard-design.md` (IR1–IR12).

## Reviews folded in (Phase 3)

- **API:** two read-only `GET`s, finance tier checked first in the route (role → tier → validation → query). New routes only; no
  existing contract changes; `ledger.lines()` is read, never changed (mgmt-006 works beside it). Decimal amounts serialise as strings.
  The period validation reuses the mgmt-010 rules (`MONTH` pattern, `EARLIEST_MONTH`, no future month); `period` is a `Literal`.
  The payments scope is exactly one of `program_id` / `batch_id` / `unlinked` (422 otherwise); an unknown id is a 422 field message
  ("Choose a course from the list"), not a 404, because it is a filter. `limit` 1–100 (default 25), `offset` ≥ 0.
- **Database:** two grouped queries over the `lines()` subquery with outer joins to `payments` → `enrollments` → `batches` and to
  `ledger_entries` (PK joins), one grouped enrolment count; no N+1 (titles loaded once for the ids present). No migration.
- **Frontend:** server-rendered like `/management/expenses`; GET form with `key`/`autoComplete="off"` (memory: stale fields after
  client navigation); existing `table`, `metric`, `expense-bar`, `table-wrap` styles; titles outside scroll regions (mgmt-010 QA-02);
  captions; empty / error / access states; the payments list is a section of the same page with pager links, so refresh / back /
  shared links keep everything. No client JS.
- **Security:** finance tier only; no student names or emails (Q-32 open); enrolment codes are pseudonymous identifiers already shown
  to the finance tier on ledger lines' sources. ORM-bound parameters only. No writes → no CSRF / audit surface. Course titles rendered
  as text (React escapes).

## Tasks

1. RED/GREEN `services/management_it_revenue.py` + route + schemas, driven by `tests/test_mgmt_007_it_revenue.py` (access, validation,
   attribution, exclusions, invariants, year period, not counted).
2. RED/GREEN payments drill-down (`/revenue/it/payments`) in the same test file.
3. RED/GREEN `lib/managementItRevenue.ts` with `tests/lib/managementItRevenue.test.ts`.
4. RED/GREEN `components/ManagementItRevenue.tsx` with `tests/components/ManagementItRevenue.test.tsx`; page; nav `href`
   (update nav tests that pin live entries).
5. Playwright `tests/e2e/mgmt-007-it-revenue.spec.ts`.
6. Docs (after merging main): DEC-SCOPE, API §, RBAC §, backlog status, QA report.
