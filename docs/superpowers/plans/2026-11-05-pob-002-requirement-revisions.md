# pob-002 Requirement Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, chosen by the owner's "proceed" instruction).
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Requirement revisions, hiring-process fields, per-requirement commercial terms and a backup owner.

**Architecture:**
- New `job_revisions` table plus 9 nullable `jobs` columns (migration 0281).
- A new `services/job_revisions.py` owns snapshot/record/read. The requirement PATCH, the create route and the rec-031 fee PUT call it
  in their own transaction.
- Commercials are gated with pob-001's `recruiter_contracts.commercial_access`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2; Next.js 15 / React client components, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-05-pob-002-requirement-revisions-design.md` (R1–R12).

## Global Constraints
- Every new PATCH field is optional; omitted = unchanged, null = clear. `extra="forbid"` stays.
- Commercial keys: `fee_basis, fee_value, payment_trigger, payment_days, payment_terms, replacement_terms`. They are absent (never null)
  without `commercials.client.view`.
- `payment_trigger` ∈ `on_joining | days_after_joining | on_invoice`. `payment_days` is 1–365 and present iff `days_after_joining`.
- `interview_rounds` / `screening_steps`: ≤10 items of ≤120 characters. `expected_tat_days`: 1–365.
- One transaction per write; nothing in services commits.

## Review Focus
1. **Concurrent PATCHes on one job.** Each gets its own revision number. The job row lock is taken before numbering, and a unique
   `(job_id, revision)` is the backstop. Test: two sequential edits give revisions 2 and 3.
2. **A skills-only change.** It writes a revision (skills are material). Test in Task 2.
3. **Clearing the backup by sending null.** It writes a revision and audits. Test in Task 3.
4. **`compare_to` equal to `n`, or unknown.** Equal gives empty changes; unknown gives 404. Test in Task 2.
5. **A recruiter without commercials editing hiring fields.** The edit succeeds, and the revision read hides the commercial keys. Test
   in Task 4.

---

### Task 1: Model + migration 0281
**Files:**
- Modify: `apps/api/app/models.py` (Job columns, `JOB_REVISION_CHECKS`, `JOB_PAYMENT_TRIGGERS`, `class JobRevision`)
- Create: `apps/api/alembic/versions/0285_job_revisions.py`
- Test: `apps/api/tests/test_pob_002_migration.py`

**Produces:** `Job.interview_rounds: list|None` (JSON), `screening_steps`, `decision_maker_contact_id`, `expected_tat_days`,
`payment_trigger`, `payment_days`, `payment_terms`, `replacement_terms`, `backup_owner_user_id`; `JobRevision(job_id, revision, snapshot,
changed_fields, reason, author_user_id, created_at)`; `JOB_TERMS_CHECKS` dict (frozen in the migration as `CHECKS`).

- [ ] **Write the tests:**
  - `test_chain` (revision `0285_job_revisions`, down `0284_interview_panel`);
  - `test_checks_are_frozen_copies` (`_migration.CHECKS == {**JOB_TERMS_CHECKS, **JOB_REVISION_CHECKS}`);
  - `test_round_trip` (upgrade adds the table and columns; downgrade drops them; existing jobs keep their rows).
- [ ] **Run them:** they fail (no file). **Implement. Run:** pass. **Commit.**

### Task 2: Revisions service + PATCH/create/fee wiring + read routes
**Files:**
- Create: `apps/api/app/services/job_revisions.py`
- Modify: `apps/api/app/api/recruiter_requirements.py`, `apps/api/app/api/recruiter_revenue.py` (fee PUT),
  `apps/api/app/schemas.py` (`revision_reason`)
- Test: `apps/api/tests/test_pob_002_revisions.py`

**Produces:**
- `async snapshot(db, job) -> dict`
- `async record(db, user|None, job, changed: list[str], reason: str|None) -> int|None`: writes the baseline first when the job has no
  revisions and `changed`.
- `async record_created(db, user, job) -> None`
- `async list_page(db, job, view: bool, limit, offset) -> dict`
- `async read(db, job, n, compare_to, view: bool) -> dict`
- `COMMERCIAL_KEYS`, `LABELS: dict[str, str]`

