# tel-009 Qualification form — implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-009-qualification-form-design.md` (DEC-SCOPE-092, QF1–QF3, QD1–QD4). Every task is TDD: the
failing test is written and run first (RED), then the minimum code (GREEN), then a refactor with the focused tests re-run.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | `LeadQualification` model + migration `0088_lead_qualifications` (guarded upgrade, drop on downgrade) | `tests/test_tel_009_migration.py`: one head chained after `0087_lead_import_batches`; model columns/CHECKs equal the migration's; round trip in a throwaway DB | `app/models.py`, `alembic/versions/0088_lead_qualifications.py` |
| 2 | `LeadQualificationIn` + service `lead_qualification` (`read`, `replace`) + `GET/PUT /telecaller/leads/{id}/qualification` | `tests/test_tel_009_qualification.py`: AC1–AC6 (sections by group, ranges, hidden group kept, write-through, no stage move + one audit, 404/403 scope and handed-over), extra key 422, idempotent repeat = no second audit | `app/schemas.py`, `app/services/lead_qualification.py`, `app/api/telecaller.py` |
| 3 | Web: types/labels in `lib/telecallerLeads.ts`; `LeadQualificationForm` (load, error+retry, view, edit, fieldsets, `aria-invalid`, leave guard, read-only); mounted in `LeadDetailPanel` with write-back of shared fields | `tests/components/LeadQualificationForm.test.tsx` (vitest) | `apps/web/lib/telecallerLeads.ts`, `apps/web/components/LeadQualificationForm.tsx`, `apps/web/components/LeadDetailPanel.tsx` |
| 4 | Playwright journey: telecaller fills overseas UK Masters Sep 2027; 120% refused; switch product to IT, overseas hidden then back, values kept | `tests/e2e/tel-009-qualification.spec.ts` | — |
| 5 | Docs: DEC-SCOPE-092, API §12O, backlog tel-009 status, RBAC matrix row | — | `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/architecture/API_CONTRACT.md`, `docs/delivery/TELECALLER_CRM_BACKLOG.md` |

Focused regression: `test_tel_008_workspace.py`, `test_tel_004_*`, `LeadDetailPanel.test.tsx`, tel-008 e2e. The full suite is deferred to the
regression session.
