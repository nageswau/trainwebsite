# itc-022 — Modules, labs, computed progress, trainer feedback and remediation (design + plan)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-022 (PDF §4 "Training progress: module/topic, … practical/lab completion,
trainer feedback, overall progress %, risk flag, remediation plan", §6; PDF classified `UNVERIFIED`; owner-approved for build in waves by
Q-01, 2026-11-01). **Decision:** `DEC-SCOPE-365`. **Dependencies:** itc-001 (`DEC-SCOPE-335`, merged) and itc-028 (`DEC-SCOPE-351`,
merged); itc-023 (merged) supplies the open risk flag a plan links to. Q-20 is open; built with the recommended answers below (owner:
"proceed with recommended answers"), each `NEEDS_CONFIRMATION`.

## Discovery (graphify-led)

| Class | Item |
|---|---|
| MUST CHANGE | `models.py` (+`ProgramModule`, `ProgramTopic`, `TopicCompletion`, `ItProgressFormula`, `RemediationPlan`; `Enrollment.progress_override_reason`); migration `0247_it_training_progress`; new `services/it_progress.py`, `api/it_progress.py`; `schemas.py` (lab type, override reason, plan/formula inputs); `workflows.py` (PATCH progress override; `refresh` after grading / assignment / assessment writes; batch-progress additive fields); `main.py` router tuple; `portal.py` (`progress-plans` header) |
| MAY CHANGE | `TrainerProgressPanel.tsx` (computed badge, breakdown, override, topics, remediation); `TeacherWorkspaceActions.tsx` (Lab option); `PortalPage.tsx`, `navigation.ts`; `it_student_360.py` + `ItStudent360View.tsx` (plans, read only) |
| SHOULD NOT CHANGE | `training_progress.py` builders (certificates, reports, KPIs share them); `_criteria`/eligibility rule; every reader of `Enrollment.progress_percent` (reports, management KPIs, placement, portal) — they keep reading the column; itc-028 notes service |
| HIGH REGRESSION RISK | certificate eligibility (nehn-031) and the reports reading `progress_percent`; the PATCH progress contract (nehn-028 tests); grading endpoints that gain a `refresh` call; PortalPage dispatch; Playwright `name:` substring matches on new buttons |

## Decisions (Claude's calls under "proceed with recommended answers", `NEEDS_CONFIRMATION`)

- **P1 structure (Q-20 "migrate?")** — modules and topics are per programme (`program_modules`, `program_topics`, ordered). The
  migration creates empty tables and **moves no data**; the IT Admin's **Progress Plans** page has "Copy from syllabus" which fills the
  form from the programme's PUB-025 manual syllabus (`{title, topics[]}`) or, failing that, one module per curriculum line. Saved only
  when the admin saves. So **nothing changes on deploy**.
- **P2 one save** — `PUT /admin/it/progress-plans/{program_id}` replaces the plan: modules/topics sent with an `id` are kept (renamed,
  reordered), new ones are created, missing ones are deleted (their completions cascade). Limits: ≤ 30 modules, ≤ 50 topics each,
  titles 1–200.
