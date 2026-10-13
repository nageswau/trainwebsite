# mgmt-012 — Marketing budget, spend, ROI — implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-012-marketing-roi-design.md` (MK1–MK14). Branch `feature/mgmt-012`. TDD for each task
(RED → GREEN → REFACTOR), with focused tests only.

## Tasks

1. **Model + migration** (`models.py` `MarketingBudget`, `MARKETING_BUDGET_CHECKS`; `0156_marketing_budgets`).
   - Test `test_mgmt_012_migration.py`: a single head, and the CHECKs equal the model's.
   - Verify `alembic upgrade head` and offline `--sql`.
2. **Schemas** (`MarketingBudgetsIn` with channel `Literal[TEL_SOURCES]`, money = `SalaryMoney`, duplicate check; out models).
3. **Service: figures** (`management_marketing.dashboard`).
   - Leads, qualified and customers per channel and campaign.
   - Spend from tagged approved entries.
   - Revenue from `ledger.lines()` payment lines joined to converted leads.
   - ROI and conversion, the groups, and the totals.
   - Money is skipped when the caller lacks the finance tier.
   - Tests: AC1, AC2, attribution, zero spend, super_admin without money.
4. **Service: budgets** (`save_budgets`: advisory lock, replace month, audit `mgmt.marketing_budget` with field names only).
   - Tests: replace/clear, 422s, audit row, no row when unchanged.
5. **Routes** (`GET /management/marketing`, `PUT /management/marketing/budgets`).
   - Tests: 401/403 per role, the future month 422.
6. **Audit kind** in `management_audit.KINDS`; update the pinned kinds set in `test_mgmt_002_activity.py`.
7. **Web lib** `lib/marketing.ts` + vitest.
8. **Web components**: `MarketingDashboard`, `MarketingBudgetForm`, page `app/management/marketing/page.tsx`, the nav hrefs in
   `lib/management.ts`. Vitest for the dashboard (money hidden for super_admin, "—" ROI, "Not set" budget, Influencer "Not tracked").
9. **Playwright** `mgmt-012-marketing.spec.ts`.
10. **Docs**: `DEC-SCOPE-206`, API §12DT, RBAC §2.131, DATA_MODEL, backlog status, QA report.

## Regression risks

- `models.py`, `schemas.py` and `management.py` are append-only.
- `lib/management.ts` nav: there is a nav test (check `tests/lib/management.test.ts`).
- The audit KINDS pinned set in the mgmt-002 test.
- `ledger.lines()` is read only (frozen), so nothing changes in it.
