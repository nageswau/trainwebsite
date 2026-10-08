# rec-008 JD management — implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-008-jd-management-design.md` (DEC-SCOPE-132, 0117, §12AZ, §2.58).

## Tasks (TDD: red → green → refactor per task)

1. **Model + migration.** `JobDescription` and `JD_NUMBER_SEQ` go in `models.py`; `CHECKS` mirrors the migration. Add
   `alembic/versions/0117_job_descriptions.py` with guarded creation and a downgrade that refuses while JDs exist. Test:
   `test_rec_008_migration.py` (CHECK strings equal, head = 0117, table and indexes present).
2. **Schema.** `RecJdCreate` (extra=forbid; JD3 lengths; role required; control-character rule via `_rec_requirement_text_type`).
3. **Service** `services/job_descriptions.py`:
   - `read_file` reuses `candidates.read_resume`'s sniffing, generalised as `read_document(file, max_bytes, label)`; rec-009 behaviour is
     unchanged.
   - `store`, `discard` and `next_number`.
   - `add_version` locks the requirement (caller), flips current and inserts.
   - `fields_from_requirement`, `check_contact` and `jd_out`.
4. **Routes** `api/recruiter_job_descriptions.py` (GET, POST, PUT file, GET file), registered in `main.py`. Tests:
   - AC1: upload is linked, with the version shape.
   - AC2: v2 becomes current and v1 is kept; carry-forward both ways.
   - AC3: PNG → 415, 6 MB → 413, empty → 422.
   - Contact from another company → 422.
   - Out-of-scope recruiter → 404; manager/BDM write → 403; hr_team → 403.
   - Cancelled → 409.
   - Download audit and headers; a version without a file → 404.
   - `closing_date_differs`.
   - Stored file discarded on failure.
5. **Web lib** `lib/recruiterJd.ts`: types, URLs, `jdValues` (from the current version or the requirement), `jdBody`,
   `requirementChangesFromJd` (the JD6 diff). Test with vitest.
6. **Component** `RecruiterRequirementJd.tsx`, wired into `RecruiterRequirementDetail` and `[id]/page.tsx` (parallel server fetch;
   failure → section error state, page still renders).
7. **e2e** `tests/e2e/rec-008-jd.spec.ts`: create JD, upload v2, JD → requirement confirm.
8. **Docs:**
   - DEC-SCOPE-132; API §12AZ; RBAC §2.58; DATA_MODEL.
   - SCREEN_CATALOG row; backlog status.

## Phase 3 review notes (applied to the plan)

- **API:** additive routes only; existing requirement responses are unchanged. `201` on each version write (not idempotent: each call is a
  version, like rec-009 resumes). The `{version}` path param is an int, so a non-int is `422`. Transaction: requirement row lock → max
  version → flip → insert → audit → one commit.
- **Security:**
  - Scope comes from `load_scoped` before any byte is read (404 first).
  - Role is checked before the body is read.
  - The type is judged by the bytes; the size cap is read with `read(max+1)`.
  - The file name is a display name only (`Path(...).name[:255]`). The storage key is server-generated.
  - The download name is built from the JD number. Headers are `nosniff`, `Cache-Control: no-store` (the `HEADERS` idiom).
  - Audit and logs hold no free text.
  - No HTML is rendered from JD text (React escapes; multiline via the existing `multiline`).
  - CSRF follows the existing cookie/session middleware (unchanged).
- **Frontend:**
  - Reuse `DetailList`, `multiline`, `BdmConfirm`, `LocalTime`, `sendJson`/`sendRequest`, and the `action-card`/`form-grid`/`field`
    classes.
  - Labels on every input; busy and duplicate-submit guards.
  - `role="alert"` errors, a `role="status"` notice, and focus moved to the notice after writes.
  - Responsive via the existing grid.
