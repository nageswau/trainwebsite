# mgmt-006 — Abroad Education revenue dashboard — implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-006-abroad-revenue-design.md` (MR1–MR12). TDD per task; focused tests only.

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | `can_view_university_commission` (partner only) | backend: partner true, accountant / super_admin false | `services/management_access.py` |
| 2 | Route + schema + service skeleton: access (MR11), month validation (MR10), empty shape | 401/403/422, default month, keys | `api/management.py`, `schemas.py`, `services/management_abroad_revenue.py` |
| 3 | Revenue kinds (MR2/MR3) + not-counted (MR9) | service fee / other type / manual / deposit & IT excluded / non-INR | service |
| 4 | Breakdowns + agent-generated (MR4/MR5) | linked agency app, direct app, receipt, sums = revenue | service |
| 5 | Commission rule (MR7) | partner sees receipt, accountant does not (all figures) | service |
| 6 | Expenses, shared note, contribution (MR6/MR8) | commission, agent trip, manual abroad, shared only in note, contribution | service |
| 7 | Web lib | vitest: month param, URLs, ledger href | `lib/managementAbroadRevenue.ts` |
| 8 | Component | vitest: kinds, breakdowns, contribution, commission note, empty | `components/ManagementAbroadRevenue.tsx` |
| 9 | Page + Command Center `href` | vitest for nav entry | `app/management/revenue/abroad/page.tsx`, `lib/management.ts` |
| 10 | Playwright | partner / accountant / super_admin | `tests/e2e/mgmt-006-abroad-revenue.spec.ts` |
| 11 | Docs after merging main: DEC-SCOPE, API §, RBAC §, backlog status | — | `docs/...` |

## Phase 3 review notes (applied to the tasks above)

- **API:** GET only, no body; one validated query param (`month`, regex + range). It follows the `/management/expenses` contract shape
  (decimal strings, `not_counted`), and adds no new status codes. There are no writes, so there is no transaction, lock or audit row
  (reads of finance dashboards are not audited, as mgmt-010).
- **Security:** finance tier checked first in the route. The commission rule is applied in the service query (rows are never fetched for
  the accountant), not only in the UI. No client-supplied ids, so no IDOR surface. The ORM builds every query, so there is no raw SQL
  input. No PII in the payload (MR12). Server-rendered React escapes the names.
- **Frontend:** reuses the `action-card` / `analytics-form` / `table-wrap` / `expense-bar` idiom of mgmt-010. Every table has a caption
  and scrolls in its own region (`tabIndex=0`), and the titles sit outside the scroll areas (mgmt-010 QA-02). Error and empty states
  follow the same idiom. The month form is a GET form, so refresh, back and shared links work.
- **Performance:** two grouped queries over the existing UNION, with indexed joins (`payments.id`, `overseas_applications.id`,
  `universities.id`, `agent_org_members.user_id`).
