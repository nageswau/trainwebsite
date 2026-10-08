# rec-005 — Company pipeline: implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-005-company-pipeline-design.md`. Branch `feature/rec-005` from `origin/main` @ `a62ad9d7`.
TDD per task: failing test first, then code, then the focused tests.

| # | Task | Files | Tests |
|---|---|---|---|
| 1 | Stage catalogue + model columns + `CompanyStageHistory` + migration 0108 | `recruiter_stages.py`, `models.py`, `alembic/versions/0108_company_pipeline.py` | `test_rec_005_migration.py` |
| 2 | Engine: `apply_event`, `person_move`, `mark_lost`, `reopen`, `pipeline_out`, `history_page`, `board` | `services/company_pipeline.py` | `test_rec_005_pipeline.py` (engine) |
| 3 | Routes + schemas; company detail `pipeline`, row `stage`/`stage_label`/`lost` | `api/recruiter_pipeline.py`, `schemas.py`, `services/recruiter_companies.py`, `main.py` | `test_rec_005_pipeline.py` (API), `test_rec_003_*` regression |
| 4 | Frontend lib + company pipeline section + stage history | `lib/recruiterPipeline.ts`, `RecruiterCompanyPipeline.tsx`, `RecruiterStageHistory.tsx`, `RecruiterCompanyDetail.tsx` | `RecruiterCompanyPipeline.test.tsx` |
| 5 | Board page + list Stage column + nav | `app/recruiter/pipeline/page.tsx`, `RecruiterPipelineBoard.tsx`, `RecruiterCompaniesPanel.tsx`, `navigation.ts` | vitest board + nav tests |
| 6 | E2E + browser QA | `tests/e2e/rec-005-pipeline.spec.ts` | Playwright |
| 7 | Docs: DEC-SCOPE-123, API §12AQ, RBAC §2.49, DATA_MODEL, backlog status, ROLE_NAVIGATION, SCREEN_CATALOG, QA report | `docs/**` | — |

Regression risks: `companies` inserts (EMP-001, `/workflows/it/jobs`) rely on the server defaults; the rec-003 detail/row contract only gains
fields; rec-004 (in flight) also edits `RecruiterCompanyDetail.tsx` and takes a migration, so re-chain at merge.
