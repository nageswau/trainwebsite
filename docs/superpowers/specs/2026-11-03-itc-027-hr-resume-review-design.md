# itc-027 — HR resume-review task, assignment rule, HR stages and HR workspace (design)

`DEC-SCOPE-354`. Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-027 (PDF §5 steps 2–6 and HR stages, §4 "HR / Placement",
§3 step 10, §8 HR dashboard, §11 HR workspace, §12 AC3/AC4; PDF classified `UNVERIFIED`). Owner Q-01 (2026-11-01): all phases approved
for build in waves. Dependencies itc-001 (#408), itc-002, itc-003, itc-026 (#424) and itc-028 (#423) are merged. The owner said to
proceed with the recommended answers, so every call below marked H* is the builder's (`NEEDS_CONFIRMATION`). The source PDF is not in
the repository, so the stage names below are the backlog's examples plus the builder's completion of the set.

## Intent

When an IT student (or their counselor / the IT Admin) uploads a resume version shared with HR (itc-026), HR gets one review task for
that student, assigned by a rule, and works it through stages in an HR workspace. The counselor sees where the review stands; the student
sees only a student-safe label and, when HR asks for changes, the action to take.

## Non-goals

- Changing the nehn-017 HR population/reads, `PlacementProfile` statuses (placement team) or the Interview/JobOffer flows (the HR page
  only links to them).
- An HR manager role (none exists): the IT Admin is the manager here (H5).
- Branch-based rules (no branch on IT students today), notes/sharing (itc-028 already gives HR notes with student sharing).

## Decisions (builder's calls)

- **H1 — Q-25 stages, separate from placement/offer statuses:** `resume_received`, `under_review`, `changes_requested`, `screening`,
  `interview_ready` (open) and `completed`, `withdrawn` (closed). Student-safe labels: Resume received · Under review · Action required:
  update your resume · Screening scheduled · Ready for interviews · Review complete · Review closed. HR moves freely between open stages
  and to `completed`; `withdrawn` is system-only; a closed task takes no stage move (409) until a new shared upload re-opens it.
- **H2 — one task per student (AC1):** `hr_review_tasks.student_user_id` is unique. A shared (`hr`) upload creates the task, or updates
  its `resume_version`; if the task is closed it re-opens at `resume_received`, and if it is at `changes_requested` it moves back to
  `resume_received` (the student acted). A `private` upload, or a student outside the nehn-017 HR population, creates nothing. The upload
  already locks the student's user row, so two uploads serialise; the unique key is the backstop.
- **H3 — Q-24 assignment rule:** the IT Admin maps a programme (course) to an active `hr_team` user (`hr_assignment_rules`, one per
  programme). On create/re-open without an active owner: the student's newest active enrolment whose programme has a rule with an active
  HR owner wins; else round-robin = the active HR user whose last assignment is oldest (never-assigned first, ties by id; stateless);
  else unassigned (the IT Admin assigns by hand). A re-opened task keeps its owner while that owner is active.
- **H4 — Q-26 scope:** HR works only tasks assigned to them; any other task (or student without a task) is 404. HR's existing
  nehn-017 read of the whole pool is unchanged.
- **H5 — management:** the IT Admin lists every task (filter by stage / unassigned, where unassigned includes deactivated owners — the
  deactivation edge case) and (re)assigns to an active HR user; edits the rules. Audited (itc-001) and the new owner is notified.
- **H6 — HR fields:** screening date, role preferences (≤300 chars), skill-gap notes (internal, ≤4000), and a fixed review checklist
  (contact details, education, skills, projects/experience, formatting) stored as the list of ticked keys. One PATCH saves fields and/or
  the stage; a stage change writes `hr_review_stage_history` (from, to, actor, reason) and every change one audit row (notes as
  "changed", itc-001's PII rule).
- **H7 — who sees what:** HR owner and IT Admin: the full task. The linked itc-003 counselor: stage (internal label), owner name,
  next action (fixed text per stage), screening date, updated time — never skill-gap notes, preferences or checklist. The student
  (`/it/me/hr-review`): the safe label, an action line for `changes_requested` only, and the updated date. Anyone else 403.
- **H8 — notifications (itc-002, fixed preview-safe text):** shared upload → `it.resume.uploaded` to the owner and the counselor (AC3);
  stage move → `it.placement.updated` to the student and new `it.hr_review.updated` to the counselor; manual assignment → new
  `it.hr_review.assigned` to the new owner.
- **H9 — withdrawal:** rec-010 opt-out and a placement-profile update that sets `withdrawn` close the open task as `withdrawn`
  (history, no notification); a later shared upload re-opens it.

## API (§12IZ)

- HR: `GET /hr/review-tasks?stage=&limit=&offset=` (own queue, newest activity first, paginated, `counts` per stage);
  `GET /hr/students/{id}/review` (full task); `PATCH /hr/students/{id}/review` `{stage?, screening_date?, role_preferences?,
  skill_gap_notes?, checklist?}`.
- IT Admin: `GET /admin/it/hr-review-tasks?stage=&unassigned=&limit=&offset=`; `PUT /admin/it/hr-review-tasks/{task_id}/owner`
  `{hr_user_id}`; `GET /admin/it/hr-assignment-rules` (programmes, rules, HR users); `PUT /admin/it/hr-assignment-rules/{program_id}`
  `{hr_user_id | null}` (null removes).
- Counselor: `GET /counselor/it/students/{id}/hr-review`; IT Admin: `GET /admin/it/students/{id}/hr-review` (both `{task: … | null}`).
- Student: `GET /it/me/hr-review` → `{status: {label, action, updated_at} | null}`.

## Data

Migration `0237_hr_review_tasks` (on `0236_it_at_risk`): `hr_review_tasks` (unique student, owner, stage CHECK, resume_version,
screening_date, role_preferences, skill_gap_notes, checklist JSON, assigned_at, closed_at, updated_by, timestamps; index
`(owner_user_id, stage)`), `hr_review_stage_history` (task, from, to, actor nullable, reason, created_at), `hr_assignment_rules`
(program PK, hr_user, updated_by, timestamps). Guarded create; downgrade drops. No existing data changes.

## UI

- HR: nav "Review Queue" → `/it/hr/queue` (stage filter, paginated table, link to the student). The HR student page gains
  `HrReviewCard` (stage, screening date, preferences, checklist, internal skill-gap notes, Save; links to Interviews and Shortlists).
- IT Admin: nav "Hr Reviews" → `/it/admin/hr-reviews`: the task table with owner reassign and the rules panel.
- Counselor/IT Admin student record (itc-012 page): read-only "HR review" card.
- Student Placement Status: "Resume review" card with the safe label and action.

## Acceptance (testable)

1. A shared upload creates exactly one task; a second shared upload updates it (no second row); a `private` upload creates none.
2. The owner follows the programme rule; without one, round-robin picks the least recently assigned active HR user.
3. The owner and the counselor get `it.resume.uploaded`.
4. A stage move writes history + audit and the counselor's view shows it; the counselor never gets skill-gap notes.
5. The student's payload has only the safe label (`changes_requested` → "Action required: update your resume").
6. **−** another HR user gets 404 on the task; a student calling the HR API gets 403.
7. **E** withdrawal closes the task; the IT Admin reassigns a deactivated owner's task.

## Risks

itc-026 upload path (the hook runs inside its transaction), nehn-017 HR access, rec-010 opt-out and the placement profile write
(`test_adm_007_placement`), pinned nav arrays.