- [ ] **Tests:**
  - `test_create_writes_revision_1`
  - `test_headcount_2_to_3_writes_one_revision_with_the_diff`: vacancies [2, 3] in revision 2 changes; revision 1 snapshot vacancies 2.
  - `test_no_change_writes_no_revision` (same values and an empty body)
  - `test_skills_only_change_is_a_revision`
  - `test_legacy_job_gets_a_baseline_then_the_edit` (delete revision rows to simulate; then revisions 1 (author null) and 2)
  - `test_compare_to_and_unknown_revision_404`
  - `test_out_of_scope_recruiter_gets_404`
  - `test_fee_override_writes_a_revision`
  - `test_reason_is_kept`
- [ ] **RED → implement → GREEN.** Routes are `GET /{id}/revisions` and `GET /{id}/revisions/{n}` (NO_STORE).
- [ ] Add rec-038 rows for the two routes. **Commit.**

### Task 3: Hiring process + backup owner
**Files:**
- Modify: `schemas.py` (fields + validators), `services/recruiter_requirements.py` (`REC_REQUIREMENT_FIELDS` additions,
  `check_references` decision-maker company rule, scope, `_manages_owners`, `requirement_out`, `audited_values` names),
  `services/requirement_owners.py` (`set_primary` clears the backup; `release` clears backups + audit)
- Test: `tests/test_pob_002_fields.py`

- [ ] **Tests:**
  - `test_hiring_process_round_trip`
  - `test_decision_maker_must_be_active_contact_of_same_company_422`
  - `test_limits_422` (11 rounds; tat 0)
  - `test_backup_reads_edits_and_manages_owners`
  - `test_non_owner_recruiter_cannot_set_backup_403`
  - `test_backup_must_be_active_recruiter_422_and_not_primary_409`
  - `test_reassign_to_backup_clears_it`
  - `test_deactivating_backup_clears_it`
  - `test_clearing_backup_writes_revision`
- [ ] **RED → GREEN. Commit.**

### Task 4: Commercial terms + gate
**Files:** `schemas.py`, `services/recruiter_requirements.py` (`commercial_terms` block, `can_edit_terms`, PATCH 403),
`services/job_revisions.py` (strip). **Test:** `tests/test_pob_002_commercials.py`.

- [ ] **Tests:**
  - `test_terms_inherit_from_contract_until_overridden`
  - `test_days_required_with_days_after_joining_422`
  - `test_without_view_no_terms_block_no_commercial_keys_in_revisions_and_patch_403`
  - `test_view_without_edit_patch_terms_403_hiring_edit_ok`
  - `test_manager_sees_terms`
- [ ] **RED → GREEN. Commit.**

### Task 5: Web
**Files:**
- Modify: `apps/web/lib/recruiterRequirements.ts` (types, FORM_FIELDS, valuesOf/wire for lists), `components/RecruiterRequirementForm.tsx`
  (Hiring process / Commercial terms / Backup owner / reason), `components/RecruiterRequirementDetail.tsx` (rows, terms card, revisions)
- Create: `components/RequirementRevisions.tsx`
- Tests: `tests/lib/pob002Requirement.test.ts`, `tests/components/pob002RequirementRevisions.test.tsx`

- [ ] **Tests:**
  - `wire("interview_rounds", "A\n\nB") → ["A","B"]`; an empty list → null;
  - the revisions list renders, "View revision 2" shows `Number of vacancies: 2 → 3`, and an error shows the alert;
  - the commercial terms section is hidden without `can_edit_terms`.
- [ ] **RED → GREEN.** Then tsc, eslint and vitest on the touched files. **Commit.**

### Task 6: Docs + e2e
- Add `DEC-SCOPE-407`, API §12LA, RBAC §2.300, DATA_MODEL, the backlog status line and the RTM row if one exists.
- Add the e2e spec `tests/e2e/pob-002-revisions.spec.ts`: edit headcount, view revision 2's diff, mobile width without sideways scroll.
- **Commit.**
