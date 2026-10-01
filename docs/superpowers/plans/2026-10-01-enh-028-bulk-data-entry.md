# ENH-028 Bulk Data Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CSV bulk entry for Academic Results, Psychometric, Test Prep and Language records, with idempotent replay,
per-row validation that never blocks the batch, and a batch/row audit trail.

**Architecture:** One new router module `app/api/school_bulk.py` holds a single upload routine driven by a small
`BulkTarget` description per module (role, row schema, natural key, tier key, record builder). Row validation is a Pydantic
model per module in `app/schemas.py`, reusing the existing text/list/date cleaners. Two new tables (migration `0051`). One
new React panel, configured per module from `lib/bulkEntry.ts`.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy, Alembic, PostgreSQL; Next.js 15 / React 19, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md` (approved with S1–S5; `DEC-SCOPE-043`).

## Global Constraints

- File ≤ 1,048,576 bytes (413 `The file is larger than 1 MB`); 1–500 filled-in rows (422).
- `Idempotency-Key` required, `[A-Za-z0-9._:-]{1,120}`; unique per (uploader, target_type, key); same key + same SHA-256 → 201 replay; different file → 422.
- Lock wait 5 s (`set_config('lock_timeout', '5s', true)`), sqlstate `55P03` → 409.
- Row rejection order: unknown code → outside portfolio → field validation → tier → duplicate. Messages never echo values.
- Results always `draft`; never call `require_school_entitlement` inside the loop (it commits on deny).
- Parent notices only after the commit, each isolated (try/commit/rollback); Results notify nobody.
- Logs carry ids and counts only.
- Existing single-record endpoints, roster upload and its tables: unchanged.
- No new dependencies.

## Review Focus

1. A CSV saved by Excel (UTF-8 BOM, CRLF, quoted cells with commas/newlines) — must parse like a plain file. → Task 3 test `test_excel_style_csv_parses`.
2. A template downloaded, left untouched and uploaded — must be 422 "no filled-in rows", not a batch of rejections. → Task 3 test `test_untouched_template_is_422`.
3. Header case/whitespace variations (`Student_Code `) — accepted. → Task 3 test `test_header_names_are_trimmed_and_case_insensitive`.
4. Same student twice in one file with different subjects — both accepted (only identical natural keys clash). → Task 3 test `test_same_student_different_subject_both_accepted`.
5. A key reused by a different user — processes as a new batch, never replays another user's report. → Task 3 test `test_another_users_key_never_replays`.

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/alembic/versions/0051_school_bulk_uploads.py` (new) | create the two tables |
| `apps/api/app/models.py` (modify) | `SchoolBulkUploadBatch`, `SchoolBulkUploadRow` |
| `apps/api/app/schemas.py` (modify) | `BulkResultRow`, `BulkPsychometricRow`, `BulkTestPrepRow`, `BulkLanguageRow` |
| `apps/api/app/api/school_bulk.py` (new) | targets, upload routine, template routine, 8 routes |
| `apps/api/app/main.py` (modify) | include `school_bulk.router` |
| `apps/web/lib/bulkEntry.ts` (new) | four `BulkTarget` configs (URLs, columns) |
| `apps/web/components/SchoolBulkEntryPanel.tsx` (new) | download/upload/report UI |
| `apps/web/app/school/academic-team/dashboard/page.tsx`, `…/psychometric-team/dashboard/page.tsx` (modify) | mount the panel |
| tests (new) | `test_enh_028_*.py`, `SchoolBulkEntryPanel.test.tsx`, `enh-028-bulk-entry.spec.ts` |
| docs (modify) | API_CONTRACT §12A, DATA_MODEL §6.13, RBAC_MATRIX, SCREEN_CATALOG, RTM, backlog status |

Commands (PowerShell, repo root; `$T` = `docker compose -p enh028 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps`):
- backend test: `$T -v "${PWD}\apps\api:/app" api-test python -m pytest -q -p no:cacheprovider tests/<file>`
- migrate the dev DB: `$T -v "${PWD}\apps\api:/app" api-test alembic upgrade head`
- web unit: `$T -v "${PWD}\apps\web:/app" -v /app/node_modules web-test npx vitest run <file>`

---

### Task 1: Tables, models, migration 0051

**Files:** Create `alembic/versions/0051_school_bulk_uploads.py`, `tests/test_enh_028_migration.py`; Modify `app/models.py` (after `SchoolRosterUploadRow`).

