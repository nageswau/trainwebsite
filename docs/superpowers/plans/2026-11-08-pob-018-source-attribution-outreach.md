# pob-018 — implementation plan

Design: `docs/superpowers/specs/2026-11-08-pob-018-source-attribution-outreach-design.md` (DEC-SCOPE-427).

| # | Task | Test first |
|---|---|---|
| 1 | Migration `0308_candidate_sourcing` (guarded, backfill `source_date`, seeds) + model columns/checks | `test_pob_018_migration.py` (chain, frozen checks, round trip, backfill) |
| 2 | `services/candidate_sourcing.py`: attribution checks (A3), outreach (A4/A5), verify (A6), `permitted` (A7), `out` (A10) | `test_pob_018_source_attribution.py` AC1–AC3, A3–A5 |
| 3 | Schemas + create/PATCH accept attribution; `PUT /outreach`, `POST /verify`; detail/list output | same file: routes, 403/404/409/422 |
| 4 | AC3 gate in `profile_sharing._candidates`; existing share fixtures record a permission | `test_rec_019_shares.py` and the other share tests |
| 5 | Anonymiser clears the new free text (A9) | AC test on anonymise |
| 6 | rec-038 matrix rows for the two routes | `test_rec_038_matrix` |
| 7 | Web: `lib/recruiterCandidates.ts` types/helpers, `RecruiterCandidateSourcing` card, detail page | vitest `RecruiterCandidateSourcing.test.tsx` |
| 8 | Playwright `pob-018-source-attribution.spec.ts` | verify → date shown; consent → share allowed |
| 9 | Docs: register, API §12LT, RBAC §2.318, data model, RTM, backlog status | — |
