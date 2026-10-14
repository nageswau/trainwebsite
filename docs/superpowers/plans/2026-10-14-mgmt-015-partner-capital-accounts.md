# mgmt-015 — Partner capital accounts — implementation plan

Spec: `docs/superpowers/specs/2026-10-14-mgmt-015-partner-capital-accounts-design.md`. TDD for each task: test first (RED), the minimum
code (GREEN), then refactor. Focused tests only; full regression is deferred to its own session.

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | `PartnerCapitalEntry`, `PartnerShare` models + CHECKs; migration `0158_partner_capital` (guarded; downgrade refuses with data) | `test_mgmt_015_migration.py` | `models.py`, `alembic/versions/0158_partner_capital.py` |
| 2 | Schemas: entry create (CP3), shares in (CP5/CP6), outputs | `test_entry_rejects_*`, `test_shares_reject_*` | `schemas.py` |
| 3 | `POST /management/capital/entries`: active partner, date ≤ today, audit create (CP12) | `test_entry_*` | `services/partner_capital.py`, `api/management.py` |
| 4 | `PUT /management/capital/shares`: upsert per month, lock, 409 race, audit create/update/no-op (CP6, CP12, CP14) | `test_shares_*` | same |
| 5 | `GET /management/capital`: figures (CP8, AC2), share total (CP7, AC1), profit share per month (CP9, AC3), period (CP10), entries paging, share history, former partners (CP1) | `test_view_*`, `test_ac*` | same |
| 6 | M13 on every route (AC4, CP13) | `test_access_*` | `api/management.py` |
| 7 | Seed demo shares + initial capital once (CP15) | run the seed twice in the stack | `seed.py` |
| 8 | Web lib: types, labels, query/URLs, form problems/bodies; live nav entry | `partnerCapital.test.ts`, `management.test.ts` | `lib/partnerCapital.ts`, `lib/management.ts` |
| 9 | Page + `PartnerCapital` (table, warnings, red, histories, paging, empty/error/403) | `PartnerCapital.test.tsx` | `components/PartnerCapital.tsx`, `app/management/capital/page.tsx` |
| 10 | `CapitalEntryForm` (overdraw confirm CP11, double click) and `CapitalSharesForm` | `CapitalEntryForm.test.tsx`, `CapitalSharesForm.test.tsx` | `components/Capital*Form.tsx` |
| 11 | Playwright: a partner records an entry and sets shares; the accountant and the super_admin are refused | `mgmt-015-partner-capital.spec.ts` | `tests/e2e/` |
| 12 | Docs: DEC-SCOPE, API §, RBAC §, DATA_MODEL, backlog status, QA report (numbers taken after merging main) | — | `docs/` |

Regression watch:
- The alembic head must stay single.
- The mgmt-001 e2e checks that "Partner capital accounts" is visible (still true once the entry is linked).
- The `management.test.ts` accountant exclusion.
- `/admin/audit` must keep hiding `mgmt.capital` (MA8, unchanged).
- `management_pnl` is read only.
