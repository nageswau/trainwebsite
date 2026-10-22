# ccrm-011 application codes — implementation plan

Design: `docs/superpowers/specs/2026-10-22-ccrm-011-application-codes-design.md`.

1. **Migration + model (TDD).** `tests/test_ccrm_011_migration.py`: chain after `0165`, single head, model default == migration default,
   column/unique exist in the shared DB, throwaway-DB round trip with backfill order. Then `models.py` (sequence, column, constraint,
   `eager_defaults`) and `alembic/versions/0166_application_codes.py`.
2. **Code semantics (TDD).** `tests/test_ccrm_011_application_codes.py`: new rows get distinct `APP-` codes; code survives withdraw.
3. **Payloads (TDD).** Same file: `/workflows/overseas/applications`, agency list + detail, portal counselor/admin applications table,
   rep table, student Applications section carry the code. Update `test_agn_023_filters.py` rep column list (intended change).
4. **Lookup search (TDD).** Same file: counselor finds own application by code; another counselor's code returns nothing.
5. **Frontend (TDD).** `AgentApplicationsPanel`, `AgentApplicationDetail`, `lib/agentApplications.ts` type; vitest updates.
6. **Docs.** Decision register `DEC-SCOPE-239`, API contract `12EQ`, RBAC note `2.153` (no new permission), backlog status, RTM row.
7. **E2E.** Playwright spec: counselor Applications page shows an `APP-` code.