- **P3 formula (Q-20 "weights")** — per programme, optional: `topics`, `assignments`, `assessments` weights, integers 0–100 summing
  to **100** (otherwise 422). No weights = progress stays manual (today's behaviour). Computed **only** when weights are set **and** the
  plan has ≥ 1 topic (backlog edge: no modules → manual).
  `progress = round(Σ wᵢ·doneᵢ/totalᵢ / Σ wᵢ)` over the components whose total > 0 in that batch (a batch with no assessments yet can
  still reach 100 %); topics done/total, assignments graded/published (labs included), assessments passed/counted — the nehn-010 figures
  certificates already use. Half-up to a whole percent (the column is an integer).
- **P4 materialised** — the result is written to `enrollments.progress_percent`, so certificate eligibility, reports, KPIs, the portal
  and the 360 read it unchanged. `it_progress.refresh(db, batch_id)` recomputes the batch's **active** enrolments without an override in
  the same transaction as: a topic-completion change, a plan/weights save (every batch of the programme), clearing an override, and the
  existing writes that move a component (create/edit assignment, grade a submission, create/edit assessment, submit/grade an attempt).
  A programme without a formula costs one query and writes nothing. Completed/dropped seats are frozen.
- **P5 override** — the existing `PATCH /workflows/it/trainer/enrollments/{id}/progress` gains optional `reason` (≤ 500). On a
  computed programme a reason is **required** (422) and the value sticks (`progress_override_reason` set); `DELETE …/progress/override`
  clears it and recomputes. Both audited before/after (itc-001 `audit_change`, action `enrollment.progress_override`). A manual
  programme behaves exactly as before.
- **P6 topic completion** — `PUT /it/batches/{batch_id}/topics/{topic_id}/completions` `{enrollment_ids[1..500], completed}` marks or
  unmarks in bulk; idempotent (unique `(topic_id, enrollment_id)`, insert-on-conflict-nothing); each id must be an active enrolment of
  the batch (422 naming the count); the topic must belong to the batch's programme (404). Trainer of the batch or IT Admin. One audit
  row (ids and counts only).
- **P7 labs** — `assignment_type` accepts `lab` (additive); labs count as assignments in the formula and are reported separately
  (`labs_graded / labs_total`).
- **P8 trainer feedback = itc-028 notes** — the trainer already writes notes on their students with internal/student visibility,
  append-only and audited; a second `trainer_feedback` table would duplicate it. The student progress view links to Updates.
- **P9 remediation plan** — `remediation_plans`: actions (1–2000), owner, due date (not in the past, IST), status
  `open → in_progress → completed | cancelled` (any open state can move to any other; closed is final), the open itc-023 flag at
  creation linked. **AC3:** only for an `active` enrolment (422 otherwise). Owner must be the batch's trainer, the student's itc-003
  counselor, or an IT Admin (422). Create/edit: the batch trainer or the IT Admin; the owner may also change the status. Read: the
  itc-028 staff scope minus HR (trainer seated, counselor linked, IT Admin) and the student (their own plans, allow-listed fields:
  actions, due date, status, owner name). Every write audited before/after. No notification (not required).
- **P10 student view** — `GET /it/me/progress`: per active/completed enrolment: progress %, mode (computed/manual/override), the
  components, modules → topics with done ticks, and their remediation plans. Shown on the student's **Course** page.

## API (§12JK, additive)

| Method | Path | Who |
|---|---|---|
| GET | `/admin/it/progress-plans` | IT Admin — programmes with module/topic counts and weights |
| GET / PUT | `/admin/it/progress-plans/{program_id}` | IT Admin (GET also returns the syllabus/curriculum to copy from) |
| GET | `/it/batches/{batch_id}/topics` | trainer (own batch), IT Admin — modules, topics, completed enrolment ids |
| PUT | `/it/batches/{batch_id}/topics/{topic_id}/completions` | trainer (own batch), IT Admin |
| PATCH | `/workflows/it/trainer/enrollments/{id}/progress` | + optional `reason` |
| DELETE | `/workflows/it/trainer/enrollments/{id}/progress/override` | trainer (own batch), IT Admin |
| GET | `/workflows/it/batches/{id}/progress` | + `progress_mode`, per student `computed_percent`, `override_reason`, `topics_*`, `labs_*` |
| GET / POST | `/it/students/{student_id}/remediation-plans` · `/it/enrollments/{id}/remediation-plans` | read: staff scope; create: trainer/IT Admin |
| PATCH | `/it/remediation-plans/{id}` | trainer/IT Admin; owner (status only) |
| GET | `/it/me/progress` | IT student |

Errors: 401 anonymous; 403 wrong role; 404 out of scope (same as missing); 422 validation.

## Security review
AuthZ per endpoint above, resource scope via the batch's `trainer_id`, itc-003 link, enrolment. IDOR: every id is resolved inside the
caller's scope (404). Student payloads are allow-lists (no internal notes, no override reason, no audit). Inputs Pydantic-bounded; no raw
SQL; React escapes text. Logs carry ids only. CSRF/session unchanged (cookie proxy). No new secrets or integrations.

## Frontend
- **IT Admin › Progress Plans** (`/it/admin/progress-plans`): programme list → editor (modules with ordered topic inputs, add/remove,
  weights with a live "sums to N" check, Copy from syllabus, Save). Loading / empty / error states; labels on every input.
- **Trainer** (`TrainerProgressPanel`): the Progress cell shows `Computed`/`Override` badges; Details lists the breakdown and an
  override form (value + reason; "Use computed" clears); a **Topics** card: choose topic, tick students (select all), Mark complete /
  Mark not complete. A **Remediation** block per student in Details (list, create, status change).
- **Assignment form:** Work type gains **Lab**.
- **Student › Course:** "My progress" card.
- **360:** remediation plans (read only).

## Tests (TDD)
Backend `tests/test_itc_022_training_progress.py`: formula (+ renormalisation, half-up), weights ≠ 100 → 422, no topics → manual,
bulk completion (idempotent, non-active → 422, other batch → 403/404), refresh after grading, override required reason/audit/clear,
remediation AC3 + owner rule + scope (trainer other batch 404, counselor read, HR 403, student own allow-list), lab type, migration
up/down. Frontend vitest for the panels; Playwright e2e for admin plan → trainer bulk mark → student view.

## Plan
1. Migration + models (RED: migration test). 2. Service: plan read/save + formula validation. 3. Compute + refresh + hooks in
workflows. 4. Completions endpoints. 5. Override PATCH/DELETE. 6. Remediation. 7. Student `/it/me/progress`. 8. Batch progress
additive fields. 9. FE admin editor, trainer panel, student card, 360, Lab option. 10. Docs (DEC, API, RBAC, RTM, backlog). 11. e2e.

## Browser QA (2026-11-03, isolated stack: API :13122, web :18122)

| ID | Sev | Role / page | Issue | Fix |
|---|---|---|---|---|
| QA-01 | Medium | IT Admin / Progress Plans | The topic input's label "Module 1 topic 1" was a substring of its Remove button's name — two controls with one accessible name | Remove button named "Remove topic 1 of module 1" |
| QA-02 | Low | IT Admin / Progress Plans | Page title "Progress Plans" and card heading "Progress plans" repeated each other | Card heading "Plans by programme" |
| QA-03 | Low | Trainer / remediation form | The Owner list showed the caller twice ("Me" and "Name (trainer)") | The API returns `viewer_id`; the caller is listed once, "(me)" |
| QA-04 | Medium | Counselor (owner) / 360 | A plan's owner had no status buttons (the component did not know the reader) | Same `viewer_id`; the owner can move the status (verified in the browser) |
| QA-05 | Medium | Trainer / Student Progress, phone and tablet | The details row spans the 874 px table, so remediation plans and their buttons ran off-screen | The details content is pinned left and capped to the screen width (measured: fits at 390, 820, 1366) |
| QA-06 | Low | IT Admin / Progress Plans | Topic inputs were unstyled (outside `.field`) | Wrapped in `.field` (their labels are now visible too) |

Verified without issue: weights ≠ 100 (client message and API 422), blank titles blocked, Cancel, Copy from syllabus, bulk tick with a
double-click (one request's worth of rows: idempotent), override without a reason (the server's message is shown), override badge and
"Use worked-out figure", past due date 422, student 403 on completions, anonymous 401, trainer/student on the admin page get the existing
"Access unavailable" screen, the student card after refresh, the IT Admin's and the owner counselor's 360, no horizontal page overflow at
390/820/1366, no console errors beyond the deliberate 4xx probes.
