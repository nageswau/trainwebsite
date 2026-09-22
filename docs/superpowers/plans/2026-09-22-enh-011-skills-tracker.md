# ENH-011 School Skills Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Career Counselors run Soft Skills / Digital Skills batches (enrol → attendance → assessments → completion/certification) for one school each; parents and school staff see progress read-only.

**Architecture:** Six create-only tables (migration `0035_school_skills`), one new router module `app/api/school_skills.py` reusing `schools.py` helpers, Pydantic models in `app/schemas.py`; additive edits to the overview, timeline and entitlements handlers; four focused client components plus `lib/skills.ts` in the web app.

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL + Alembic; Pydantic v2; Next.js/React + vitest + Playwright. **No new dependency.**

**Spec:** `docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md`

## Global Constraints

- SCH-009 tables, routes, UI and tests are not modified.
- No existing table altered; migration is create-only; `downgrade()` drops only the new tables.
- Existing response fields unchanged; overview `skills` and timeline categories are additive.
- Error bodies are FastAPI `{"detail": ...}`; field names snake_case; no `Idempotency-Key`.
- Enums: `module_type` ∈ `soft_skills|digital_skills`; batch `status` ∈ `open|closed`; enrolment `status` ∈ `enrolled|completed|certified|withdrawn`.
- Limits: title 1–160; topic/trainer_name ≤120; session topic ≤160; assessment name 1–120; remarks ≤2000; `max_score` 0<x≤1000, 2 dp; ids per request 1–100 (enrol), 1–200 (attendance/scores); 200 enrolments per batch; page `limit` 1–100 default 25.
- Parent notifications only after commit, failure logged and swallowed.
- Backend DB tests run in the isolated compose project (user-authorised Docker only). Commands from repo root:
  `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh011 --profile ci run --rm --no-deps api-test python -m pytest <tests> -q`
  Web: `npm --prefix apps/web run test -- <file>`.

---

### Task 1: Shared free-text rule + request/response schemas (no DB)

**Files:** Modify `apps/api/app/schemas.py` (append ENH-011 block; generalise `clean_free_text` by length without changing its behaviour). Test: `apps/api/tests/test_enh_011_schemas.py`.

**Produces:** `SkillModule`, `SkillBatchStatus`, `SkillEnrollmentStatus` (Literals); `SkillBatchCreate`, `SkillBatchUpdate`, `SkillEnrollCreate`, `SkillEnrollmentUpdate`, `SkillSessionCreate`, `SkillAttendanceIn`, `SkillAssessmentCreate`, `SkillScoresIn`; outputs `SkillBatchOut`, `SkillBatchPage`, `SkillEnrollmentOut`, `SkillSessionOut`, `SkillAttendanceOut`, `SkillAssessmentOut`, `SkillScoreOut`, `SkillBatchDetail`.

- [ ] **Step 1: failing tests** — `test_enh_011_schemas.py`:
  - `test_batch_create_accepts_minimal_valid_payload` (school_id, module_type, title, start_date)
  - `test_batch_create_rejects_unknown_module_and_extra_fields` (`module_type="ielts"`, `status="closed"`, `created_by_user_id`)
  - `test_batch_create_rejects_end_before_start`
  - `test_batch_update_forbids_school_and_module` (`school_id`, `module_type` → ValidationError)
  - `test_enroll_requires_1_to_100_unique_ids`
  - `test_attendance_and_scores_reject_duplicate_enrollment_ids`
  - `test_score_bounds_and_remarks_text_rules` (score < 0 → error; remarks with `\x00`/`‮` → error; 2001 chars → error)
  - `test_max_score_bounds` (0 and 1000.01 → error; 1000 ok)
  - `test_existing_transfer_free_text_rule_unchanged` (500 ok, 501 error — guards the refactor)
- [ ] **Step 2: run, RED** — ImportError on `SkillBatchCreate` (expected reason: not defined).
- [ ] **Step 3: implement** — refactor:
  ```python
  def _clean_text(value: str | None, limit: int) -> str | None:  # body of today's clean_free_text with FREE_TEXT_MAX → limit
  def clean_free_text(value: str | None) -> str | None:
      return _clean_text(value, FREE_TEXT_MAX)
  def _text(limit: int):
      return Annotated[str | None, AfterValidator(lambda v: _clean_text(v, limit))]
  ```
  then the ENH-011 models (`extra="forbid"`, `str_strip_whitespace`), `model_validator` for end ≥ start, `field_validator` for unique id lists, `Decimal` with `max_digits=6, decimal_places=2`.
- [ ] **Step 4: run, GREEN**; also `tests/test_enh_005_schemas.py` still passes.
- [ ] **Step 5: commit** `feat(enh-011): request/response schemas for the skills tracker`.

### Task 2: Models + migration 0035 (no DB)

