# pob-006 — Company and contact import, and authorised merge (plan)

Design: `docs/superpowers/specs/2026-11-06-pob-006-company-import-merge-design.md` (`DEC-SCOPE-418`).

## Tasks (TDD: each test is written and seen failing first)
1. **Model + migration 0297** — `merged_into_id/at/by` on `companies` and `company_contacts`, `crm_import_batches`, `crm_import_rows`, the `crm` catalogue resource and its
   `placement_manager` grants. Guarded (inspect before add); downgrade drops them. Tests: `test_pob_006_migration.py`, the catalogue test in `test_nehn_005_permissions.py`.
2. **Import** — `services/company_import.py` + `api/recruiter_company_imports.py`: template, preview, commit, history, report, report.csv. Tests: `test_pob_006_import.py` (AC1, AC2, per-row
   errors, scope, replay, CSV guard).
3. **Company merge** — `services/company_merge.py`: preview and merge, every foreign key decided (`test_every_reference_is_handled`), Q-06, employer accounts, id-ordered locks. A merged
   company cannot be edited or restored; `/workflows/it/jobs` follows it to its survivor. Tests: `test_pob_006_merge.py`.
4. **Contact merge** — the same service: moves by `contact_id`, Do Not Contact contagious, primary and decision-maker carried, merged rows hidden from the list, the duplicate warning and the edit
   routes. Tests: `test_pob_006_merge.py`.
5. **Web** — `lib/recruiterCompanyImport.ts`, `RecruiterCompanyImport`, `RecruiterCompanyMerge`, three pages, links on the list, the detail and each contact. Vitest:
   `RecruiterCompanyImport.test.tsx`; e2e `pob-006-import-merge.spec.ts`.
6. **Docs** — DEC-SCOPE-418, API §12LK, RBAC §2.310, DATA_MODEL, backlog status, RTM rows, rec-038 rows.

## Review notes (Phase 3)
- **API:** additive only (`merged_into` is optional). Multipart upload plus `Idempotency-Key`, as hrc-013. 404 for out of scope, 403 for no grant, 409 for state, 422 for validation.
- **Security:** the grant is additive to the role gate and never widens scope; both merge sides resolve through `caller_scope`; rules are re-checked on the locked rows; the report escapes formulas;
  no cell value is stored or logged; audit rows hold ids, counts and field names. The merged banner shows only a company code or a fixed sentence, and no person's name goes in a URL.
- **Transactions:** one transaction per import with a savepoint per row, the advisory lock serialising imports; a merge locks both companies in id order.
- **Frontend:** reuses `BulkColumnReference`, the hrc-013 wizard shape and hrc-014's comparison; radios per differing field; a ref guards double submission; loading, empty, error and retry states;
  `table compact stack` on a phone.
