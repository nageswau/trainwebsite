# rec-010 implementation plan

Spec: `docs/superpowers/specs/2026-10-09-rec-010-placement-pool-opt-in-design.md`. TDD: each task writes its tests first and watches them
fail, then makes them pass.

1. **Model + migration `0123_candidate_consents`.** `CandidateConsent` and `CANDIDATE_CONSENT_CHECKS` go in `models.py`; the migration
   uses a guarded create and a refusing downgrade. Test: `test_rec_010_migration.py` (chain/single head, model = migration, round trip,
   CHECK, downgrade refusal).
2. **Service `services/placement_pool.py`** (`require_student`, `state`, `opt_in`, `opt_out`, the seed, `latest_courses`,
   `employer_visible`) **+ routes** in `api/account.py`, with the `PlacementPoolOptIn` schema. Test: `test_rec_010_placement_pool.py`
   (AC1–AC4, negatives, idempotency, stale version, backfill link, external link, seed rules, recruiter list visibility).
3. **EMP-003 / EMP-004 re-point** (`api/employer.py`). Update `test_emp_003_candidate_search.py` and `test_emp_004_interview_scheduling.py`
   for the opt-in rule (R12, a deliberate change). Run the EMP, rec-009 and rec-017 focused tests.
4. **Web:** `components/PlacementPoolCard.tsx`, mounted in `WorkflowPanel` for `it_student` on `placement-status`. Test:
   `tests/components/PlacementPoolCard.test.tsx`.
5. **E2E:** a new `tests/e2e/rec-010-placement-pool.spec.ts`, and update `emp-003-candidate-search.spec.ts` (opt in rather than a placement
   profile).
6. **Docs:** `DEC-SCOPE-138` (register), API_CONTRACT §12BF, RBAC §2.64, DATA_MODEL, SCREEN_CATALOG, backlog status line.
7. **Browser QA** (Docker stack on isolated ports), fixes, simplification, verification, merge `origin/main`, push.
