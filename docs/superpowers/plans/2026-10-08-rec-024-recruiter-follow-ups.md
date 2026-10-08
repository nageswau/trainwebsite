# rec-024 implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-024-recruiter-follow-ups-design.md`. TDD per task: red, green, then refactor. Lite tests only.

1. **Model + migration.** Add `RECRUITER_FOLLOW_UP_REASONS`, `RECRUITER_FOLLOW_UP_CHECKS` and `RecruiterFollowUp` in `models.py`, and
   `0114_recruiter_follow_ups.py`. Test: `test_rec_024_migration.py` (CHECKs equal the model, a single head, the table and indexes
   exist).
2. **Schemas.** `RecFollowUpCreate`, `RecFollowUpUpdate` (due_at and reason not nullable), `RecFollowUpComplete`. Cancel reuses
   `BdmAppointmentReason`.
3. **Service + routes.** `services/recruiter_follow_ups.py`: scope, load_for_write, check_links, create, the cap, output and the three
   lists. `api/recruiter_follow_ups.py`: six routes, registered in `main.py`. Test: `test_rec_024_follow_ups.py`.
4. **Next follow-up.** A correlated min() subquery in the company list, detail and contact list, plus the schema fields. Tests in the same
   file.
5. **Web.**
   - `lib/recruiterFollowUps.ts`.
   - `RecruiterFollowUpForm`, `RecruiterFollowUpItem`, `RecruiterCompanyFollowUps`, `RecruiterFollowUpsPanel`.
   - `app/recruiter/follow-ups/page.tsx`.
   - Nav entries; "Next follow-up" in the details and contacts.
   - vitest.
6. **e2e:** `rec-024-follow-ups.spec.ts`.
7. **Docs.** DEC-SCOPE-129, API §12AW, RBAC §2.55, DATA_MODEL, SCREEN_CATALOG, the backlog status.

**Regression watch:**
- rec-003 and rec-004 tests: row and contact output gain a key.
- The navigation recruiter test.
- The alembic single-head tests.
