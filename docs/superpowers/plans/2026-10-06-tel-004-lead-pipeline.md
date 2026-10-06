# tel-004 — Lead pipeline: implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-004-lead-pipeline-design.md`. TDD per task (RED → GREEN → REFACTOR), lite backend set only
(test-regression-cadence); the full suite runs in the dedicated regression session.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | Stage catalogue + model (`LeadStageHistory`, `ck_enquiries_status`) | `test_tel_004_migration::test_model_matches_the_migration` | `app/lead_stages.py`, `app/models.py` |
| 2 | Migration 0080: table, PL1 mapping, CHECK, guarded upgrade, refusing downgrade | `test_tel_004_migration` (throwaway DB: map, CHECK, round trip, refusal, single head) | `alembic/versions/0080_lead_stage_pipeline.py` |
| 3 | Service: events, person moves, history, scope | `test_tel_004_pipeline.py` (unit on the DB session: AC1–AC4, reasons, closed rules) | `app/services/lead_pipeline.py`, `app/schemas.py` (`LeadStageMove`) |
| 4 | Telecaller routes: POST stage, GET history | `test_tel_004_routes.py` (telecaller own/other 404, manager reports/queue, super_admin, wrong role 403, reopen 403, AC5 order) | `app/api/telecaller.py` |
| 5 | Admin: PATCH through engine, history route, link/unlink events, `status_label` | update `test_adm_002`, `test_bdm_017_conversion`; new admin cases in `test_tel_004_routes.py` | `app/api/admin.py`, `app/services/bdm_leads.py` |
| 6 | Fixture/seed values valid under the CHECK | lite run catches them | tests, `seed.py` if needed |
| 7 | Web: `leadStages.ts`, filters, panel stage control + history | vitest `leadStages.test.ts`, `AdminLeadManagementPanel.test.tsx` | `apps/web/lib/leadStages.ts`, `AdminLeadFilters.tsx`, `AdminLeadManagementPanel.tsx` |
| 8 | Playwright e2e for admin stage change / reason / reopen / history | `tel-004-lead-pipeline.spec.ts` | `apps/web/tests/e2e/` |
| 9 | Docs: DEC-SCOPE-079, API §12G, SCREEN_CATALOG addendum, backlog status, RBAC note | — | `docs/…` |

Lite backend set: `test_tel_004_*`, `test_tel_003_*`, `test_adm_002_*`, `test_bdm_017_*`, `test_cns_001_*`, `test_rpt_001_*`,
`test_pub_002_enquiry_crm`, `test_tel_001_reads`, `test_tel_017_*`.
Frontend: vitest (touched files), `tsc --noEmit`, `eslint` (touched), `next build`.
