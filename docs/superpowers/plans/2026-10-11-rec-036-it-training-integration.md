# rec-036 implementation plan

Spec: `docs/superpowers/specs/2026-10-11-rec-036-it-training-integration-design.md`. TDD per task; focused tests only.

1. **Model + migration** — `ProgramSkill` in `models.py`; `0147_program_skills` (create if missing, downgrade refuses with rows);
   `tests/test_rec_036_migration.py` (chain, model/migration parity, round trip, refusal).
2. **Program tags API** — `services/course_skills.py` (`program_skills_out`, `set_program_skills`, `skill_options`); routes in
   `admin.py`. Tests: roles (it_admin, super_admin write; recruiter/overseas_admin 403), unknown/inactive/too many → 422, replace semantics,
   audit row, options lookup.
3. **Grant** — `course_skills.grant` + hooks (`placement_pool.opt_in`, `workflows.issue_certificate`, PUT tags). Tests: AC1 (opt-in after
   certificate; certificate after opt-in; tag after both), CI4 statuses, CI5 upgrade/keep, CI6 removed tag keeps rows, not opted in /
   archived untouched, Java completer found by skill search (positive scenario).
4. **Merge** — `skills.absorb` re-points tags; test in the merge suite style.
5. **Journey** — `course_skills.journey` + `GET /recruiter/candidates/{id}/journey`. Tests: AC2 stages with dates, external candidate,
   non-opted-in 404, employer/other role 403, hr_team reads.
6. **Web** — `lib/programSkills.ts`, tags editor in `AdminProgramManagementPanel`, `lib/candidateJourney.ts` +
   `RecruiterCandidateJourney.tsx` on the detail page. Vitest for both.
7. **E2E** — `tests/e2e/rec-036-it-integration.spec.ts`.
8. **Docs** — DEC-SCOPE-176, API §12CQ, RBAC §2.102, DATA_MODEL, backlog status.

## Phase 3 review notes (applied above)

- API: PUT is a full replace (idempotent); GET/PUT share one shape; 422 one-sentence errors via `_parse`; no change to existing contracts
  (opt-in and certificate responses unchanged).
- Transactions: every grant runs inside the caller's transaction; candidates locked FOR UPDATE in id order (no deadlock with rec-011,
  which locks one candidate row).
- Frontend: reuse `SearchableSelect`, `sendJson`, `LocalTime`, `action-card`; no new dependency; keyboard reachable; 375px layout.
- Security: role check before any read; journey behind `candidates.load` (pool filter → 404); no lead PII (phone/email/message) in the
  journey; audit ids only.
