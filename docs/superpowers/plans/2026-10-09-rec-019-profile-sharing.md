# rec-019 — Profile sharing (plan)

Spec: `docs/superpowers/specs/2026-10-09-rec-019-profile-sharing-design.md` (DEC-SCOPE-158, S1–S14). TDD per task: write the failing
test, run it (RED), implement the minimum (GREEN), then refactor and re-run.

1. **Models + migration `0140_profile_shares`.** Add `ProfileShare` and `ProfileShareItem` with their CHECKs. Test: `test_rec_019_migration.py` (head, the CHECKs equal the model, downgrade).
2. **Service `services/profile_sharing.py` + schemas** `RecShareCreate`, `RecShareItemUpdate`, `EmployerShareResponse`. Includes rules S1–S12, the summary, the texts, tokens and outputs. rec-026 gets `check_cap` extracted (no behaviour change).
3. **Routes `api/recruiter_shares.py`** (POST, both lists, PATCH, the public resume route) plus the employer routes in `employer.py`. Register them in `main.py`. Test: `test_rec_019_shares.py`.
4. **Web lib `lib/recruiterShares.ts`** + vitest.
5. **Components.** `RecruiterShareDialog`, `RecruiterShares` (requirement + company pages), multi-select on the Candidates board, Matching and Find Candidates, and `EmployerSharedProfilesPanel`. vitest for each.
6. **e2e** `rec-019-shares.spec.ts`.
7. **Docs.** DEC-SCOPE-158 in the register, API_CONTRACT §12BZ, DATA_MODEL, RBAC_MATRIX §2.84, SCREEN_CATALOG and the backlog status.

Focused test set (lite): `test_rec_019_*`, `test_rec_026*`, `test_rec_017*`, `test_rec_016*`, `test_emp_003*`, `test_emp_004*`,
`test_rec_005_pipeline.py`, plus the route-inventory/RBAC tests that enumerate routes.
