# mgmt-023 — University partnership dashboard (plan)

Spec: `docs/superpowers/specs/2026-10-14-mgmt-023-university-partnership-dashboard-design.md` (UD1–UD14).

1. **Refactor (no behaviour change):** split `partnership_performance.commission_by_university` into an un-gated `commission_sums`;
   upc-018/019/029 tests stay green.
2. **RED → GREEN, backend:** `tests/test_mgmt_023_universities.py` — access (401 / 403 accountant and others / 200 partner,
   super_admin), 422 periods, revenue only for the partner, totals equal `/partnership/global-dashboard`, UD5/UD7/UD8 definitions by
   delta, the next-month list. Then `services/management_universities.py`, schemas, the route in `api/management.py`.
3. **RED → GREEN, web lib:** `tests/lib/managementUniversities.test.ts` → `lib/managementUniversities.ts` (query, url, href).
4. **RED → GREEN, component:** `tests/components/ManagementUniversities.test.tsx` → `components/ManagementUniversities.tsx`
   (tiles, Revenue only when present, pipeline, expected windows + next-month table, empty and error states, period form).
5. **Page + nav:** `app/management/universities/page.tsx`; `lib/management.ts` Universities href; `SUPER_ADMIN_NAV` entry;
   update pinned nav tests.
6. **E2E:** `tests/e2e/mgmt-023-universities.spec.ts` (partner with Revenue; super_admin without; accountant refused).
7. **Docs after merging main:** DEC-SCOPE, API §, RBAC §, backlog status, QA evidence.
