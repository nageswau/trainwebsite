# rec-017 — Candidate + Requirement tracking (design)

- **Backlog:** `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-017 (§12 lines 532–554, S2-§14 lines 1563–1583). Dependencies rec-007 (PR #166)
  and rec-009 (PR #155) are merged.
- **Decision:** DEC-SCOPE-135. **Migration:** `0120_job_application_tracking`. **API:** §12BC. **RBAC:** §2.61. (Re-check on `origin/main`
  before merging.)
- **Owner answers (2026-10-08), recorded as UNVERIFIED until DEC-SCOPE-135 is confirmed:**
  - **A1 (Q-17a):** the statuses are the 8 §12 statuses plus `withdrawn`. There is no `on_hold`; rec-018's Hold is a flag. The legacy values
    map directly: applied→sourced, screening→screened, shortlisted→shortlisted, interview_scheduled→interview,
    offer_received→selected, hired→joined, rejected→rejected, withdrawn→withdrawn.
  - **A2 (Q-17b):** transitions are permissive, with one gate on Joined (§2).
    - An interview result of selected moves the application to Selected (it used to go to Shortlisted). A result of rejected moves it to
      Rejected.
    - Creating an offer moves the application to Selected. An offer marked accepted or joined moves it to Joined.
  - **A3:** in the backfill, a student whose email or mobile already belongs to an external candidate is **linked** to that candidate,
    and the candidate stays in the pool (`opted_in=true`). Every other student gets a new candidate with `opted_in=false`. The runtime
    create-or-link follows the same rule.
  - **A4:** `drive_id` is deferred to rec-029, which owns `recruitment_drives`. Student self-apply and the employer shortlist create or
    link the student's candidate with `opted_in=false`; the opt-in prompt stays in rec-010. The history table is
    `job_application_status_history`, because `application_status_history` already belongs to overseas applications.

## 1. Data (migration 0120)

**Changes to `job_applications`:**

- `candidate_id` uuid, FK to `candidates`. It is NOT NULL after the backfill.
- `student_id` becomes **nullable**, because an external candidate has no login. When the candidate has a `user_id`, `student_id` equals it,
  and the service keeps the two in step.
- `stage_changed_at` timestamptz, NOT NULL, default now().
- `added_by_user_id` uuid, nullable, FK to `users`. It is NULL for a student self-apply and for migrated rows.
- `ck_job_applications_status`: `status IN (sourced, screened, shortlisted, profile_shared, interview, selected, joined, rejected,
  withdrawn)`. The ORM default becomes `sourced`.
- `uq_job_applications_candidate_job` (candidate_id, job_id).
- `ix_job_applications_job_status` (job_id, status) and `ix_job_applications_candidate` (candidate_id).

**New table `job_application_status_history`:** `id`, `application_id` (FK, RESTRICT), `from_status` (NULL means created), `to_status`,
`note` (500), `changed_by_user_id` (NULL means the system or the migration), and `created_at`. It has no status CHECK, so the history
survives a future change to the catalogue. It is append-only, with an index on (application_id, created_at).

**Backfill (upgrade order).** Every step is guarded, because 0001 `create_all` already builds the new shape on a fresh database.

1. Pre-check: if any (job_id, student_id) pair is duplicated, the migration **refuses** with `RuntimeError` and lists the pairs.
   - Every insert path has always returned 409 on a duplicate, so none is expected.
   - A merge would have to re-point interviews and the one-per-application offers, so the migration leaves that to a person.
2. The candidate source is the `Edusphere students` row of `rec_candidate_sources`, matched case-insensitively. It is inserted if missing.
3. The migration finds every student in `job_applications.student_id` or `placement_profiles.student_id` who has no linked candidate.
   - If the student's email (lower-cased) or mobile (normalised with `app.notifications.phone.normalise_phone`) matches an unlinked
     candidate, that candidate is linked: `user_id` is set and `opted_in` becomes true (A3). The email match wins over the mobile match.
   - Otherwise a new candidate is inserted. Its code is `CAN-` plus the next value of `candidate_code_seq`. It takes the name, the email,
     and the mobile when that is unused (otherwise NULL). The source is the one from step 2, the status is `available`, `opted_in` is
     false, and `created_by_user_id` is the student.
4. `job_applications.candidate_id` is set to the candidate whose `user_id` equals `student_id`.
5. Each existing row gets a history row: from NULL to the mapped status, with the note `Legacy status '<old>'` and `changed_by` NULL.
   - The status is then remapped (A1). An unknown value maps to `sourced`; its note keeps the original value.
   - `stage_changed_at` is set to `updated_at`.
6. `candidate_id` is set NOT NULL, `student_id` drops NOT NULL, and the CHECK, the unique constraint and the indexes are added.

**Downgrade:** it refuses while any application has no student (an external candidate) or any history row was written by a user.
Otherwise it restores the legacy values from the notes and drops what it added. The backfilled candidates are kept, because candidates are
archived and never deleted (rec-009).

## 2. Status engine: `services/applications.py` (the single writer)

- `STATUSES`, `LABELS`, `LEGACY` (old word → new), and `TRANSITIONS`:
  - Any of sourced, screened, shortlisted, profile_shared or interview can move to any other of them, or to selected, rejected or
    withdrawn.
  - Selected can move to joined, rejected or withdrawn.
  - Joined is terminal; rec-023 extends this with Did Not Join.
  - Rejected and withdrawn can only reopen to sourced.
  - Joined can be reached **only from Selected**. Any other move to it is a 409: "Joined needs the candidate to be Selected (an offer)
    first".
- `change_status(db, actor, application, target, note)`: checks the transition (a same-status move is a 409), writes history, sets the
  status and `stage_changed_at`, and returns the previous status. The explicit status routes use it: the new recruiter route and the
  legacy PATCH.
- `follow(db, actor, application, target, note)`: used by the legacy side effects (interview scheduling and results, offers, employer
  interview). It moves the application only when the transition is allowed and the status differs. Otherwise it leaves the status alone.
  This keeps those routes from failing where they used to succeed.
- `candidate_for_student(db, student)`: the linked candidate, otherwise A3's link, otherwise a new candidate (`opted_in=false`).
- `create(db, actor, job, candidate, status, note, resume_url)`:
  - A duplicate (candidate, job) is a 409, which the unique index also enforces under a race.
  - It writes the history row from NULL.
  - It fires rec-005's `candidates_sourcing` event on the company, after locking the company row. `apply_event` only moves forward.
- `notify_student(db, application)`: when the application has a student, it adds the existing ENH-014 in-app row and queued deliveries.
  The message uses the status label.
- Output helpers: `application_row` and `history_out`.

## 3. API (§12BC)

Router `api/recruiter_applications.py`. Every write is one transaction.

| Route | Who | Rules |
|---|---|---|
| `GET /recruiter/requirements/{id}/candidates?status=` | the requirement's readers (`caller_scope`: recruiter own, manager team, super_admin, assigned BDM) | Out of scope returns 404. Returns `{items, statuses}`, where each item carries `allowed_statuses`. |
| `POST /recruiter/requirements/{id}/candidates` `{candidate_id, status?, note?}` | `placement_team` in scope, `super_admin` | `status` is sourced, screened or shortlisted (default sourced). Wrong role is 403. A closed or cancelled requirement is 409. A candidate that is not in the pool or is archived is 422. A duplicate is 409. Returns 201 with the item. |
| `POST /recruiter/applications/{id}/status` `{status, note?}` | as above, scoped through the application's requirement | 422 for an unknown status, 409 for a move that is not allowed, 404 out of scope. It notifies the student. |
| `GET /recruiter/applications/{id}/history` | the requirement's readers | Newest first. |
| `GET /recruiter/candidates/{id}/applications` | candidate readers (rec-009 `READERS`) | One row per requirement: code, title, company, status, label and since. `in_scope` says whether the requirement page will open for the caller. |

**Legacy routes keep their paths and payloads** (A1/A2 mapping).

- `POST /workflows/it/jobs/{id}/apply` creates or links the candidate. It returns 409 "Already applied" for a duplicate and creates the
  application at `sourced`.
- `PATCH /workflows/it/job-applications/{id}` accepts the legacy words or the new keys. It runs `change_status`, except that the same
  status is a no-op 200, as before. It notifies the student.
- `POST /workflows/it/interviews` follows to `interview`. `PATCH /workflows/it/interviews/{id}` follows the result: selected→selected and
  rejected→rejected.
- `POST /workflows/it/offers` follows to `selected`. `PATCH /workflows/it/offers/{id}` with accepted or joined follows to `joined`.
- `POST /employer/shortlist` creates or links the candidate and uses `create(..., "shortlisted")`. `POST /employer/interviews` follows from
  sourced to shortlisted (the old applied→shortlisted). Its clash check uses `candidate_id`.
- The legacy reader routes keep their joins on `users`, so they show student applications as before.
  - Those routes are `/workflows/it/jobs/{id}/shortlist`, `/employer/shortlist`, `/employer/interviews`, `/admin/applications`,
    `/lookups/it-job-applications` and the student portal section.
  - They add `status_label` where they return a status. The portal and lookups show the label in place of the raw key.
- `recruiter_requirements.HIRED_APPLICATION_STATUSES` becomes `("joined",)`.

## 4. RBAC (§2.61)

- Writers are `placement_team` (in requirement scope) and `super_admin`. The manager, the BDM (R10) and `hr_team` read only; `hr_team`
  keeps its legacy screens. This matches rec-007's `can_edit` holders.
- The candidates tab follows rec-009's readers.
- Students, the employer and `hr_team` keep their legacy routes unchanged.
- Every route without a role check would be a defect. The tests assert every route against every role.

## 5. Web

- `lib/recruiterApplications.ts` holds the types, the URLs and the type guards.
- `RecruiterRequirementCandidates`, a section on the requirement page:
  - A table with code, name (linked to the candidate), status badge, since, and a History disclosure.
  - Writers also get "Add candidate": a `SearchableSelect` over `/recruiter/candidates?q=`, the initial status and a note.
  - Each row has a status change form (the allowed statuses plus a note).
  - It has loading, empty ("No candidates on this requirement yet.") and error states, and a live region for notices.
- `RecruiterCandidateApplications`, an "Applications" section on the candidate page: one status per company or requirement. It has an empty
  state and links only to in-scope requirements.
- In the legacy panels, `HrShortlistPanel` and the employer shortlist and interviews panels show `status_label`.

## 6. Tests

- **Backend `test_rec_017_*`:**
  - The migration: the CHECK and indexes equal the models; the backfill, collision linking, mapping, duplicate refusal, and downgrade
    refusal (run on SQL fixtures, the way rec-007 does).
  - The engine: the transition table and the Joined gate.
  - The routes: AC1 (ABC Interview vs XYZ Rejected); AC2 (duplicate add returns 409); a role and scope matrix; and the legacy routes
    mapping to the new statuses.
  - ADM-007, ADM-008, EMP-003/004/005, rpt-001, bdm-021 and enh-031 are updated only where they insert `JobApplication` rows directly (they
    now need a candidate) or assert a legacy status word (AC4).
- **Web:** vitest for the two components and the lib guards; a Playwright e2e for adding a candidate, changing the status, a duplicate 409,
  and the candidate's Applications tab.

## 7. Risks

- **The live-table migration (backfill, remap, new unique key).** It is guarded and refuses on duplicates. The full backend suite must run
  after rec-017.
- **`student_id` becomes nullable.** Every legacy reader inner-joins `users`, so external applications never reach those readers.
- **Interview result Selected now means Selected rather than Shortlisted (A2).** This is a deliberate behaviour change and is tested.
