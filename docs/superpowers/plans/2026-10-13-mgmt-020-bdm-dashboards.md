# mgmt-020 BDM dashboards — implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-020-bdm-dashboards-design.md` (BD1–BD12). TDD per task; focused tests only.

1. **bdm-024 per-type totals** — move the route's per-BDM / per-type summing into `bdm_performance.type_totals(members, rows)`;
   `performance()` calls it. Regression: `test_bdm_024_performance.py` green, unchanged.
2. **Team-aware builders** — `bdm_metrics._activities` and `_linked_schools` use `_owned`. Regression: `test_bdm_015_*`, `test_bdm_016_*`.
3. **Service** `services/management_bdm.py`: `FIGURES` (per type: key, label, definition, basis, source) and `dashboard(db, type, start,
   end)` — bdm-024 totals for BD4, `hierarchy()` for BD5 (agent only), one SELECT of scalar subqueries for BD6–BD11.
4. **Route + schema** `GET /management/bdm` in `api/management.py`, `ManagementBdmOut`; operational tier (BD12). RED first:
   `test_mgmt_020_bdm_dashboards.py` (access, 422s, keys, AC equality, deltas, not tracked).
5. **Web lib** `lib/managementBdm.ts` (query from search params, API url, page href) + unit test.
6. **Component** `components/ManagementBdm.tsx` (tabs, period form, two tile groups, not tracked, error) + RTL test.
7. **Page** `app/management/bdm/page.tsx` (+ `loading.tsx` if siblings have one); nav: `lib/management.ts` href, `SUPER_ADMIN_NAV`
   entry; nav tests.
8. **e2e** `tests/e2e/mgmt-020-bdm-dashboards.spec.ts`: partner tabs + period, super admin, accountant refused, phone width.
9. **Docs**: DEC-SCOPE, API §12DN, RBAC §2.125, backlog status, QA report.