**Files:** Modify `apps/api/app/models.py` (after `SchoolLanguageRecord`); Create `apps/api/alembic/versions/0035_school_skills.py`; Test `apps/api/tests/test_enh_011_model.py`.

**Produces:** `SchoolSkillBatch`, `SchoolSkillEnrollment`, `SchoolSkillSession`, `SchoolSkillAttendance`, `SchoolSkillAssessment`, `SchoolSkillScore`.

- [ ] **Step 1: failing tests** — table names/columns per spec §4; defaults (`status` open / enrolled); named constraints `ck_skill_batch_module`, `ck_skill_batch_status`, `ck_skill_batch_dates`, `ck_skill_enrollment_status`, `ck_skill_assessment_max`, `ck_skill_score_nonneg`, uniques `uq_skill_enrollment_batch_student`, `uq_skill_session_batch_date`, `uq_skill_attendance_session_enrollment`, `uq_skill_assessment_batch_name`, `uq_skill_score_assessment_enrollment`; offline render of `0035` upgrade contains each `CREATE TABLE`, and `downgrade` renders `DROP TABLE` for all six and nothing else (`ALTER TABLE` absent); `revision="0035_school_skills"`, `down_revision="0034_school_transfer_requests"`.
- [ ] **Step 2: RED** — ImportError `SchoolSkillBatch`.
- [ ] **Step 3: implement** models + migration (same inspector guard as 0034; indexes per spec).
- [ ] **Step 4: GREEN.**
- [ ] **Step 5 [DB]:** `alembic upgrade head`, `downgrade -1`, `upgrade head` in the compose stack; record output.
- [ ] **Step 6: commit** `feat(enh-011): skills tracker tables and migration 0035`.

### Task 3: Batches — create, list, detail, update [DB]

**Files:** Create `apps/api/app/api/school_skills.py`; Modify `apps/api/app/main.py` (import + router tuple); Create `apps/api/tests/enh011_helpers.py` (`skills_world`: school A with 2 students + parent link, school B with 1 student, counselor with A in portfolio, second counselor with B, academic_team member; built on `enh005_helpers`); Test `apps/api/tests/test_enh_011_batches.py`.

**Produces:** `router`; `_require_career_counselor`; `_batch_in_portfolio(db, user, batch_id, lock=None) -> SchoolSkillBatch` (404 when missing/outside); `_batch_out`, `_detail(db, batch) -> dict`; logger `app.school.skills`.

