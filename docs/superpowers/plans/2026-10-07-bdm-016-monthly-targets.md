# bdm-016 — Monthly targets — implementation plan

Spec: `docs/superpowers/specs/2026-10-07-bdm-016-monthly-targets-design.md`. TDD per task (red → green → refactor); focused tests only.

| # | Task | Files | Tests first |
|---|---|---|---|
| 1 | Model `BdmTarget` + migration `0096_bdm_targets` | `app/models.py`, `alembic/versions/0096_bdm_targets.py` | `tests/test_bdm_016_migration.py` (chain/head, parity, guarded, downgrade refusal) |
| 2 | KPI catalogue + `month_range` + `monthly_counts` (one SELECT); generalize `_new_prospects` / `_mou_moved_to` / meetings by org type without changing daily behaviour | `app/services/bdm_metrics.py` | `tests/test_bdm_016_metrics.py`: catalogues, each new builder in/out of month and other BDM, not tracked, constant query count; rerun `test_bdm_015_metrics.py` |
| 3 | Schemas (`BdmTargetsPut`, `BdmTargetsCopy`, `BdmTargetSheet`, `BdmTargetTeam`) | `app/schemas.py` | covered by API tests |
| 4 | Service: month parsing/rules, sheet, upsert + audit, copy | `app/services/bdm_targets.py` | via API tests |
| 5 | Routes + registration | `app/api/bdm_targets.py`, `app/main.py` | `tests/test_bdm_016_targets.py` (own read, manager team/detail, PUT rules, 403/404/422, audit, copy, AC5 73%) |
| 6 | Web lib + components: `lib/bdmTargets.ts`, `BdmTargetsEditor`, `BdmTargetsCard` | `apps/web/lib`, `apps/web/components` | vitest `tests/components/BdmTargets*.test.tsx`, `tests/lib/bdmTargets.test.ts` |
| 7 | Pages + nav: `/bdm/manager/targets`, `/bdm/manager/targets/[bdmId]`, My Day card, manager nav "Targets" | `apps/web/app/bdm/...`, `lib/navigation.ts` | page tests; nav test; Playwright `tests/e2e/bdm-016-targets.spec.ts` |
| 8 | Docs: `DEC-SCOPE-103`, backlog status, API §12W, RBAC §2.29, browser QA record | `docs/...` | — |

Verification per task: `pytest tests/test_bdm_016_*.py tests/test_bdm_015_*.py -q` in the `bdm016` api container, `ruff`; web: `tsc`,
`eslint`, vitest for touched files; at the end `next build`, Playwright for bdm-016 + bdm-015 + bdm-014.
