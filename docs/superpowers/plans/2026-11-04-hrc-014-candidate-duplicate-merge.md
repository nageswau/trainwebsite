# hrc-014 implementation plan

Design: `docs/superpowers/specs/2026-11-04-hrc-014-candidate-duplicate-merge-design.md` (DEC-SCOPE-377).

1. **RBAC** — `rbac.ACTIONS += "merge"`, `CATALOGUE["candidates"] = merge`, `DEFAULT_GRANTS["placement_manager"]`; update the nehn-005
   pins. Test first (catalogue + default holder).
2. **Model + migration 0256** — `Candidate.merged_*`, `CandidateDuplicate`, seed grant. Migration test (upgrade/downgrade, CHECKs pinned).
3. **Detection service** `services/candidate_duplicates.py` — `detect(db, candidate_id=None)` (two equality self-joins, ON CONFLICT DO
   NOTHING), `queue`, `dismiss`. Hook into create/update routes. Tests: each signal, no pair across archived/out-of-pool, dismissed stays.
4. **Merge service** `services/candidate_merge.py` — find/lock/check/merge/preview. Tests per child table, resumes, same-job rules,
   student-login rules, audit, queue closure, restore blocked, concurrency (second merge 409).
5. **Routes** `api/recruiter_candidate_duplicates.py` + merge routes in `recruiter_candidates.py`; `merged_into` on the detail; restore
   guard. Tests: 403/404/409/422 matrix.
6. **Web** — `lib/recruiterDuplicates.ts`, `RecruiterDuplicateQueue.tsx`, `RecruiterCandidateMerge.tsx`, pages, nav, detail banner.
   Vitest component tests.
7. **e2e** `hrc-014-duplicates.spec.ts`; docs (decision register, API §12JV, RBAC §2.275, RTM, backlog status).
