# mgmt-025 — Recruitment dashboard: implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-025-recruitment-dashboard-design.md` (RC1–RC12). TDD for every task; focused tests only.

1. **Service + route + schema (pytest first).** `tests/test_mgmt_025_recruitment.py` RED → `recruiter_metrics.management(..., roles=)`
   keyword + a shared `new_companies()` B4 sub-query; `management_recruitment_revenue.revenue_total()` public;
   `services/management_recruitment.py` (`dashboard()`), `schemas.RecruitmentDashboardOut`, `GET /management/recruitment` → GREEN.
   Re-run `test_rec_034*`, `test_rec_035*`, `test_mgmt_008*`.
2. **Web lib (vitest first).** `tests/lib/managementRecruitment.test.ts` → `lib/managementRecruitment.ts` (filters, urls, KPI list, rate text).
3. **Component (vitest first).** `tests/components/ManagementRecruitment.test.tsx` → `components/ManagementRecruitment.tsx` (form, tiles,
   pipeline, super-admin view, error).
4. **Page + nav.** `app/management/recruitment/page.tsx` (mgmt-019 page pattern); `lib/management.ts` hrefs for the two mgmt-025 entries;
   `SUPER_ADMIN_NAV` link; nav tests.
5. **E2E.** `tests/e2e/mgmt-025-recruitment.spec.ts`: partner opens it from the Command Center, applies a range, refresh keeps it; super
   admin sees no revenue; accountant gets the access card.
6. **Docs.** DEC-SCOPE (RC1–RC12), API §12, RBAC §2, backlog status line, QA report.

Review notes (Phase 3): read-only GET, no transaction or locking; inputs are two `date` query params (FastAPI 422 when malformed, rec-033
range rules otherwise); authorization runs `require_management` → operational tier before any read; revenue is computed only for
`can_view_finance` (the super admin never touches the ledger); output is counts plus one money total, with no PII; React escapes text;
GET only, so no CSRF surface; SQL is ORM-built; the 366-day cap bounds the cost.
