# tel-007 — Lead distribution: implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-007-lead-distribution-design.md`. Branch `feature/tel-007` (worktree `tel-007`) from `main` @ `3986958c`.
TDD per task: write the test, see it fail for the expected reason, implement, see it pass.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | Models + migration `0084_tel_distribution` | `test_tel_007_migration.py` (chain/single head, model ⇔ migration, round trip in a throwaway DB, shape CHECK, unique indexes, downgrade refusal) | `models.py`, `alembic/versions/0084_tel_distribution.py` |
| 2 | Service: `next_in_turn`, `distribute`, `assign`, `on_intake`, `assignee` | `test_tel_007_distribution.py` (AC1–AC4, cursor order, product without team, savepoint fallback) | `services/lead_distribution.py` |
| 3 | Intake wiring | `test_tel_007_intake.py` (website + BDM assign: stage, history row, audit; unassigned when no candidate) | `api/public.py`, `api/bdm_leads.py` |
| 4 | Rules API | `test_tel_007_rules.py` (CRUD, 401/403/404/409/422, editable flag, DI3) | `schemas.py`, `api/telecaller_distribution.py`, `main.py` |
| 5 | Queue + assign API | `test_tel_007_assign.py` (lists + scope, AC5 403, 404 out of scope, 422 cross-team/inactive, unchanged, audit per lead, cap 100) | same |
| 6 | Web lib + rules page | `TelecallerRulesPanel.test.tsx`, `telecallerDistribution.test.ts` | `lib/telecallerDistribution.ts`, `components/TelecallerRulesPanel.tsx`, `TelecallerRuleRow.tsx`, page, nav |
| 7 | Web assignment page | `TelecallerAssignmentPanel.test.tsx` | `components/TelecallerAssignmentPanel.tsx`, page |
| 8 | E2E | `tests/e2e/tel-007-lead-distribution.spec.ts` | — |
| 9 | Docs | — | decision register `DEC-SCOPE-084`, API §12J, SCREEN_CATALOG, ROLE_NAVIGATION, backlog status |

Lite backend set: the tel-007 files plus `test_tel_003_intake`, `test_pub_002_enquiry_crm`, `test_tel_004_routes`, `test_tel_004_pipeline`,
`test_bdm_017_conversion`, bdm lead tests, `test_tel_001_reads`, and the latest migration tests (`test_tel_004_migration`, `test_tel_022_migration`).
