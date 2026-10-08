# rec-017 implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-017-candidate-requirement-tracking-design.md`. TDD per task (red → green → refactor). Focused
tests run in the `api-test` / `web-test` containers.

## Phase 3 review outcomes (folded into the tasks)

**API:**
- Status writes are POST sub-resources, matching the rec-007 `/status` idiom.
- Statuses: 201 on create; 404 out of scope (no existence leak); 403 for the wrong role before 409 for the wrong state; 422 for an unknown
  status or a bad candidate.
- The bodies are Pydantic models with `extra="forbid"`, and the note is trimmed to at most 500 characters.
- The legacy contracts are kept: same paths and payloads. Each response gains `status_label`; nothing is removed.
- **Transactions:**
  - The application row is locked `FOR UPDATE` before a status change, so two concurrent moves serialise and the second sees the new
    status.
  - On create, a race is decided by the unique index: IntegrityError becomes 409.
  - The company row is locked inside `apply_event`.

**Security:**
- IDOR: every `{id}` resolves through the requirement scope (`load_scoped`). An application resolves through its job's scope.
- The candidate must pass `pool_filter`, so a backfilled student who has not opted in can never be added by a recruiter.
- Logs and audit rows carry ids and statuses only, never names or contact data.
- React escapes all text, so there is no XSS. CSRF uses the existing cookie and same-origin model; nothing changes.

**Frontend:**
- Reuse `SearchableSelect`, `sendJson`, `LocalTime`, the `action-card` sections and the badge styles.
- The tables scroll horizontally inside `.table-wrap` on mobile.
- Labelled controls; a live region for notices; focus returns after an action.

## Tasks

1. **Models + constants:** add `APPLICATION_STATUSES`, `APPLICATION_CHECKS` and the `JobApplication` columns and indexes, and add
   `JobApplicationStatusHistory`.
2. **Migration 0119 + `test_rec_017_migration.py`:** the CHECK matches the models; a SQL-fixture backfill (links, new candidates, mapping,
   history); duplicate refusal; downgrade refusal.
3. **`services/applications.py` + `test_rec_017_engine.py`:** the transition table, the Joined gate, `follow`, `candidate_for_student`
   (link or create), and `create` (409 and the company event).
4. **Recruiter API + `test_rec_017_api.py`:**
   - AC1 and AC2.
   - Add with each initial status.
   - Status change and history; notification to the student.
   - The role and scope matrix; a candidate outside the pool or archived; a closed requirement.
   - The candidate applications tab.
5. **Legacy writers and readers:** workflows, employer, portal, lookups, admin, seed and `HIRED_APPLICATION_STATUSES`. Update the tests that
   insert rows directly or assert legacy words (AC3/AC4), and add `test_rec_017_legacy.py` (apply, PATCH mapping, interview and offer
   follow, employer shortlist).
6. **Web lib + components + vitest:** `recruiterApplications.ts`, `RecruiterRequirementCandidates`, `RecruiterCandidateApplications`, and
   the legacy panel labels.
7. **e2e `rec-017-applications.spec.ts`.**
8. **Docs:** API_CONTRACT §12BD, RBAC_MATRIX §2.62, DATA_MODEL, the DEC-SCOPE-136 register entry, SCREEN_CATALOG, and the backlog status
   line.
