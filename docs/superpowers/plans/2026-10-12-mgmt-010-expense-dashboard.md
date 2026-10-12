# mgmt-010 — Expense dashboard — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-010-expense-dashboard-design.md` (ME1–ME10).

## Reviews folded in (Phase 3)

- **API:** one read-only `GET`, finance tier checked first in the route (M13 convention: role → tier → action). New route only; no
  existing contract changes. Decimal amounts serialise as strings, as the ledger does. `422` messages are plain strings (no field).
- **Frontend:** server-rendered page like `/management/snapshot`; GET form so refresh/back/shared links keep the month; existing
  `table`/`metric` styles; captions on both tables; bars `aria-hidden` with the percentage written in text; no client JS.
- **Security:** aggregate only — no ids, no person names (MA7); category names are rendered as text (React escapes). No writes, so no
  CSRF/audit surface. Tier refusal at the route, before any query.

## Tasks

1. RED/GREEN `services/management_expenses.py` + route + schemas, driven by `tests/test_mgmt_010_expenses.py`
   (access, validation, heads, exclusions, reversal, auto lines, FY boundary, invariants, not-counted).
2. RED/GREEN `lib/managementExpenses.ts` with `tests/lib/managementExpenses.test.ts`.
3. RED/GREEN `components/ManagementExpenses.tsx` with `tests/components/ManagementExpenses.test.tsx`; page; nav `href`
   (update `management.test.ts` expectations if they list live entries).
4. CSS for the share bars in `globals.css`.
5. Playwright `tests/e2e/mgmt-010-expenses.spec.ts`.
6. Docs: DEC-SCOPE, API §12DH, RBAC §2.119, backlog status, QA report.
