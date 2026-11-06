# pob-020: Role-specific screening forms, question bank and scorecard (design)

**Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` `pob-020` (classified `UNVERIFIED`). Dependencies built: pob-002
(`DEC-SCOPE-407`), hrc-001 (`DEC-SCOPE-371`). The owner assigned pob-020 for build on 2026-11-06 and said to proceed with the recommended
answers, so S1–S14 below are **the builder's calls (`NEEDS_CONFIRMATION`)**.

**Evidence gap:** the source docx (`Edusphere_Placement_Officer_Business_Development_CRM_Functional_Requirements.docx`, §10) is not on this
machine and the backlog does not list the five category names, so S1 is a proposal, not the document's wording.

## Goal

Replace "one fixed form, overwritten on every save" with a question bank, per-requirement forms, a kept history of screening sessions, a
scorecard and a side-by-side comparison, without breaking the rec-018 checklist other features read.

## Decisions

| # | Decision |
|---|---|
| S1 | Five categories: `experience` Experience and qualification, `technical` Technical skills, `communication` Communication, `availability` Availability and location, `compensation` Compensation. The seeded template "Standard 5-category screening" has one question for each. |
| S2 | **Additive.** `application_screenings`, `GET/PUT …/screening`, the board's `screening_result` and the rec-018 status moves stay as they are (backward compatibility). The backlog's "rewrite" is met by adding history underneath: every changed checklist save also appends a `legacy` session. |
| S3 | Q-15 = yes: the migration copies each existing checklist row to one `legacy` session (shortlisted→pass, hold→hold, rejected→reject, need_more_info→hold; the original result stays in the snapshot). Original rows are not touched. |
| S4 | Forms are versioned; question rows are immutable per `(form, version)`. Editing writes a new version. A session stores its `form_version`, so a form change never alters earlier sessions. Comparison is per version. |
| S5 | Team Lead = `placement_manager` (pob-001's mapping), and `super_admin`. Only they approve knock-outs. |
| S6 | Knock-outs are `yes_no` questions only, expected answer `yes` or `no` (default `yes`), and never in `compensation` (a recruiter without the salary grant could not answer them). |
| S7 | Knock-outs count only once approved on the requirement's form. Until then the runner shows "pending approval" and they act as ordinary questions. A new version keeps the approval when the knock-out set (text + expected answer) is unchanged, otherwise it goes back to pending. Approving names the version, so a stale screen gets a 409. |
| S8 | A failed approved knock-out forces the recommendation to `reject`, unless the screener ticks override and gives a reason (any writer; both are stored and shown). An approved knock-out must be answered. Other questions may be left unanswered. |
| S9 | A session never moves the application's status or notifies the candidate. A recommendation is advice; the screener moves the status with the existing action. (Status moves remain with the rec-018 checklist.) |
| S10 | Score: optional whole number 0–5 per answer. A `rating` answer scores itself when no score is sent. Scorecard = total, maximum (5 × scored answers), percent. No weights. |
| S11 | Sessions are immutable: no edit or delete route. A session needs an open application (409, same wording as rec-018) and the form's current version (409 otherwise, the runner reloads). |
| S12 | hrc-001 H2 applies: answers in the `compensation` category and the checklist's `expected_salary` are withheld without `candidates.compensation.view`; such a caller sending a compensation answer gets 403. Scores remain visible. |
| S13 | Bank and templates: read/write for `placement_team`, `placement_manager`, `super_admin`. Requirement form edit: the same three, within the requirement's scope, 409 on an ended requirement. Sessions: `applications.can_write` (recruiter, super_admin); manager and assigned BDM read (rec-018 SC8). Bank edits never alter existing forms because forms copy the question. Questions and templates are archived, never deleted. The default template cannot be archived. |
| S14 | A form session counts as "Screened" for hrc-021 engagement, and appears on the candidate timeline via a `recruiter_application.screening` audit row (ids + recommendation, never answers or notes). |

## Data (migration, guarded, additive)

- `screening_questions`: category, text, format (`text|yes_no|numeric|choice|rating`), choices, evaluation_criteria, expected_answer, active.
- `screening_forms`: `job_id` NULL = template, unique per requirement; name, is_default, version, knockout_status (`none|pending|approved`), approver + time, archived_at.
- `screening_form_questions`: form_id, version, position, a copy of the question, is_knockout, source question_id (`SET NULL`).
- `screening_sessions`: application_id (`RESTRICT`), kind (`form|legacy`), form_id, form_version, screened_by, notes, recommendation (`pass|hold|reject`), knockout_triggered, knockout_overridden, override_reason, legacy_snapshot, timestamps. Index `(application_id, created_at)`.
- `screening_answers`: session_id, form_question_id, answer, score (0–5), unique per pair.

Downgrade drops the five tables; the rec-018 table was never changed, so nothing is lost for it.

## API (`/api/v1/recruiter`)

| Route | Purpose |
|---|---|
| `GET/POST screening/questions`, `PATCH screening/questions/{id}` | Bank |
| `GET/POST screening/templates`, `PATCH screening/templates/{id}` | Templates (a PATCH with questions is a new version) |
| `GET/POST/PUT requirements/{id}/screening-form` | Read; create from a template (default if none named); new version |
| `POST requirements/{id}/screening-form/approve-knockouts` | Team Lead approval of a named version |
| `GET requirements/{id}/screening-comparison?version=` | Latest session per candidate on one version; at most 50, `truncated` flag; two queries for sessions and answers |
| `GET/POST applications/{id}/screening-sessions` | History plus current form; record a session |

Out of scope = 404 via the existing `load_scoped`; no student, employer or public route reads these tables (added to the hrc-001 leak test).

## Web

- `RecruiterScreeningSessions`: runner + history, shown in the candidate row's Screening panel above the existing checklist.
- `RecruiterScreeningForm`: on the requirement page, opened on demand: create from template, edit, approve knock-outs, comparison table.
- `/recruiter/screening-bank` and `/recruiter/manager/screening-bank`: bank and templates, in both menus.

Loading, empty and error states on every fetch; a `useRef` guard against double submission (the rec-018 pattern); the comparison uses the shared `.table stack` on phones.

## Not built

Weighted scoring, candidate self-completion, auto-assigning screening tasks (pob-027), automatic status moves from a recommendation (S9),
sharing scorecards with clients (pob-021).

## Acceptance criteria → tests

1. A form with 5 questions is created from the template: `test_ac1_*`, e2e.
2. A knock-out "No" sets the recommendation to reject unless overridden: `test_ac2_*`, e2e.
3. Two sessions keep their history: `test_ac3_*`, e2e.
4. The comparison shows scores: `test_ac4_*`, e2e.
5. Edge: the form changes after some candidates were screened: `test_edge_*`.
6. Answers and notes never reach candidate or employer APIs: `test_hrc_001_access` extension.
