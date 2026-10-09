# rec-016 — Requirement matching: implementation plan

The design is in `docs/superpowers/specs/2026-10-09-rec-016-requirement-matching-design.md`. Every task follows TDD: a failing test first, then the code, then the focused tests again.

1. **The `allocate` pure function.** Unit tests come first: totals of 100, exact sums, the largest remainder, and experience/location at 10 points each. Then write `services/matching.allocate`.
2. **The matches query and route.** API tests come first (Java example, AC1/AC2, AND, preferred-only, related, not-in-master, no_skills, experience, location/remote, rejected status, pool/archived, paging). Then write `matching.plan` / `matching.matches` and `GET /recruiter/requirements/{id}/matches`.
3. **Roles.** Tests for BDM and hr_team 403, an out-of-scope recruiter 404, a manager who reads with `can_shortlist`/`can_edit_weights` false, super_admin, and Shortlist via rec-017 (once, then 409, AC3).
4. **The weights PUT.** Tests for 422 on a foreign or duplicate id or a weight out of range, 403 for a manager, 409 for a cancelled requirement, the audit row, no write when nothing changed, and matches that reflect the new weights. Then add the `RecSkillWeights` schema and the route.
5. **Web lib + section.** Write `lib/recruiterMatching.ts`, a vitest for `RecruiterRequirementMatches` (loading, error/retry, no_skills, empty, rows/breakdown, shortlist, weights form, read-only manager), then the component, then mount it in `RecruiterRequirementDetail`. Add the `refreshKey` to `RecruiterRequirementCandidates`.
6. **E2E.** Write `tests/e2e/rec-016-matching.spec.ts`: seed through the API, view the ranking, shortlist, adjust weights, and check a mobile viewport.
7. **Docs.** Add DEC-SCOPE-157 (M1–M8), API §12BY, RBAC §2.83, SCREEN_CATALOG, and the backlog status line.
8. **Lite verification.** Run `test_rec_016_matching.py`, `test_rec_017_tracking.py`, `test_rec_007_requirements.py` and `test_rec_013_find_candidates.py`; vitest for the touched components; tsc, eslint and the next build; and the e2e for rec-016 and the rec-017 neighbour.
