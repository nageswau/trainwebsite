# pob-003 implementation plan

Spec: `docs/superpowers/specs/2026-11-05-pob-003-company-business-context-design.md` (DEC-SCOPE-406). TDD per task: failing test → minimum
code → green → refactor. Focused tests only (full regression deferred to the dedicated session).

## Backend
1. **Migration + models** — `0283_company_business_context`: companies columns (`products_services`, `departments_hiring`,
   `hiring_locations`, `target_roles` JSON, `last_contacted_at` + index), tables `company_branches`, `company_skill_demand`,
   `company_documents` (kind CHECK), backfill of `last_contacted_at`. Test: `test_pob_003_migration.py` (columns/tables/checks exist,
   checks match models, backfill expression, downgrade/upgrade round-trip).
2. **Business context on PATCH/POST** — schemas (`RecCompanyUpdate` + out models), service `save_context` (branches set, skill set with
   active check, lists), `company_out` fields. Tests in `test_pob_003_company_context.py`: save/read back all fields, `[]` clears, list
   normalisation, 422s (too many, blank city, inactive skill, unknown skill), no-change = no audit, legacy `branches` untouched.
3. **last_contacted_at** — `refresh_last_contact` + hooks in calls (create/update/delete), messages create, interviews contact email,
   profile_sharing message, meeting outcome; list `sort` + row field. Tests: call logged → set; edit/delete call → recomputed; WhatsApp
   message → set; meeting outcome → set; no activity → null; sort order nulls last; updated_at not bumped.
4. **Documents** — `services/company_documents.py` + `api/company_documents.py` (router in main.py). Tests: upload each kind + audit,
   list/filter, download + audit + headers, agreement grant 403s (view/edit deny overrides), scope 404, manager/bdm 403 upload, archived
   409, meeting of another company 422, oversize 413, wrong type 415, throttle 429, cap 409; rec-038 rows.

## Web
5. `lib/recruiterCompanies.ts` types/helpers (+ vitest for pure helpers: list parsing, context body).
6. `RecruiterCompanyBusiness.tsx` (view/edit) + vitest.
7. `lib/recruiterCompanyDocuments.ts` + `RecruiterCompanyDocuments.tsx` + vitest (list, empty, error, upload gating, agreement option).
8. Detail wiring ("Last contact", "Branch notes", message re-read), list column + sort (+ update existing vitest fixtures).
9. Playwright e2e `pob-003-company-context.spec.ts`: save context, log call → Last contact, upload + download a document.

## Docs
10. DEC-SCOPE-406 register entry, API §12KZ, RBAC §2.299, DATA_MODEL, RTM row, backlog status line.
