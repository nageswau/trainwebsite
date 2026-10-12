# mgmt-014 — Investment register + ROI — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-014-investment-register-design.md`. TDD for each task: test first (RED), minimum code
(GREEN), refactor. Focused tests only; full regression is deferred to its own session.

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | `Investment` model, `investment_code_seq`, CHECKs; migration `0150_investments` (guarded, downgrade refuses with data) | `test_mgmt_014_migration.py` | `models.py`, `alembic/versions/0150_investments.py` |
| 2 | `investments.roi` (MI7) and totals (MI8) | `test_roi_*`, `test_totals_*` | `services/investments.py` |
| 3 | Schemas: create/update validation (MI2, MI4–MI6), output, page | `test_create_rejects_*` | `schemas.py` |
| 4 | `POST /management/investments`: code, investor rule, audit create (MI11) | `test_create_*` | `services/investments.py`, `api/management.py` |
| 5 | `GET /management/investments` (filters, paging, totals, investor choices) and `GET /{id}` (404) | `test_register_*` | same |
| 6 | `PATCH /management/investments/{id}`: changed fields only, lock, audit before/after, no-op writes nothing | `test_update_*` | same |
| 7 | M13 access on every route: partner only; super_admin/accountant/other 403; 401 | `test_access_*` | `api/management.py` |
| 8 | Seed the §23 example once (MI14) | run seed twice in the stack | `seed.py` |
| 9 | Web lib: types, labels, URLs, ROI/money text, filters; live nav entry | `investments.test.ts`, `management.test.ts` | `lib/investments.ts`, `lib/management.ts` |
| 10 | Register page: totals, filter form, table, empty/error/403 states, paging; add form | `InvestmentRegister.test.tsx`, `InvestmentForm.test.tsx` | `components/Investment*.tsx`, `app/management/investments/page.tsx` |
| 11 | Detail page: fields, ROI, created/updated by, edit form, 404 | `InvestmentForm.test.tsx` | `app/management/investments/[id]/page.tsx` |
| 12 | Playwright: partner add/edit + 260% demo; accountant and super_admin refused | `mgmt-014-investments.spec.ts` | `tests/e2e/` |
| 13 | Docs: DEC-SCOPE-189, API §12DC, RBAC §2.115, DATA_MODEL note, backlog status, QA report | — | `docs/` |

Regression watch: alembic single head (sibling branches may also claim 0150 — re-chain at merge); mgmt-001/002/003 tests; `/admin/audit`
hides `mgmt.investment` rows (MA8, unchanged); `management.test.ts` / `ManagementCommandCenter.test.tsx`.
