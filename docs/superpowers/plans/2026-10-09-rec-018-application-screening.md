# rec-018 — Screening form + result (plan)

The spec is `docs/superpowers/specs/2026-10-09-rec-018-application-screening-design.md` (DEC-SCOPE-140, SC1–SC8). The work is TDD, one
task at a time.

1. **Model and migration.** Add `SCREENING_RESULTS`, `SCREENING_CHECKS` and `ApplicationScreening` to `models.py`. Add
   `0125_application_screenings`. Add `test_rec_018_migration.py`, covering the chain, model = migration, the round trip and the
   downgrade refusal.
2. **Schema, service and routes.**
   - `RecScreeningIn`: `extra=forbid`, the SC6 ranges, and the SC7 model validator.
   - `services/application_screening.py`, with `read` and `save` (SC3–SC5).
   - `GET` and `PUT /recruiter/applications/{id}/screening`.
   - `test_rec_018_screening.py`, covering AC1, AC2, a rating out of range, Hold and re-screening, a closed application, a no-op save, the
     audit holding names only, and the role/scope matrix.
3. **Board flag.** `item_out` gains `screening_result`. The list query and `_item` read it.
4. **Web.**
   - Add the lib types and guard.
   - Add `RecruiterApplicationScreening.tsx`.
   - In `RecruiterRequirementCandidates`, add the toggle and the badge.
   - Add the vitest `RecruiterApplicationScreening.test.tsx`.
5. **e2e.** `rec-018-screening.spec.ts`: a writer screens a candidate to Shortlisted and sees the status and the badge; Hold, then a
   re-screen; Rejected without remarks is blocked.
6. **Docs.** Update the DEC register (DEC-SCOPE-140), API_CONTRACT §12BH, DATA_MODEL, RBAC_MATRIX §2.66, SCREEN_CATALOG and the backlog
   status.

## Phase 3 review notes

- **API:**
  - PUT has replace semantics: the whole form is sent, matching tel-009 QD2.
  - The responses reuse rec-017's application item.
  - 409 means a state conflict (not open), and 422 a validation failure.
  - There is one transaction: lock, upsert, move, audit, commit.
- **Security:**
  - The scope comes from rec-017's `load_scoped`, so an object out of scope is a 404 and there is no IDOR.
  - The writer check is `require_writer`, which logs a refusal.
  - Salary is never logged or audited: the audit holds field names only.
  - No employer, student or `hr_team` route exposes a screening.
  - The text rules (no control characters) come from rec-007's validator.
  - CSRF is handled by the existing `sendJson` and cookie middleware.
- **Frontend:**
  - It reuses the board's disclosure pattern (`aria-expanded`), the `form-error` and live-region notices, and the labelled controls.
  - The form is a stacked grid, so it fits at phone width.
  - The Save button disables while saving, which stops a duplicate submit.