- [ ] **Step 1: failing tests** — `test_counselor_creates_soft_and_digital_batches` (201, fields echoed, audit row `school.skill_batch_create` without student names); `test_school_outside_portfolio_is_403`; `test_non_counselor_roles_are_403_before_lookup` (academic_team, coordinator on POST and on GET of a random uuid → 403 not 404); `test_list_is_portfolio_scoped_filtered_and_paged` (B's batch absent; `module_type`/`status` filters; `limit=1` → total 2, one item; `limit=0` → 422); `test_detail_outside_portfolio_is_404`; `test_patch_edits_and_closes_and_rejects_school_change` (422 on `school_id`; end < start → 422 including when only one date is sent against the stored other).
- [ ] **Step 2: RED** — 404 on the new paths.
- [ ] **Step 3: implement** create/list/get/patch. List query: `select(SchoolSkillBatch, School.name, count(enrollments where status != withdrawn))` grouped, `order_by(created_at.desc(), id.desc())`, `total` via `select(func.count())`.
- [ ] **Step 4: GREEN.** **Step 5: commit** `feat(enh-011): career counselor skill batches`.

### Task 4: Enrolment + status transitions + notifications [DB]

**Files:** Modify `school_skills.py`; Test `apps/api/tests/test_enh_011_enrollments.py`.

**Produces:** `TRANSITIONS: dict[str, set[str]]`; `_frozen(student, batch) -> bool`; `_notify_after_commit(db, student, title, body)`.

- [ ] **Step 1: failing tests** — `test_enrol_creates_rows_and_notifies_linked_parent_once`; `test_enrol_student_from_other_school_is_422_and_writes_nothing` (mixed list: nothing written); `test_enrol_student_outside_portfolio_is_403`; `test_duplicate_enrolment_is_409`; `test_closed_batch_rejects_enrol_409`; `test_cap_of_200_is_409` (monkeypatch `school_skills.MAX_ENROLMENTS_PER_BATCH = 1`); `test_transitions_follow_the_table` (parametrised allowed/forbidden, `certified` terminal → 409); `test_same_status_is_noop_without_notification`; `test_completion_and_certification_notify_and_stamp_dates`; `test_status_change_allowed_on_closed_batch`; `test_frozen_enrolment_rejects_status_change_409` (`move_student_directly`); `test_notification_failure_does_not_fail_the_write` (monkeypatch `school_skills._notify_student_parents` to raise → 201/200, row committed).
- [ ] **Step 2: RED.**
- [ ] **Step 3: implement** — enrol: lock batch `with_for_update(key_share=True)`; check open, cap; for each id `_student_in_portfolio` (403) then `student.school_id == batch.school_id` else 422; insert; `flush` in `try/except IntegrityError → rollback, 409`; audit; commit; then notify each student in `try/except Exception: log warning`. Status: `select(...).with_for_update()` on enrolment; frozen → 409; same → return; not in `TRANSITIONS[old]` → 409; stamp `completed_at`/`certified_at`; audit; commit; notify on completed/certified.
- [ ] **Step 4: GREEN.** **Step 5: commit** `feat(enh-011): enrolment and completion with parent notifications`.

### Task 5: Sessions + attendance [DB]

**Files:** Modify `school_skills.py`; Test `apps/api/tests/test_enh_011_attendance.py`.

- [ ] **Step 1: failing tests** — `test_add_session_and_duplicate_date_409`; `test_session_date_outside_batch_dates_422`; `test_attendance_upsert_is_idempotent_and_returns_full_set` (PUT twice, second flips one mark; rows = 2 not 4); `test_attendance_for_enrolment_of_another_batch_422`; `test_attendance_for_withdrawn_certified_or_frozen_409`; `test_closed_batch_rejects_session_and_attendance_409`; `test_detail_attendance_summary_counts_present_and_marked`.
- [ ] **Step 2: RED.**
- [ ] **Step 3: implement** — batch `with_for_update(read=True)`; upsert via `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(index_elements=[session_id, enrollment_id], set_={present, marked_by_user_id, updated_at})`.
- [ ] **Step 4: GREEN.** **Step 5: commit** `feat(enh-011): sessions and attendance`.

### Task 6: Assessments + scores [DB]

**Files:** Modify `school_skills.py`; Test `apps/api/tests/test_enh_011_scores.py`.

- [ ] **Step 1: failing tests** — `test_multiple_assessments_and_duplicate_name_409`; `test_scores_upsert_and_remarks_stored`; `test_score_above_max_is_422`; `test_scores_for_frozen_or_withdrawn_409`; `test_closed_batch_rejects_assessment_and_scores_409`.
- [ ] **Step 2: RED.** **Step 3: implement** (same locking/upsert pattern). **Step 4: GREEN.** **Step 5: commit** `feat(enh-011): assessments and scores`.

### Task 7: Concurrency [DB]

**Files:** Test `apps/api/tests/test_enh_011_concurrency.py` (reuse `_client_for`/`_held` pattern from `test_enh_005_concurrency.py`).

- [ ] **Step 1: tests** — `test_two_concurrent_certifies_give_one_transition_and_one_notification`; `test_two_concurrent_enrolments_of_same_student_give_one_201_one_409`; `test_concurrent_enrolments_cannot_exceed_cap` (cap 1, two students).
- [ ] **Step 2: run** — expected to PASS if Task 4's locks are right; if any fails, fix the lock (RED is then genuine). **Step 3: commit** `test(enh-011): concurrency guarantees`.

### Task 8: Read surfaces — overview, timeline, entitlements [DB]

**Files:** Modify `apps/api/app/api/schools.py` (`student_overview`, `student_timeline`, `school_entitlements` only — additive); Test `apps/api/tests/test_enh_011_read_surfaces.py`; Modify `apps/api/tests/test_sch_011_entitlements.py` only if it asserts `used is None` for `soft_skills`/`web_designing`.

**Consumes:** `skills_overview(db, student_id) -> dict`, `skill_timeline_events(db, student_id) -> list[dict]`, `skill_usage(db, school_id) -> dict[str, int]` — defined in `school_skills.py`, imported lazily inside the three handlers (no import cycle: `school_skills` imports `schools` at module level).

- [ ] **Step 1: failing tests** — `test_overview_has_skills_block_for_parent_teacher_coordinator_principal`; `test_overview_skills_rollup_status` (certified > completed > in_progress > not_started; withdrawn-only → not_started); `test_other_students_skills_never_leak` (parent of kid0 cannot see kid1; school B coordinator 403); `test_timeline_has_enrolled_completed_certified_events`; `test_frozen_enrolment_still_visible_at_new_school`; `test_entitlements_count_non_withdrawn_enrolments` (bronze→soft only; silver→web_designing too).
- [ ] **Step 2: RED.** **Step 3: implement.** **Step 4: GREEN** + run `test_sch_009_test_prep_language.py test_sch_reports.py test_sch_011_entitlements.py test_enh_005_approve.py` unchanged-green. **Step 5: commit** `feat(enh-011): skills in overview, timeline and entitlements`.

### Task 9: Web — `lib/skills.ts` + nav

**Files:** Create `apps/web/lib/skills.ts`; Modify `apps/web/lib/navigation.ts:43`; Test `apps/web/tests/lib/skills.test.ts`.

**Produces:** types `SkillModule`, `SkillBatch`, `SkillBatchDetail`, `SkillEnrollment`, `SkillSession`, `SkillAssessment`; `MODULE_LABEL`, `ENROLMENT_LABEL`, `ENROLMENT_CLASS`, `TRANSITIONS`, `attendanceText({present, marked})`, `canEdit(enrollment)`.

- [ ] Tests: labels complete for every enum value; `TRANSITIONS` equals backend table; `attendanceText` ("No attendance yet", "4 of 5 sessions"); `canEdit` false for frozen/withdrawn/certified; counselor nav contains Skills → RED → implement → GREEN → commit.

### Task 10: Web — batches list page + panel

**Files:** Create `apps/web/app/school/career-counselor/skills/page.tsx`, `.../skills/loading.tsx`, `apps/web/components/SchoolSkillBatchesPanel.tsx`; Test `apps/web/tests/components/SchoolSkillBatchesPanel.test.tsx`.

- [ ] Tests: renders rows with module chip text and "N enrolled"; empty state + "Create batch" focuses title field; no-school state hides form; filter change shows skeleton then rows (aborts previous); Load more appends; create posts and `router.push`es to `/school/career-counselor/skills/{id}`; 422 marks field `aria-invalid` with message; 401 shows "Sign in again"; network error shows `NOT_COMPLETED`; double click sends one request → RED → implement → GREEN → commit.

### Task 11: Web — batch detail page, header, enrolments

**Files:** Create `.../skills/[id]/page.tsx`, `.../skills/[id]/loading.tsx`, `apps/web/components/SchoolSkillBatchHeader.tsx`, `apps/web/components/SchoolSkillEnrolments.tsx`; Tests `tests/components/SchoolSkillBatchHeader.test.tsx`, `SchoolSkillEnrolments.test.tsx`.

- [ ] Tests: header edit/save/close/reopen, closed banner; enrol picker fieldset/legend, filter, excludes enrolled, "Enrol 2 students", all-enrolled message; status control offers only `TRANSITIONS[current]`; frozen row shows "Transferred out" and no control; 409 detail shown in alert and focus moved → RED → implement → GREEN → commit.

### Task 12: Web — attendance and scores

**Files:** Create `apps/web/components/SchoolSkillAttendance.tsx`, `SchoolSkillScores.tsx`; Tests alongside.

- [ ] Tests: add session; select session shows labelled checkboxes for editable enrolments only; Mark all present; Unsaved changes indicator + `beforeunload` registered only while dirty; PUT body lists only editable rows; score inputs labelled "Score for X (out of N)", > max blocked client-side with message, server 422 mapped; closed batch hides controls → RED → implement → GREEN → commit.

### Task 13: Web — parent Skills card + timeline categories

**Files:** Modify `apps/web/components/SchoolChildOverview.tsx`, `apps/web/components/SchoolStudentTimeline.tsx`; Tests `tests/components/SchoolChildOverview.skills.test.tsx`, extend `tests/components/SchoolStudentTimeline.test.tsx`.

- [ ] Tests: Skills card with both subsections, attendance text and scores; empty text per module; overview without `skills` renders without crash and without the card; timeline labels "Soft skills"/"Digital skills"; existing `SchoolStudentTimeline`/`SchoolStudentDetailPanel`/`clientBoundary` tests still pass → RED → implement → GREEN → commit.

### Task 14: E2E + entitlements spec

**Files:** Create `apps/web/tests/e2e/enh-011-skills.spec.ts`; Modify `apps/web/tests/e2e/sch-011-entitlements.spec.ts:52-55`.

- [ ] Keyboard-driven counselor flow (create → enrol → session → attendance → assessment → score → certify) then parent sees Skills card and timeline events; `sch-011` expects a number for Soft skills. Run with the isolated stack (user-authorised). Commit.

### Task 15: Documentation propagation

**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-023), `docs/product/PRD_OPEN_ITEMS.md` item 77, `docs/architecture/DATA_MODEL.md`, `docs/architecture/API_CONTRACT.md` §12A, `docs/architecture/RBAC_MATRIX.md`, `docs/features/FEATURE_ACCEPTANCE_CRITERIA.md` (SCH-008-AC04 note), `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-011 status. Commit `docs(enh-011): register DEC-SCOPE-023 and propagate`.

### Task 16: Full regression run (not a completion claim)

- [ ] Full backend suite, full vitest, `tsc --noEmit`, lint, Playwright suite in the isolated stack; record results. Browser validation and independent Codex review remain outstanding after this plan.
