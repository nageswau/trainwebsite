# mgmt-016 — Student funnel dashboard (plan)

Spec: `docs/superpowers/specs/2026-10-14-mgmt-016-student-funnel-design.md` (SF1–SF16). No migration.

1. **API test first** (`apps/api/tests/test_mgmt_016_funnel.py`):
   - The access matrix, the period default and the 422 cases, an unknown `by`.
   - Exact stage counts (SF3–SF15) over a random 17xx/18xx month, a range no other test writes in.
   - The breakdown sums (SF16) and Branch untracked.
   - RED.
2. **Service + schema + route:** `services/management_funnel.py`, `StudentFunnel*` models appended to `schemas.py`,
   `GET /management/funnel` appended to `api/management.py`. GREEN. Then ruff and mypy.
3. **Web lib + component tests first** (`tests/lib/managementFunnel.test.ts`, `tests/components/ManagementFunnel.test.tsx`). RED.
4. **Web:** `lib/managementFunnel.ts`, `components/ManagementFunnel.tsx`, `app/management/funnel/page.tsx`, and the Command Center href in
   `lib/management.ts` plus a super admin nav entry in `lib/navigation.ts`. GREEN. Then tsc, eslint and the build.
5. **Browser QA** on the mgmt016 stack (13016/18016) plus `tests/e2e/mgmt-016-funnel.spec.ts`. Write the QA report.
6. **Docs:** the DEC-SCOPE, API contract, RBAC matrix and backlog status, numbered after merging main.
