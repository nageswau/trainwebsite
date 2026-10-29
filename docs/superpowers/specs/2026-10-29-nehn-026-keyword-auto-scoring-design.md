# nehn-026 — Keyword-based auto-scoring for descriptive answers (design)

- **Feature:** `nehn-026` (`CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §nehn-026; `FEEDBACK_TRACKER.csv` row 27).
- **Evidence:** §9 "Evaluation" L209-213 (`MEETING_TRANSCRIPT_REQUEST`: "final scoring rules should be confirmed before implementation");
  `CLIENT_QUESTIONS.md` D-09 §4 (~80% order-independent keyword threshold discussed informally; **open**).
- **Dependency:** nehn-025 (merged, PR #395) — its template already carries the `keywords` column.
- **Numbering:** `DEC-SCOPE-333`; migration `0218_assessment_keyword_scoring`; API §12IE; RBAC §2.236.

## Intent

Trainers grading many written answers want a first-pass score. A text question can carry keywords; on submit the platform suggests a
score from how many keywords the answer contains. The trainer always reviews it and can override it. Keywords are the answer key, so a
student must never receive them.

## Builder's defaults (owner pre-authorised recommended answers; `NEEDS_CONFIRMATION` — D-09 §4 is still open)

- **K1 Keyword format.** `keywords` is a list of up to 30 entries, each 1-100 characters. One entry may list synonyms separated by `|`
  (`loop|iteration`): any synonym counts as that keyword. No weights.
- **K2 Matching.** Case-insensitive, order-independent, whole-word: the answer and the keyword are lower-cased (Unicode casefold), every
  non-letter/digit becomes a space, and a keyword (one or more words) matches when its word sequence appears in the answer's. A light
  plural rule lets `api` match `apis` and `class` match `classes` (trailing `s` / `es`). No other stemming, no NLP, no AI service.
- **K3 Rule.** match % = matched keywords ÷ keywords. **≥ 80% → full marks; below 80% → proportional** (`marks × matched ÷ total`, 2 dp).
  The 80% is one constant (`KEYWORD_THRESHOLD_PERCENT`), not per question.
- **K4 Trainer-reviewed.** A keyword score is a suggestion: an attempt with any text/file question still ends `submitted` (awaiting
  review) exactly as today; the suggested score is in the provisional total and is pre-filled in the grading form. Publishing the grade
  stays a trainer action. This is also the keyword-stuffing mitigation: no automatic result reaches a student unreviewed.
- **K5 Scope.** Only `text` questions take keywords; `mcq_*` and `file` questions with keywords are refused (422). File answers are never
  keyword-scored. Questions without keywords stay fully manual (score empty until the trainer grades).
- **K6 Matched keywords** are computed when the trainer opens the attempt (questions cannot change once attempted, so the result is stable);
  only the score (`auto_score`) is stored.

## Data (migration 0218, additive, no backfill)

- `assessment_questions.keywords` JSON NOT NULL, server default `[]`.
- `assessment_answers.auto_score` NUMERIC(10,2) NULL — the keyword suggestion, kept after an override.
- `assessment_answers.score_source` VARCHAR(10) NULL — `mcq` | `keyword` | `trainer`; NULL = not scored yet (existing rows stay NULL).
- Guarded add/drop (0001 builds a fresh DB from the models). Downgrade drops the columns.

## API (backward compatible; all additions)

- `AssessmentQuestionIn.keywords: list[str] = []` — single, bulk and import create paths. Trainer `GET …/questions` returns `keywords`.
- Import (nehn-025): the `keywords` column (comma separated, `|` synonyms) is now saved and shown in the preview; keywords on a non-text
  row is a row error; the "not saved yet" warning now names only `explanation`.
- Submit: text answers to keyword questions get `score = auto_score`, `score_source = "keyword"`; MCQ answers get `score_source = "mcq"`.
  Response unchanged.
- Trainer attempt detail: each answer adds `score_source`, `auto_score`, and for keyword questions `keywords`, `matched_keywords`,
  `match_percent`.
- Grade PATCH: a supplied score that differs from the stored one sets `score_source = "trainer"` (the `auto_score` is kept). The existing
  `assessment.attempt_grade` audit adds `overrides: [{answer_id, auto_score, score}]`.
- **Student payloads** (`start_assessment`, submit response, student learning views) keep their explicit field whitelists — no
  `keywords`, `auto_score` or `matched_keywords`. Tested.

## Authorization

Unchanged: trainer only on their own batches; it_admin all; students only via the existing whitelisted routes.

## UI (TeacherWorkspaceActions, QuestionImportPanel)

- "Add question": a "Keywords (written answers only)" field, comma separated, hint about `|` synonyms and the 80% rule.
- "Grade written attempt": a keyword-scored answer shows a badge "Keyword score · 4/5 · 80% matched" plus the matched / missing keywords,
  with the score pre-filled and editable; a trainer-overridden answer shows "Trainer score (keyword suggestion x)".
- Import preview shows the keywords column.

## Acceptance criteria (from the backlog)

1. Keywords [a,b,c,d,e], 80% threshold: an answer containing 4 gets full marks (K3); 3 gets 60% of the marks.
2. The trainer override replaces the auto score, keeps the suggestion, and is audited.
3. A student's view of the question or attempt never includes the keywords.
4. Questions without keywords stay manual.

## Non-goals

Weights, per-question thresholds, AI/semantic matching, non-English stemming, auto-publishing results, scoring file answers.

## Regression risks

Attempt status (`graded` vs `submitted`) must not change; MCQ scoring unchanged; nehn-025 import tests (warning text changes).

## Plan

1. Scoring function `app/services/keyword_scoring.py` + unit tests (RED → GREEN).
2. Model + migration 0218 + schema `keywords` validation (text only) + create/list routes.
3. Submit path (auto_score/score_source) + attempt detail breakdown + grade override audit; student-leak tests.
4. Import: save keywords; non-text keyword row error; warning text.
5. Frontend: keyword field, grading badge/matched list, import preview column + vitest.
6. Docs: decision register, API, RBAC, backlog, tracker.
