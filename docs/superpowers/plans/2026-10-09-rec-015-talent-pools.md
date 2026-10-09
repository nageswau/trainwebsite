# rec-015 talent pools — implementation plan

Spec: `docs/superpowers/specs/2026-10-09-rec-015-talent-pools-design.md` (DEC-SCOPE-159, P1–P8). TDD per task; focused tests only.

1. **Model + migration 0141** — `TalentPool` in `models.py`; `0141_talent_pools.py` (guarded create, P3 seed, guarded downgrade).
   Test: `test_rec_015_migration.py` (seed present, re-run idempotent, frozen copies match the model).
2. **resolve_terms(strict=False)** — unknown terms resolve to an empty id set. Test: rec-013 suite still green + a pool test.
3. **Schemas** — `TalentPoolCreate` / `TalentPoolUpdate` (rec-013 caps, skill-or-experience rule, min ≤ max) + labels.
4. **Service + routes** — `services/talent_pools.py`, `api/recruiter_pools.py`, register in `main.py`. Tests: `test_rec_015_talent_pools.py`
   (AC1, AC2, OR pool, 422s, 409, deactivated skill, roles, counts, exclusions).
5. **Web** — `lib/recruiterPools.ts`; export `SkillChips` / `Card`; `RecruiterTalentPools.tsx` (list + form) and `RecruiterTalentPool.tsx`
   (pool page); pages `app/recruiter/pools{,/[id]}`; nav. Unit test `RecruiterTalentPools.test.tsx`; e2e `rec-015-talent-pools.spec.ts`.
6. **Docs** — DEC-SCOPE-159, API §12CA, RBAC §2.85, SCREEN_CATALOG, DATA_MODEL, backlog status.

Phase-3 review notes (applied to the spec):
- API: one list query + one count query for all pools (no N+1); PATCH locks the row; the unique index is the race guard (409).
- Security: pools are division-global (R11), so there is no per-owner IDOR surface; role check runs before the body is read; names and
  terms are bound parameters / React text (no SQL or HTML injection); logs carry ids and counts only.
- Frontend: loading / empty / error states on both pages; the form keeps the Find Candidates chip input (keyboard: Enter adds);
  errors are `role="alert"`; cards stack on mobile as on Find Candidates.
