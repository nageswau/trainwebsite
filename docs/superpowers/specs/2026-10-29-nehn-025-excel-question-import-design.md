# nehn-025 — Trainer question upload from a standard Excel template (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-025` (§9 L199-208, §10 L222, action 10).
- **Depends on:** nehn-004 (`services/tabular.read_tabular`, merged in PR #349).
- **Gate:** feature-ID authorised by the owner's feature prompt; builder's defaults below are `NEEDS_CONFIRMATION`.

## Goal

A trainer (or IT admin) downloads a standard `.xlsx` template, fills in questions, uploads it into an assessment, checks a
per-row preview and imports every row in one step. The questions land in the assessment exactly as if they had been typed one by one,
so MCQs auto-grade the same way. The assessment stays a Draft (invisible to students) until the trainer publishes it through
"Edit assessment".

## Design

**Backend** (no migration, no new table):

- `app/services/question_import.py` — the column list, `template_xlsx()` (openpyxl: a header-only `Questions` sheet first, then an
  `Instructions` sheet with a column reference and worked examples), and `parse_rows()` which turns `read_tabular` rows into
  `AssessmentQuestionIn` objects plus per-row errors and warnings.
- `GET /workflows/it/trainer/assessments/question-template.xlsx` — trainer / it_admin.
- `POST /workflows/it/trainer/assessments/{id}/questions/import?commit=false|true` (multipart `file`).
  - `commit=false` (default) is the dry run: `{total_rows, questions: [...], errors: [{row, message}], warnings: [...], created: 0}`.
  - `commit=true` re-parses the same file; any row error → 422, nothing written (all-or-nothing). Otherwise the rows are created through
    the bulk route's own insert path (one transaction, one `assessment.questions_import` audit row), appended after the current last
    position, in row order.
  - Same scope as the bulk route: trainer only on their own batch's assessment (403), it_admin any; 409 once a student has started an
    attempt; 404 unknown assessment. File refused by `read_tabular` → its status (413 / 415 / 422) with the messages joined.

**Columns:** `type` (mcq_single / mcq_multiple / text / file), `question`, `option_1`…`option_6`, `correct` (option numbers: `2` or
`1,3`), `marks` (whole number 1-10000, default 1), `keywords`, `explanation`. Required header columns: `type`, `question`; unknown or
repeated columns are refused (read_tabular `known`).

**Row rules:** type valid; question 2-10000 chars; MCQ: ≥ 2 filled options, no duplicate option text, `correct` names only filled
options, `mcq_single` exactly one; text / file: no options and no `correct`. Blank rows are skipped. Duplicate question text in the
file is a warning, not an error. Filled `keywords` / `explanation` are a warning: not saved yet (keyword scoring is nehn-026).

**Frontend:** `QuestionImportPanel` on the trainer's Assessments section (below "Add question"): template link → choose assessment
(locked ones disabled, as in "Add question") → choose file → **Check file** → preview (summary, error table, warnings, question
table; stacked on phones) → **Import N questions** (only with 0 errors) or **Choose another file**. After import: success message
that the assessment stays a Draft until published, and the page data reloads.

## Builder's defaults (`NEEDS_CONFIRMATION`)

- Q1 all-or-nothing import (any row error blocks the commit).
- Q2 import targets an existing assessment (the "Create assessment" form already defaults to Draft); it does not create the assessment.
- Q3 assignments are not generated from the template (the PDF says "assessment/assignment").
- Q4 images in questions are not supported (instructions say so); CSV is accepted too (same columns).
- Q5 `keywords` / `explanation` are accepted but not stored until nehn-026 adds the columns.
- Q6 no server idempotency key on commit; the UI disables the button while importing.

## Acceptance criteria → tests

1. Template filled with 20 mixed questions → dry run 0 errors; commit creates 20, assessment still Draft (pytest + e2e).
2. `correct=7` on 4 options → error names the row; commit 422; nothing created (pytest + vitest).
3. Imported MCQs auto-grade like manual ones (pytest: student attempt on an imported vs a manual question).
4. Students do not see the draft until published (pytest: examinations list + attempt start 404).

## Regression risks

The bulk question route (shares the insert helper); `TeacherWorkspaceActions` Assessments section; trn-006 / question-lock e2e specs.
