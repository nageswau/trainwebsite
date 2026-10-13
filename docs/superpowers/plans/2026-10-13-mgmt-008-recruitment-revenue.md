# mgmt-008 — implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-008-recruitment-revenue-design.md`. TDD per task (RED → GREEN → REFACTOR).

1. **Backend RED:** `apps/api/tests/test_mgmt_008_recruitment_revenue.py` — access (partner/accountant full, super_admin KPIs only,
   it_admin/student 403, signed out 401), 422s, kinds (invoice row + manual category, reversal nets), AC1, AC2, RR6, FY period.
2. **Backend GREEN:** `recruiter_metrics.performance(..., roles=PERFORMANCE_ROLES)`; `services/management_recruitment_revenue.py`;
   `schemas.RecruitmentRevenueOut`; route in `api/management.py` (reuses `_past_month`). Re-run rec-033/035 tests.
3. **Web RED:** `tests/lib/managementRecruitmentRevenue.test.ts`, `tests/components/ManagementRecruitmentRevenue.test.tsx`,
   nav assertions in `tests/lib/management.test.ts`.
4. **Web GREEN:** `lib/managementRecruitmentRevenue.ts`, `components/ManagementRecruitmentRevenue.tsx`,
   `app/management/revenue/recruitment/page.tsx`, `lib/management.ts` href, `lib/navigation.ts` super-admin link.
5. **E2E:** `tests/e2e/mgmt-008-recruitment-revenue.spec.ts` (partner, accountant, super admin).
6. **Docs:** DEC-SCOPE, API §, RBAC §, backlog status, QA evidence.
