# rec-021 — Interview feedback (design)

**Status: IN REVIEW** on `feature/rec-021` (2026-10-11). QA: `docs/quality/REC-021_EXPLORATORY_QA_2026-10-11.md`.

- **Backlog:** `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-021. **Evidence:** `EVID-018` §15 (lines 654–674): nine fields captured
  "after every interview". **Dependency:** rec-020 (PR #193 @ `10da5148`), merged. The module scope is `DEC-SCOPE-116`.
- **Decision:** `DEC-SCOPE-175` (provisional). **Migration:** `0146_interview_feedback` on `0145_university_onboarding`. **API:** §12CP.
  **RBAC:** §2.101. All four are re-checked against `main` at merge.
- **Answers.** FB1–FB8 are **recommended defaults**, taken on the owner's standing instruction for build sessions ("proceed with the
  recommended answers; ask only if blocking"). They stay `UNVERIFIED` until the owner confirms them.
  - **FB1 (edge case "edited later"):** **one current feedback per interview**, overwritten by each save. A save writes one audit row
    `recruiter_interview.feedback` with the changed field **names** and the decision, never the text. A save with no change writes nothing.
  - **FB2 (AC1):** feedback can be **first recorded only on a Completed interview** (else 409). Once recorded it can be edited while the
    interview is Completed, On Hold, Selected or Rejected (the statuses the decision itself can lead to).
  - **FB3:** the fields:
    - Technical, communication and overall ratings, 1–5. **Overall is required**; the other two are optional. A 6 is a 422.
    - Strengths, weaknesses, recruiter comments and company feedback: optional text, up to 2,000 characters each.
    - Next round: optional, one of the five §14 rounds.
    - Final decision: optional, one of **Selected, Rejected, On Hold** (the interview's own decision statuses).
    - A next round with the decision Rejected is a 422 on `next_round`.
  - **FB4 ("the decision sets the interview status"):** a decision different from the current status moves the interview through
    rec-020's `change_status` in the same transaction: its move table (a decided interview cannot change its decision: 409), its history
    row (note `Feedback`), and IV8 (Rejected rejects the application; Selected on a Final or Client round selects it). No decision, or the
    current status, moves nothing.
  - **FB5 (AC2 "next round creates a draft for the next interview"):** the draft is the **schedule form opened with the suggested round
    pre-chosen** on the application's interviews, right after the save and again whenever the newest interview's feedback suggests a
    round. Nothing is inserted: an interview needs a confirmed future time (rec-020 IV4/IV5), which feedback does not know.
  - **FB6 (company feedback, "employer if allowed"):** the recruiter records the company's feedback as relayed. No employer write route in
    this item; the employer portal is unchanged.
  - **FB7 (Q-13 "Interview Verified may mark candidate skills"):** **not automatic.** A recruiter already sets a skill's source to
    Interview Verified on the candidate's skill profile (rec-011, Q-13 "any writer verifies").
  - **FB8 (who):** readers are the interview's readers (rec-020 IV10: the recruiter on their requirements, the manager on the team's, the
    assigned BDM, `super_admin`). Writers are rec-017's `WRITERS`. Employer, students, `hr_team` and `it_admin` never see feedback
    (internal, like the screening).

## 1. Data (migration 0146)

New table `interview_feedback` (TimestampMixin):

| Column | Type |
|---|---|
| `interview_id` | PK, FK to `interviews`, RESTRICT |
| `technical_rating`, `communication_rating` | smallint, NULL, CHECK 1–5 |
| `overall_rating` | smallint, NOT NULL, CHECK 1–5 |
| `strengths`, `weaknesses`, `recruiter_comments`, `company_feedback` | varchar(2000), NULL |
| `next_round` | varchar(20), NULL, CHECK in the §14 rounds |
| `final_decision` | varchar(16), NULL, CHECK in (selected, rejected, on_hold) |
| `recorded_by_user_id` | FK users, RESTRICT, NOT NULL |
| `created_at`, `updated_at` | timestamptz |

Plus CHECK `final_decision IS DISTINCT FROM 'rejected' OR next_round IS NULL`. The CHECK text lives once in `app.models.FEEDBACK_CHECKS`
and is repeated in the migration (a test keeps them equal). The step is guarded (0001 builds from the models); `downgrade()` refuses
while any row exists.

## 2. Service (`services/interviews.py`)

- `FEEDBACK_FIELDS`, `DECISIONS`, `FEEDBACK_EDITABLE = ("completed", "on_hold", "selected", "rejected")`.
- `save_feedback(db, user, interview, application, sent, now)`: the caller holds rec-020's `load_for_write` locks. FB2 gate → upsert the
  one row (FB1, audit names only) → FB4 move via `change_status`. Returns the previous status when it moved.
- `_out` gains `feedback` (null or the saved fields with labels, `recorded_by`, `updated_at`) and `can_feedback`. Feedback rows load in
  one batched query beside the history (no N+1).

## 3. API

`PUT /api/v1/recruiter/interviews/{id}/feedback` — body `RecInterviewFeedbackIn` (the whole form; a field left out is cleared;
`extra="forbid"`). One transaction; replies `{"interview": <item>}`. 404 out of scope / missing, 403 a non-writer, 409 FB2/FB4, 422
validation. Logged event `recruiter_interview_feedback_saved` with ids, field names and the decision only.

## 4. UI

- `RecruiterInterviewItem`: a "Record feedback" / "Edit feedback" action when `can_feedback`; a `FeedbackForm` (three rating selects,
  four textareas, next round, decision; `noValidate`, 422s on their fields, double-submit guard, Escape cancels); a "Feedback" summary
  (`<details>`) for every reader once recorded.
- `RecruiterApplicationInterviews`: FB5 — after a save whose feedback suggests a round, and whenever the newest interview's feedback does,
  "+ Schedule <round> (suggested)" opens `RecruiterInterviewForm` with `round` pre-chosen (`draftRound` prop).

## 5. Tests

- API (`tests/test_rec_021_feedback.py`): AC1 gate (scheduled → 409, completed → 200, edit after decision); validation (6 → 422,
  overall missing → 422, next round with Rejected → 422, unknown key → 422); FB4 moves + IV8 (rejected rejects the application,
  deciding-round selected selects it) and the 409 on changing a decided outcome; FB1 overwrite + audit names only + no-op; roles
  (manager reads not writes, another recruiter 404, other roles 403); `feedback`/`can_feedback` in reads.
- Migration (`tests/test_rec_021_migration.py`): chain, models = migration, round trip, constraint, downgrade refusal.
- Web (vitest): the form's body, its validation, the summary, the suggested-round draft.
- E2E (`tests/e2e/rec-021-interview-feedback.spec.ts`): complete → record feedback with next round → draft form pre-chosen → decision
  shown in history.

## 6. Plan (TDD, in order)

1. Migration + model + migration test (RED → GREEN).
2. Schema + service + route + API tests (RED → GREEN), rec-020 tests rerun.
3. Web lib types + `FeedbackForm` + summary + draft (vitest RED → GREEN), tsc + eslint.
4. Docs: DEC-SCOPE, API §, RBAC §, backlog status, this spec's status.
5. Docker stack, Playwright e2e + exploratory QA at desktop / tablet / mobile.