**Produces:** `SchoolBulkUploadBatch(id, target_type, uploaded_by_user_id, idempotency_key, file_sha256, total_rows, accepted_count, rejected_count, created_at, updated_at)`, `SchoolBulkUploadRow(id, batch_id, row_number, status, error_message, student_code, created_record_id)`, `BULK_TARGET_TYPES`.

- [ ] Write `test_enh_028_migration.py`: revision `0051_school_bulk_uploads`, down `0050_notification_channels`, single head; live columns/nullability match; unique constraint `uq_school_bulk_upload_key` on the three columns; CHECK `ck_school_bulk_upload_target_type`; downgrade/upgrade body only creates/drops these two tables (source scan).
- [ ] Run → FAIL (file missing).
- [ ] Add models + migration (create-table only, guarded like 0048).
- [ ] `alembic upgrade head`; run → PASS.
- [ ] Commit `feat(enh-028): bulk upload batch/row tables (migration 0051)`.

### Task 2: Row schemas

**Files:** Modify `app/schemas.py`; Create `tests/test_enh_028_schemas.py`.

**Produces:** `BulkResultRow`, `BulkPsychometricRow` (subclass of `PsychometricResultFields` adding `assessment_type`, `report_url`), `BulkTestPrepRow`, `BulkLanguageRow`, all `extra="ignore"`; `split_list_cell(value: str) -> list[str] | None`.

Tests (each asserts `validation_message(exc)` text or the parsed value):
- results: required fields `"academic_year is required"`; `max_marks "abc"` → `"max_marks must be a number"`; `0` and `10000` → `"max_marks must be greater than 0 and at most 9999.99"`; `marks_obtained -1` → `"marks_obtained must be between 0 and 9999.99"`; `150/100` → `"marks_obtained must not exceed max_marks"`; `nan`/`inf` rejected; subject 81 chars → `"subject must be at most 80 characters"`; grade 11 chars; remarks 2001 chars; NUL in subject rejected; valid row parses to floats/None.
- psychometric: `assessment_type` required/≤120; `report_url "javascript:x"` → `"report_url must start with http:// or https://"`; 501 chars; list cell `"A; b;a"` → `["A", "b"]`; date `"2026-13-01"` → `"test_date must be a date in YYYY-MM-DD format"`.
- test prep: `"IELTS"` → `"ielts"`; `"toefl"` → `"test_type must be one of ielts, sat"`; target_score 21 chars.
- language: required/≤60; level ≤30.
- [ ] Write tests → run → FAIL (import error). Implement → PASS. Commit `feat(enh-028): bulk row schemas`.

### Task 3: Upload routine + Results bulk upload

**Files:** Create `app/api/school_bulk.py`, `tests/enh028_helpers.py`, `tests/test_enh_028_bulk_core.py`, `tests/test_enh_028_bulk_results.py`; Modify `app/main.py`.

**Consumes:** Tasks 1–2; from `schools.py`: `_portfolio_school_ids`, `OUTSIDE_PORTFOLIO`, `_entitlement_denial`, `_today_ist`, `TIER_DENIED`, `_notify_student_parents`, `TEST_PREP_SERVICE_KEYS`, `logger` conventions.

**Produces:** `BulkTarget` dataclass, `RESULTS`, `_upload(target, file, key, user, db) -> dict`, route `POST /school/academic-team/results/bulk-upload`.

Core tests (via Results): missing key 422; bad key format 422; wrong role 403 (psychometric user); >1 MiB 413; non-UTF-8 422; NUL 422; malformed CSV (unterminated quote) 422; missing `subject` header 422 `Missing required column: subject`; 0 filled rows 422; 501 rows 422; **all of these leave no batch row**; replay same key+file → 201 identical report, no new results; same key different file → 422; another user's key → processes independently; concurrent same key (two `asyncio.gather` clients) → one batch, both 201 with the same batch id; report arithmetic; Review Focus 1–5; `bulk_upload_completed` log has counts, no codes/subjects.

