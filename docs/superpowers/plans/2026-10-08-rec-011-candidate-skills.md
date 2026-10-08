# rec-011 — Candidate skill profile (plan)

Spec: `docs/superpowers/specs/2026-10-08-rec-011-candidate-skills-design.md`. Branch `feature/rec-011`. Each task uses TDD (red, then
green, then refactor) and runs only the focused tests.

1. **Data.** Add `CANDIDATE_SKILL_*` constants and the `CandidateSkill` model. Add migration `0120_candidate_skills`.
   - Test: `test_rec_011_migration.py` (CHECKs = model, indexes, single head, downgrade refusal).
2. **Schemas.** Add `CandidateSkillCreate`, `CandidateSkillUpdate`, `CandidateSkillStatusChange` and their field labels.
3. **Service and API.** Add `services/candidate_skills.py` and `api/recruiter_candidate_skills.py` (router in `main.py`).
   - `test_rec_011_candidate_skills.py`: roles and pool, add (AC1), duplicate 409 by name, case and alias (AC2), unknown or inactive
     skill 422, validation, PATCH and no-op audit, delete, status change who/when and back to claimed (AC3), archived 409, the cap,
     the race backstop.
4. **Merge.** Add `merge` to `services/skills.py` and `POST /recruiter/skills/{id}/merge` to `api/recruiter_skills.py`.
   - `test_rec_011_skill_merge.py`: re-point, stronger-status clash, job skills, aliases/related moved, A deleted, A's name resolves,
     refusals, roles.
5. **Web.** Add `lib/recruiterCandidateSkills.ts` and `RecruiterCandidateSkills`; wire it into `RecruiterCandidateDetail`. Add the merge
   section to `RecruiterSkillDetail`.
   - vitest for the lib, the card and the merge section.
6. **e2e.** Add `rec-011-candidate-skills.spec.ts`.
7. **Docs.** API_CONTRACT §12BC, RBAC_MATRIX §2.61, DATA_MODEL, DEC-SCOPE-135, the backlog status, SCREEN_CATALOG.
8. **Checks.** Lite backend (rec-006/007/009/011), vitest, tsc, eslint, next build, then e2e and browser QA.
