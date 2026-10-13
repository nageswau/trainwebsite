# mgmt-017 — Training & trainer dashboard (plan)

Spec: `docs/superpowers/specs/2026-10-13-mgmt-017-training-dashboard-design.md` (TR1–TR16). TDD per task; focused tests only.

1. **Backend RED:** `apps/api/tests/test_mgmt_017_training.py` — access matrix (TR16), period (TR1), per-trainer figures (TR2/3/8/9/15),
   KPI deltas (TR4–TR14), TR7 = snapshot Trainers. Run → fails (404).
2. **Backend GREEN:** `services/management_training.py` (`KPIS`, `TRAINER_FIGURES`, `dashboard`), `schemas.py`
   (`ManagementTrainingOut`), `api/management.py` (`GET /management/training`). Run → passes. ruff on changed files.
3. **Web lib RED/GREEN:** `tests/lib/managementTraining.test.ts` → `lib/managementTraining.ts` (types, query parsing, url, formatters).
4. **Web component RED/GREEN:** `tests/components/ManagementTraining.test.tsx` → `components/ManagementTraining.tsx`,
   `app/management/training/page.tsx`; nav entries in `lib/management.ts` and `lib/navigation.ts` (update their existing tests if they
   pin the entries).
5. **e2e:** `tests/e2e/mgmt-017-training.spec.ts` against the isolated stack (partner path, period reload, 422, super admin, accountant,
   phone width).
6. **Docs:** `DEC-SCOPE-208`, API §12DV, RBAC §2.133, backlog status, QA report `docs/quality/MGMT-017_EXPLORATORY_QA_2026-10-13.md`.

Risks: shared test DB (assert on own fixtures, KPI deltas); nav tests pinning entry lists; `SUPER_ADMIN_NAV` one-liner merges.