Results tests: 40-row happy path → 40 drafts, each with `SchoolResultStatusHistory(none→draft)` and `school.result_create` audit carrying `bulk_batch_id`; one bad row among good ones; unknown code; outside-portfolio student (second school not in portfolio) → `OUTSIDE_PORTFOLIO`, others accepted; duplicate in file → `same student and academic_year, term and subject as row N of this file`; duplicate in DB (case-insensitive) → `this student already has a result for the same academic_year, term and subject`; untouched template rows skipped and not counted; no `Notification` rows created; uploader cannot verify a bulk draft (403), another member can.

- [ ] Write helpers + tests → run → FAIL (404 route).
- [ ] Implement `school_bulk.py` + include router → PASS. Refactor (keep the routine < ~150 lines). Commit `feat(enh-028): bulk results upload with idempotent replay and per-row validation`.

### Task 4: Psychometric bulk upload

**Files:** Modify `app/api/school_bulk.py`; Create `tests/test_enh_028_bulk_psychometric.py`.

Tests: assign rows → `assigned`; row with `report_url` → `completed`; ENH-027 fields stored (lists split on `;`, dates); audit `school.psychometric_record_create` `{assessment_type, fields, bulk_batch_id}`; parent notices: assigned vs report-ready titles identical to single create, one per accepted row, none for rejected rows; a school whose tier lacks `psychometric_test` → row rejected with the tier message + exactly one `school.tier_access_denied` audit for two denied rows of that school; notify failure (monkeypatched `_notify_student_parents` raising) keeps all records and returns 201; duplicate key incl. blank test_date.
- [ ] RED → GREEN → commit `feat(enh-028): bulk psychometric upload`.

### Task 5: Test Prep and Language bulk upload

**Files:** Modify `app/api/school_bulk.py`; Create `tests/test_enh_028_bulk_test_prep_language.py`.

Tests: test prep create (`in_progress`, target score), tier per row (`sat_coaching` missing on a lower tier while `ielts_coaching` allowed), duplicate student+test_type; language create, `foreign_language_classes` denial, case-insensitive duplicate; notices match single create; `academic_team` only.
- [ ] RED → GREEN → commit `feat(enh-028): bulk test prep and language upload`.

### Task 6: Pre-filled templates

**Files:** Modify `app/api/school_bulk.py`; Create `tests/test_enh_028_templates.py`.

Tests: each of the four templates: role-gated (403 other roles), `text/csv`, `attachment; filename=<module>-bulk-template.csv`, `Cache-Control: private, no-store`; header = `student_code,student_name,school_name,<module columns>`; one row per portfolio student only (a non-portfolio school's student absent); a student named `=HYPERLINK("x")` exported as `'=HYPERLINK("x")`; empty portfolio → header only; the downloaded template, filled and re-uploaded, is accepted (round trip).
- [ ] RED → GREEN → commit `feat(enh-028): pre-filled bulk templates`.

### Task 7: Frontend panel

**Files:** Create `apps/web/lib/bulkEntry.ts`, `apps/web/components/SchoolBulkEntryPanel.tsx`, `apps/web/tests/components/SchoolBulkEntryPanel.test.tsx`; Modify both dashboard pages.

Tests: empty state (no form, message); column reference lists the target's columns; template link `href` + `download`; submit without file → field error; loading → button "Uploading…" disabled, form `aria-busy`; success → "Upload result" heading focused, summary text, rows in file order with Student ID and "Added"/"Rejected"; 422 → `role=alert` with detail; network failure → connection message, then retry sends the **same** `Idempotency-Key`; choosing a new file sends a new key; `router.refresh` called after success.
- [ ] RED → GREEN; run lint + typecheck; commit `feat(enh-028): bulk entry panel on Academic and Psychometric dashboards`.

### Task 8: E2E + docs

**Files:** Create `apps/web/tests/e2e/enh-028-bulk-entry.spec.ts`; Modify API_CONTRACT, DATA_MODEL, RBAC_MATRIX, SCREEN_CATALOG, RTM, ENHANCEMENT_BACKLOG status.

E2E: seeded `school.academic1` downloads results template, fills two rows (one bad), uploads → report shows 1 added / 1 rejected → Results table shows the Draft; psychometric member uploads one assignment → Assessments list shows it.
- [ ] Run against the rebuilt `enh028` stack → PASS. Commit docs + e2e.

### Task 9: Verification gates

ruff format/check, mypy, full backend regression set (spec §11), vitest full, eslint, tsc, `next build`, Playwright (ENH-028 + regression specs), browser checklist at 1440/768/375/320. Record evidence in RTM. No completion claim without these outputs.
