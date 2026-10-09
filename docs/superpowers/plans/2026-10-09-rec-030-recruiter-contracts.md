# rec-030 Recruiter contracts — implementation plan

Spec: `docs/superpowers/specs/2026-10-09-rec-030-recruiter-contracts-design.md`. TDD for each task: write the test, see it fail, then implement it.

1. **Migration and models.** Add `RECRUITER_CONTRACT_*` constants, `RecruiterContract` and `RecruiterContractEvent` in `models.py`, and
   `0137_recruiter_contracts.py`. Test: `test_rec_030_migration.py` (chain, single head, CHECK parity, round trip, downgrade refusal).
2. **Schemas.** `RecContractCreate` / `Update` / `Out` / `Envelope` / `CompanyContracts` / `EventPage`. The `contract` field on the
   company detail.
3. **Service** `services/recruiter_contracts.py`: effective status, rules (CT2–CT4, CT8), load current, store/discard/read document,
   upload wait, history, output.
4. **Routes** `api/recruiter_contracts.py`, registered in `main.py`. Test: `test_rec_030_contracts.py` (AC1–AC3, the negative and edge
   cases, roles, documents, renewal).
5. **Web lib** `lib/recruiterContracts.ts`, plus the `contract` field in the `Company` type and a "Contract status" Details row.
6. **Components:** `RecruiterCompanyContract`, `RecruiterContractForm`, `RecruiterContractDocument`, `RecruiterContractHistory`.
   Vitest for these.
7. **Playwright** `rec-030-contracts.spec.ts`.
8. **Docs:** DEC-SCOPE-153, API §12BU, RBAC §2.79, DATA_MODEL, SCREEN_CATALOG, and the backlog status.
